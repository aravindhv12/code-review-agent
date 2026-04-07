"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export default function Home() {
  const [mode, setMode] = useState("code");
  const [code, setCode] = useState("");
  const [review, setReview] = useState<any>(null);
  const [repoUrl, setRepoUrl] = useState("");
  const [repoResults, setRepoResults] = useState<any[]>([]);
  const [readme, setReadme] = useState("");
  const [summary, setSummary] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const copyToClipboard = async (text: string) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch (err) {
      console.error("Copy failed", err);
    }
  };

  const summaryPoints = (text: string) => {
    return text
      .split(/(?:\n|\r\n|(?<=[.?!])\s+(?=[A-Z]))/)
      .map((line) => line.trim().replace(/^[-*•\s]+/, ""))
      .filter(Boolean)
      .slice(0, 8);
  };

  const reset = () => {
    setCode("");
    setRepoUrl("");
    setReview(null);
    setRepoResults([]);
    setReadme("");
    setSummary("");
    setError("");
  };

  const switchMode = (m: "code" | "repo") => {
    setMode(m);
    reset();
  };

  const handleReview = async () => {
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });

      const data = await res.json();

      if (data.error) {
        setError(data.error);
        setReview(null);
      } else {
        setReview(data);
        setSummary(data.summary || "");
      }
    } catch (err) {
      setError("Failed to connect backend");
    }

    setLoading(false);
  };

  const handleRepo = async () => {
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/review-repo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: repoUrl }),
      });

      const data = await res.json();

      if (data.error) {
        setError(data.error);
        setRepoResults([]);
      } else {
        setRepoResults(Array.isArray(data.files) ? data.files : []);
        setReadme(data.readme || "");
        setSummary(data.summary || "");
      }
    } catch (err) {
      setError("Repo analysis failed");
    }

    setLoading(false);
  };

  const handleDownloadZip = async () => {
    if (!repoUrl) return;
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/download-repo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: repoUrl }),
      });

      if (!res.ok) {
        throw new Error("Download failed");
      }

      const blob = await res.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = "repo-updated.zip";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      setError("Download failed");
    }

    setLoading(false);
  };

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="relative overflow-hidden">
        <div className="pointer-events-none absolute -left-24 top-12 h-72 w-72 rounded-full bg-slate-200/70 blur-3xl" />
        <div className="pointer-events-none absolute right-0 top-48 h-80 w-80 rounded-full bg-sky-200/40 blur-3xl" />

        <section className="mx-auto max-w-7xl px-6 py-16 lg:py-24">
          <div className="grid gap-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
            <div className="space-y-8">
              <p className="inline-flex rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold uppercase tracking-[0.3em] text-white shadow-lg shadow-slate-900/10">
                Smart Review, Faster Shipping
              </p>
              <h1 className="text-5xl font-semibold tracking-tight text-slate-950 sm:text-6xl">
                Turn code review into a premium design experience.
              </h1>
              <p className="max-w-2xl text-lg leading-8 text-slate-600">
                Analyze code quality, discover bugs, and ship cleaner code with a refined interface inspired by Apple and Nike. Everything feels calm, polished, and effortless.
              </p>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                <button
                  onClick={() => switchMode("code")}
                  className="inline-flex items-center justify-center rounded-full bg-slate-950 px-7 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
                >
                  Review Code
                </button>
                <button
                  onClick={() => switchMode("repo")}
                  className="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white px-7 py-3 text-sm font-semibold text-slate-950 transition hover:border-slate-400"
                >
                  Analyze Repo
                </button>
              </div>
            </div>

            <div className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-8 shadow-[0_40px_120px_-60px_rgba(15,23,42,0.2)] backdrop-blur-xl">
              <div className="mb-6 flex flex-wrap gap-3 text-sm font-medium text-slate-700">
                <span className={`rounded-full px-4 py-2 ${mode === "code" ? "bg-slate-950 text-white" : "bg-slate-100"}`}>
                  Code
                </span>
                <span className={`rounded-full px-4 py-2 ${mode === "repo" ? "bg-slate-950 text-white" : "bg-slate-100"}`}>
                  Repo
                </span>
              </div>
              <p className="text-slate-500 leading-7">
                {mode === "code"
                  ? "Paste your code and get a structured review with bug detection, improvements, and automatic fixes."
                  : "Provide a GitHub repository URL and get a high-level analysis with repo-specific recommendations."
                }
              </p>
              <div className="mt-8 rounded-[1.75rem] bg-slate-950/5 p-6">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-3xl bg-white p-5 shadow-sm">
                    <p className="text-sm uppercase tracking-[0.25em] text-slate-400">Mode</p>
                    <p className="mt-3 text-lg font-semibold text-slate-900">{mode === "code" ? "Code Review" : "Repo Audit"}</p>
                  </div>
                  <div className="rounded-3xl bg-white p-5 shadow-sm">
                    <p className="text-sm uppercase tracking-[0.25em] text-slate-400">Status</p>
                    <p className="mt-3 text-lg font-semibold text-slate-900">{loading ? "Analyzing" : "Ready to review"}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <section className="mx-auto max-w-7xl px-6 pb-20">
        <div className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-6 rounded-[2rem] border border-slate-200/80 bg-white p-8 shadow-[0_40px_120px_-60px_rgba(15,23,42,0.15)]">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-2xl font-semibold text-slate-950">Workspace</h2>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  Switch between code and repository review workflows with a smooth, elevated interface.
                </p>
              </div>
              <div className="inline-flex overflow-hidden rounded-full border border-slate-200 bg-slate-100">
                <button
                  onClick={() => switchMode("code")}
                  className={`px-5 py-2 text-sm font-semibold transition ${mode === "code" ? "bg-slate-950 text-white" : "text-slate-600 hover:bg-white"}`}
                >
                  Code
                </button>
                <button
                  onClick={() => switchMode("repo")}
                  className={`px-5 py-2 text-sm font-semibold transition ${mode === "repo" ? "bg-slate-950 text-white" : "text-slate-600 hover:bg-white"}`}
                >
                  Repo
                </button>
              </div>
            </div>

            {error && (
              <div className="rounded-3xl bg-red-50 p-4 text-sm text-red-700">
                {error}
              </div>
            )}

            {mode === "code" ? (
              <>
                <textarea
                  className="min-h-[260px] w-full rounded-[1.5rem] border border-slate-200 bg-slate-50 p-5 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200"
                  placeholder="Paste code to review"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
                <button
                  onClick={handleReview}
                  className="inline-flex items-center justify-center rounded-full bg-slate-950 px-8 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
                >
                  {loading ? "Analyzing..." : "Review Code"}
                </button>

                {review && (
                  <div className="mt-8 space-y-6">
                    <div className="grid gap-6 md:grid-cols-2">
                      <div className="rounded-[1.75rem] bg-slate-50 p-6 shadow-sm border border-slate-200">
                        <div className="flex items-center gap-3">
                          <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-red-100 text-red-700">!</span>
                          <div>
                            <h3 className="text-lg font-semibold text-slate-950">Bugs Found</h3>
                            <p className="text-sm text-slate-500">Issues and unexpected behaviors identified in your code.</p>
                          </div>
                        </div>
                        <pre className="mt-4 whitespace-pre-wrap rounded-2xl bg-white p-4 text-sm leading-6 text-slate-700 border border-slate-200">
                          {review.bugs || "No bugs found."}
                        </pre>
                      </div>

                      <div className="rounded-[1.75rem] bg-slate-50 p-6 shadow-sm border border-slate-200">
                        <div className="flex items-center gap-3">
                          <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700">✓</span>
                          <div>
                            <h3 className="text-lg font-semibold text-slate-950">Improvements</h3>
                            <p className="text-sm text-slate-500">Refactoring, readability, and performance upgrades.</p>
                          </div>
                        </div>
                        <pre className="mt-4 whitespace-pre-wrap rounded-2xl bg-white p-4 text-sm leading-6 text-slate-700 border border-slate-200">
                          {review.improvements || "No improvements found."}
                        </pre>
                      </div>
                    </div>

                    <div className="rounded-[1.75rem] bg-slate-50 p-6 shadow-sm border border-slate-200">
                      <div className="flex items-start justify-between gap-4">
                        <h3 className="text-lg font-semibold text-slate-950">Fixed Code</h3>
                        <button
                          onClick={() => copyToClipboard(review.fixed_code || code)}
                          className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-700 transition hover:border-slate-400"
                        >
                          Copy
                        </button>
                      </div>
                      <pre className="mt-3 max-h-72 overflow-auto rounded-2xl bg-slate-950/95 p-4 text-sm leading-6 text-slate-100 font-mono">
                        {review.fixed_code || code}
                      </pre>
                    </div>

                    {review.walkthrough && (
                      <div className="rounded-[1.75rem] bg-slate-50 p-6 shadow-sm border border-slate-200">
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <h3 className="text-lg font-semibold text-slate-950">Code Walkthrough</h3>
                            <p className="text-sm text-slate-500">Step through the updated code line-by-line.</p>
                          </div>
                          <button
                            onClick={() => copyToClipboard(review.walkthrough)}
                            className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-700 transition hover:border-slate-400"
                          >
                            Copy
                          </button>
                        </div>
                        <pre className="mt-3 max-h-72 overflow-auto rounded-2xl bg-white p-4 text-sm leading-6 text-slate-700 border border-slate-200">
                          {review.walkthrough}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : (
              <>
                <input
                  className="w-full rounded-[1.5rem] border border-slate-200 bg-slate-50 p-5 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200"
                  placeholder="GitHub repo URL"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                />
                <button
                  onClick={handleRepo}
                  className="inline-flex items-center justify-center rounded-full bg-slate-950 px-8 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
                >
                  {loading ? "Analyzing Repo..." : "Analyze Repo"}
                </button>
              </>
            )}

            <div className="grid gap-4 pt-4 sm:grid-cols-2">
              <div className="rounded-[1.5rem] bg-slate-100 p-5">
                <h3 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-500">Output</h3>
                <p className="mt-3 text-sm leading-6 text-slate-600">Review results appear here with clean, easy-to-scan insights.</p>
              </div>
              <div className="rounded-[1.5rem] bg-slate-100 p-5">
                <h3 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-500">Confidence</h3>
                <p className="mt-3 text-sm leading-6 text-slate-600">Built for calm focus with a premium layout and subtle visual hierarchy.</p>
              </div>
            </div>
          </div>

          <aside className="space-y-6">
            {summary && (
              <div className="rounded-[2rem] bg-slate-950 p-8 text-white shadow-[0_40px_120px_-60px_rgba(15,23,42,0.25)]">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-semibold">Summary</h2>
                    <p className="mt-2 text-sm text-slate-300">Clear, actionable insights from the review.</p>
                  </div>
                  <button
                    onClick={() => copyToClipboard(summary)}
                    className="rounded-full border border-slate-700 bg-slate-900/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-200 transition hover:border-slate-500"
                  >
                    Copy Summary
                  </button>
                </div>
                <ul className="mt-4 space-y-3 text-sm leading-7 text-slate-200">
                  {summaryPoints(summary).map((point, idx) => (
                    <li key={idx} className="flex gap-3">
                      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-slate-200" />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {readme && readme.trim() && (
              <div className="rounded-[2rem] bg-white p-8 shadow-[0_40px_120px_-60px_rgba(15,23,42,0.1)]">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-semibold text-slate-950">README</h2>
                    <p className="mt-2 text-sm text-slate-500">Copy or review the generated repository README.</p>
                  </div>
                  <button
                    onClick={() => copyToClipboard(readme)}
                    className="rounded-full border border-slate-300 bg-slate-50 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-700 transition hover:border-slate-400"
                  >
                    Copy README
                  </button>
                </div>
                <pre className="mt-4 max-h-72 overflow-auto whitespace-pre-wrap text-sm leading-6 text-slate-600">{readme}</pre>
              </div>
            )}

            {repoResults.length > 0 && (
              <div className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-[0_30px_90px_-60px_rgba(15,23,42,0.12)]">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-xl font-semibold text-slate-950">Repo Results</h2>
                    <p className="mt-2 text-sm text-slate-500">Download all generated fixes and README as a zip file (only includes modified files).</p>
                  </div>
                  <button
                    onClick={handleDownloadZip}
                    className="inline-flex items-center justify-center rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
                    disabled={loading}
                  >
                    {loading ? "Preparing ZIP..." : "Download ZIP"}
                  </button>
                </div>
                <div className="mt-5 space-y-5">
                  {repoResults.map((file: any, index) => (
                    <div key={index} className="rounded-[1.5rem] bg-slate-50 p-5 border border-slate-200">
                      <p className="font-semibold text-slate-900">{file.file}</p>
                      <div className="mt-3 space-y-3">
                        <div>
                          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">Bugs</p>
                          <pre className="mt-2 whitespace-pre-wrap rounded-2xl bg-white p-4 text-sm leading-6 text-slate-700 border border-slate-200">
                            {file.bugs || "No bugs found."}
                          </pre>
                        </div>
                        <div>
                          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">Improvements</p>
                          <pre className="mt-2 whitespace-pre-wrap rounded-2xl bg-white p-4 text-sm leading-6 text-slate-700 border border-slate-200">
                            {file.improvements || "No improvements found."}
                          </pre>
                        </div>
                        <div>
                          <div className="flex items-start justify-between gap-4">
                            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">Fixed Code</p>
                            <button
                              onClick={() => copyToClipboard(file.fixed_code || "")}
                              className="rounded-full border border-slate-300 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-700 transition hover:border-slate-400"
                            >
                              Copy
                            </button>
                          </div>
                          <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded-2xl bg-slate-950/95 p-4 text-sm leading-6 text-slate-100 border border-slate-800 font-mono">
                            {file.fixed_code || "No fixed code available."}
                          </pre>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </aside>
        </div>
      </section>
    </main>
  );
}
