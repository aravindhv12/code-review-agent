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
import tempfile
from typing import List, Dict, Tuple
from dotenv import load_dotenv
import psycopg2
import urllib.request
import urllib.error

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
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    try:
        return psycopg2.connect(database_url, sslmode="require", connect_timeout=5)
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        raise ValueError(f"Failed to connect to database: {str(e)}")

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

def find_git_executable():
    """Find git executable in the system"""
    import subprocess
    
    # Try to find git using which/where command
    try:
        git_path = shutil.which('git')
        if git_path:
            print(f"Found git via shutil.which: {git_path}")
            return git_path
    except Exception as e:
        print(f"shutil.which failed: {e}")
    
    # List of common git paths across different systems
    common_paths = [
        '/opt/homebrew/bin/git',   # macOS Homebrew Apple Silicon
        '/usr/local/bin/git',      # macOS Homebrew Intel
        '/usr/bin/git',            # Linux/Unix
        '/bin/git',                # Some systems
        'C:\\Program Files\\Git\\bin\\git.exe',  # Windows
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            print(f"Found git at: {path}")
            return path
    
    print("Warning: git executable not found in any common paths")
    return None


# Check git availability at startup
GIT_AVAILABLE = find_git_executable() is not None
if not GIT_AVAILABLE:
    print("WARNING: Git is not available on this system. Will use HTTP-based downloads for repository analysis.")
else:
    print("Git executable found. Repository analysis will use git cloning.")


def download_repo_selective(url, max_size_mb=50):
    """Download and selectively extract only needed files from GitHub repository"""
    normalized_url = normalize_repo_url(url)

    try:
        parts = normalized_url.rstrip('/').split('/')
        repo_name = parts[-1]
        owner = parts[-2]

        # Priority files to extract first
        priority_files = [
            "main.py", "app.py", "server.py", "index.js", "app.js", "server.js",
            "main.ts", "app.ts", "index.ts", "package.json", "requirements.txt",
            "setup.py", "pyproject.toml", "Dockerfile", "docker-compose.yml",
            "README.md", "readme.md", "index.html", "app.html"
        ]

        # File extensions to analyze
        supported_extensions = (".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".html", ".css", ".md")

        # Directories to skip
        skip_dirs = {
            "node_modules", ".git", "__pycache__", "dist", "build",
            "venv", "env", ".env", "coverage", ".next", ".nuxt",
            "target", "bin", "obj", ".vscode", ".idea"
        }

        extracted_files = {}
        total_downloaded = 0
        max_bytes = max_size_mb * 1024 * 1024  # Convert MB to bytes

        for branch in ['main', 'master']:
            zip_url = f"https://github.com/{owner}/{repo_name}/archive/refs/heads/{branch}.zip"
            print(f"Attempting to stream repo from: {zip_url}")

            try:
                # Stream the ZIP file instead of downloading entirely
                with urllib.request.urlopen(zip_url) as response:
                    with zipfile.ZipFile(io.BytesIO(response.read())) as zip_ref:
                        # Get list of files in the ZIP
                        zip_files = zip_ref.namelist()

                        # Filter files we want to extract
                        files_to_extract = []
                        for zip_file in zip_files:
                            # Skip directories
                            if zip_file.endswith('/'):
                                continue

                            # Get the relative path within the repo (remove the branch folder prefix)
                            parts = zip_file.split('/')
                            if len(parts) > 1:
                                rel_path = '/'.join(parts[1:])
                            else:
                                continue

                            # Skip files in unwanted directories
                            path_parts = rel_path.split('/')
                            if any(part in skip_dirs for part in path_parts):
                                continue

                            # Check if file has supported extension or is a priority file
                            filename = os.path.basename(rel_path).lower()
                            if (filename in priority_files or
                                rel_path.endswith(supported_extensions) or
                                any(rel_path.endswith(ext) for ext in supported_extensions)):
                                files_to_extract.append((zip_file, rel_path))

                        # Limit to top priority files to avoid excessive downloads
                        def get_file_priority(rel_path):
                            filename = os.path.basename(rel_path).lower()
                            if filename in priority_files:
                                return priority_files.index(filename)
                            elif filename.startswith(("main", "app", "index", "server")):
                                return 10
                            elif "test" in filename or "spec" in filename:
                                return 100
                            else:
                                return 50

                        files_to_extract.sort(key=lambda x: get_file_priority(x[1]))
                        files_to_extract = files_to_extract[:25]  # Limit to 25 files

                        # Extract only the selected files
                        for zip_file, rel_path in files_to_extract:
                            try:
                                with zip_ref.open(zip_file) as file_in_zip:
                                    content = file_in_zip.read()
                                    total_downloaded += len(content)

                                    # Check size limit
                                    if total_downloaded > max_bytes:
                                        print(f"Repository too large ({total_downloaded} bytes > {max_bytes} bytes). Stopping extraction.")
                                        break

                                    # Decode content
                                    try:
                                        text_content = content.decode('utf-8')
                                        extracted_files[rel_path] = text_content
                                    except UnicodeDecodeError:
                                        # Skip binary files
                                        continue

                            except Exception as e:
                                print(f"Failed to extract {zip_file}: {e}")
                                continue

                        if extracted_files:
                            print(f"Successfully extracted {len(extracted_files)} files from {branch} branch")
                            return extracted_files

            except urllib.error.HTTPError as e:
                print(f"Failed to download from {branch} branch: {e}")
                continue

        if not extracted_files:
            raise ValueError("Could not download repository from GitHub. Tried main and master branches.")

        return extracted_files

    except Exception as e:
        raise ValueError(f"Failed to parse repository URL or download: {str(e)}")


def analyze_repo(url):
    normalized_url = normalize_repo_url(url)

    with cache_lock:
        if normalized_url in repo_cache:
            return repo_cache[normalized_url]

    try:
        # Use selective extraction instead of full download
        print("Using selective repository extraction...")
        extracted_files = download_repo_selective(url)

        if not extracted_files:
            return [], "No supported code files were found in the repository.", "No repository files were analyzed."

        # File extensions to analyze
        supported_extensions = (".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".html", ".css", ".md")

        def get_file_priority(file_path):
            """Get priority score for a file (lower = higher priority)"""
            filename = os.path.basename(file_path).lower()
            priority_files = [
                "main.py", "app.py", "server.py", "index.js", "app.js", "server.js",
                "main.ts", "app.ts", "index.ts", "package.json", "requirements.txt",
                "setup.py", "pyproject.toml", "Dockerfile", "docker-compose.yml",
                "README.md", "readme.md", "index.html", "app.html"
            ]
            if filename in priority_files:
                return priority_files.index(filename)
            elif filename.startswith(("main", "app", "index", "server")):
                return 10
            elif "test" in filename or "spec" in filename:
                return 100  # Lower priority for test files
            else:
                return 50

        # Convert extracted files to analysis format
        files_to_analyze = []
        for rel_path, content in extracted_files.items():
            if len(content.strip()) >= 30:  # Skip very small files
                priority = get_file_priority(rel_path)
                files_to_analyze.append((rel_path, content, priority))

        # Sort by priority and limit to top 20 files
        files_to_analyze.sort(key=lambda x: x[2])
        files_to_analyze = files_to_analyze[:20]

        def analyze_single_file(file_info):
            """Analyze a single file"""
            rel_path, code, _ = file_info

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

    except Exception as e:
        print(f"Error during repo analysis: {e}")
        return [], f"Failed to analyze repository: {str(e)}", "Repository analysis failed."

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

# ================= HEALTH CHECK =================
@app.get("/health")
def health_check():
    """Health check endpoint to verify backend is running"""
    return {"status": "ok", "message": "Backend is running"}


@app.get("/health/db")
def health_check_db():
    """Health check endpoint to verify database connection"""
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ok", "message": "Database connection successful"}
    except Exception as e:
        return {"status": "error", "message": f"Database connection failed: {str(e)}"}, 503

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

        # Try to save to database, but don't fail if database is unavailable
        try:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reviews (code, review) VALUES (%s, %s)",
                (input.code, str({**parsed, "summary": summary, "walkthrough": walkthrough})),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as db_error:
            print(f"Warning: Failed to save to database: {str(db_error)}")
            # Continue anyway - database is optional for the review functionality

        return {**parsed, "summary": summary, "walkthrough": walkthrough}
    except Exception as e:
        return {"error": str(e)}


# ================= REPO REVIEW =================
@app.post("/review-repo")
def review_repo(input: RepoInput):
    try:
        results, readme, summary = analyze_repo(input.url)

        # Try to save to database, but don't fail if database is unavailable
        try:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reviews (code, review) VALUES (%s, %s)",
                (input.url, str({"files": results, "summary": summary})),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as db_error:
            print(f"Warning: Failed to save to database: {str(db_error)}")
            # Continue anyway - database is optional for the review functionality

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
from mangum import Mangum

handler = Mangum(app)

# Local development server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
