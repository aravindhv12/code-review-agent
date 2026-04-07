"use client";

export default function HistoryPanel({ history }) {
  return (
    <section className="max-w-5xl mx-auto mt-20">

      <h2 className="text-3xl font-bold tracking-tighter mb-6">
        Recent Reviews
      </h2>

      <div className="space-y-4">
        {history.map(item => (
          <div
            key={item.id}
            className="p-4 rounded-xl backdrop-blur-md bg-white/70 border border-white/10 shadow-xl"
          >
            <p className="text-xs text-gray-400">{item.created_at}</p>

            <pre className="text-sm mt-2">{item.code}</pre>

            <details className="mt-2 text-gray-600">
              <summary>View Review</summary>
              <pre className="mt-2 whitespace-pre-wrap">
                {item.review}
              </pre>
            </details>
          </div>
        ))}
      </div>

    </section>
  );
}