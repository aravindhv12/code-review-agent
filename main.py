from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
import os
import re
import io
import zipfile
import shutil
import time
import threading
import concurrent.futures
from typing import List, Dict, Tuple
from dotenv import load_dotenv
import psycopg2
from git import Repo

load_dotenv()

app = FastAPI()

# ================= CORS =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ================= DB =================
def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")

repo_cache: Dict[str, Tuple[List[dict], str, str]] = {}
cache_lock = threading.Lock()


def normalize_repo_url(url: str) -> str:
    return url.rstrip("/").removesuffix(".git")

# ================= MODELS =================
class CodeInput(BaseModel):
    code: str

class RepoInput(BaseModel):
    url: str

# ================= PARSER =================
REVIEW_REGEX = re.compile(
    r"BUGS:\s*(.*?)\s*IMPROVEMENTS:\s*(.*?)\s*FIXED_CODE:\s*(.*)",
    re.S | re.I,
)


def retry_api_call(func, max_retries=3, base_delay=1):
    """Retry API calls with exponential backoff on rate limit errors."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            error_msg = str(e).lower()
            if "rate limit" in error_msg or "429" in error_msg:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    time.sleep(delay)
                    continue
            raise e


def parse_ai(text, fallback):
    try:
        match = REVIEW_REGEX.search(text)
        if match:
            bugs = match.group(1).strip() or "No bugs found"
            improvements = match.group(2).strip() or "No improvements"
            fixed_code = match.group(3).strip() or fallback
        else:
            bugs = "No bugs found"
            improvements = "No improvements"
            fixed_code = fallback

        return {
            "bugs": bugs,
            "improvements": improvements,
            "fixed_code": fixed_code,
        }
    except Exception:
        return {
            "bugs": "Could not extract bugs",
            "improvements": "Could not extract improvements",
            "fixed_code": fallback,
        }


# ================= REVIEW HELPERS =================
def build_review_prompt(code):
    return f"""
You are a senior engineer.
Analyze the code below and respond EXACTLY in this format.

BUGS:
- Describe any bug, wrong behavior, or logic issue.

IMPROVEMENTS:
- Describe any refactoring, readability, performance, or style improvements.

FIXED_CODE:
- Provide the full corrected code with all suggested changes applied.

