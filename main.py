from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
import os
import re
from typing import List, Dict, Tuple
from dotenv import load_dotenv
import psycopg2

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
    # Temporarily disabled for Vercel deployment
    return {"error": "Repository analysis is currently disabled. Please use code review instead."}


@app.post("/download-repo")
def download_repo(input: RepoInput):
    # Temporarily disabled for Vercel deployment
    return {"error": "Repository download is currently disabled. Please use code review instead."}


# Vercel handler
from mangum import Mangum

handler = Mangum(app)