Code:
{code}
"""


def summarize_text(text, prompt):
    def _call():
        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
        )
        return res.choices[0].message.content

    return retry_api_call(_call)


def analyze_code(code):
    prompt = build_review_prompt(code)

    def _call():
        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
        )
        ai_text = res.choices[0].message.content
        parsed = parse_ai(ai_text, code)
        return parsed, ai_text

    return retry_api_call(_call)


def generate_code_walkthrough(code):
    def _call():
        prompt = (
            "Provide a line-by-line walkthrough for the updated code below. "
            "Explain what each section does and why it works. Keep the walkthrough focused on the updated code only.\n\n"
            f"Updated Code:\n{code}"
        )
        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
        )
        return res.choices[0].message.content

    return retry_api_call(_call)


def analyze_repo(url):
    normalized_url = normalize_repo_url(url)

    with cache_lock:
        if normalized_url in repo_cache:
            return repo_cache[normalized_url]

    repo_path = "temp_repo"

    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)

    repo_url = normalized_url + ".git"

    try:
        Repo.clone_from(repo_url, repo_path)
    except Exception as e:
        raise ValueError(f"Clone failed: {str(e)}")

    # Priority files to analyze first
    priority_files = [
        "main.py", "app.py", "server.py", "index.js", "app.js", "server.js",
        "main.ts", "app.ts", "index.ts", "package.json", "requirements.txt",
        "setup.py", "pyproject.toml", "Dockerfile", "docker-compose.yml",
        "README.md", "readme.md", "index.html", "app.html"
    ]

    # File extensions to analyze
    supported_extensions = (".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".html", ".css", ".md")

    def get_file_priority(file_path):
        """Get priority score for a file (lower = higher priority)"""
        filename = os.path.basename(file_path).lower()
        if filename in priority_files:
            return priority_files.index(filename)
        elif filename.startswith(("main", "app", "index", "server")):
            return 10
        elif "test" in filename or "spec" in filename:
            return 100  # Lower priority for test files
        else:
            return 50

    def collect_files():
        """Collect and prioritize files to analyze"""
        all_files = []
        for root, dirs, files in os.walk(repo_path):
            # Skip common directories
            dirs[:] = [d for d in dirs if d not in [
                "node_modules", ".git", "__pycache__", "dist", "build",
                "venv", "env", ".env", "coverage", ".next", ".nuxt",
                "target", "bin", "obj", ".vscode", ".idea"
            ]]

            for file in files:
                if file.endswith(supported_extensions):
                    path = os.path.join(root, file)
                    rel_path = os.path.relpath(path, repo_path)
                    priority = get_file_priority(rel_path)
                    all_files.append((rel_path, path, priority))

        # Sort by priority and limit to top 20 files
        all_files.sort(key=lambda x: x[2])
        return all_files[:20]

    def analyze_single_file(file_info):
        """Analyze a single file"""
        rel_path, full_path, _ = file_info

        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()
        except Exception:
            return None

        if len(code.strip()) < 30:
            return None

        # Limit code snippet size for efficiency
        snippet = code[:3000] if len(code) > 3000 else code

        try:
            parsed, _ = analyze_code(snippet)
            return {
                "file": rel_path,
                "bugs": parsed["bugs"],
                "improvements": parsed["improvements"],
                "fixed_code": parsed["fixed_code"],
                "original_code": code
            }
        except Exception:
            return None

    # Collect files to analyze
    files_to_analyze = collect_files()

    if not files_to_analyze:
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)
        return [], "No supported code files were found in the repository.", "No repository files were analyzed."

    # Analyze files in parallel
    results = []
    analysis_items = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_file = {executor.submit(analyze_single_file, file_info): file_info for file_info in files_to_analyze}
        for future in concurrent.futures.as_completed(future_to_file):
            result = future.result()
            if result:
                results.append(result)
                analysis_items.append(
                    f"File: {result['file']}\nBugs: {result['bugs']}\nImprovements: {result['improvements']}"
                )

    # Generate comprehensive summary
    if results:
        # Create context for AI analysis
        analysis_context = "\n\n".join(analysis_items[:15])

        # Generate overall repo summary
        summary = summarize_text(
            analysis_context,
            "Analyze this repository code analysis and provide a comprehensive summary in under 150 words. "
            "Describe what the repository does, its main technologies, architecture, and overall code quality. "
            "Highlight key features and any notable patterns or frameworks used.\n\n" + analysis_context
        )

        # Only generate README if there are actual fixes/improvements
        has_fixes = any(
            result["fixed_code"].strip() != result["original_code"].strip()[:3000]
            for result in results
            if result["fixed_code"].strip()
        )

        if has_fixes:
            readme = summarize_text(
                analysis_context,
                "Write a comprehensive README.md for this repository based on the code analysis. "
                "Include sections: Project Description, Features, Technologies Used, Installation, Usage, "
                "and any important notes about code quality or improvements.\n\n" + analysis_context
            )
        else:
            readme = ""
    else:
        summary = "No repository files were successfully analyzed."
        readme = ""

    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)

    with cache_lock:
        repo_cache[normalized_url] = (results, readme, summary)

    return results, readme, summary


def build_repo_zip(results, readme):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as zf:
        # Only include README if it exists
        if readme.strip():
            zf.writestr("README.md", readme)

        # Only include files that have actual fixes
        for item in results:
            if item["fixed_code"].strip() and item["fixed_code"].strip() != item.get("original_code", "").strip()[:3000]:
                zf.writestr(item["file"], item["fixed_code"])
    buffer.seek(0)
    return buffer


# ================= CODE REVIEW =================
@app.post("/review")
def review_code(input: CodeInput):
    try:
        parsed, _ = analyze_code(input.code)

        summary = summarize_text(
            input.code,
            f"Explain the behavior of this code in under 100 words and highlight the key issues and improvements.\n\nCode:\n{input.code}",
        )

        walkthrough = generate_code_walkthrough(parsed["fixed_code"])

        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO reviews (code, review) VALUES (%s, %s)",
            (input.code, str({**parsed, "summary": summary, "walkthrough": walkthrough})),
        )
        conn.commit()
        cursor.close()
        conn.close()

        return {**parsed, "summary": summary, "walkthrough": walkthrough}
    except Exception as e:
        return {"error": str(e)}


# ================= REPO REVIEW =================
@app.post("/review-repo")
def review_repo(input: RepoInput):
    try:
        results, readme, summary = analyze_repo(input.url)

        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO reviews (code, review) VALUES (%s, %s)",
            (input.url, str({"files": results, "summary": summary})),
        )
        conn.commit()
        cursor.close()
        conn.close()

        return {"files": results, "readme": readme, "summary": summary}
    except Exception as e:
        return {"error": str(e)}


@app.post("/download-repo")
def download_repo(input: RepoInput):
    try:
        normalized_url = normalize_repo_url(input.url)

        with cache_lock:
            if normalized_url in repo_cache:
                results, readme, _ = repo_cache[normalized_url]
            else:
                results, readme, _ = analyze_repo(input.url)

        buffer = build_repo_zip(results, readme)
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=repo-updated.zip"},
        )
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


# Vercel handler
def handler(request, context):
    from mangum import Mangum

    # Create ASGI handler for Vercel
    asgi_handler = Mangum(app)

    return asgi_handler(request, context)
