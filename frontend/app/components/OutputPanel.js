"use client";

import { motion } from "framer-motion";
import { Copy } from "lucide-react";
import { useState } from "react";

export default function OutputPanel({ review }) {
  const [copied, setCopied] = useState(false);

  const parse = (text) => ({
    bugs: text.split("### Bugs")[1]?.split("### Improvements")[0] || "",
    improvements: text.split("### Improvements")[1]?.split("### Fixed Code")[0] || "",
    fixed: text.split("### Fixed Code")[1] || "",
  });

  const { bugs, improvements, fixed } = parse(review);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(fixed);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  return (
    <div className="space-y-6">

      {["Bugs", "Improvements"].map((title, i) => (
        <motion.div
          key={title}
          whileHover={{ y: -4 }}
          className="p-5 rounded-2xl backdrop-blur-md bg-white/70 border border-white/10 shadow-2xl"
        >
          <h2 className={`font-semibold ${i === 0 ? "text-red-500" : "text-yellow-500"}`}>
            {title}
          </h2>

          <pre className="text-sm mt-2 whitespace-pre-wrap">
            {i === 0 ? bugs : improvements}
          </pre>
        </motion.div>
      ))}

      {/* FIXED CODE */}
      <motion.div
        whileHover={{ y: -4 }}
        className="p-5 rounded-2xl backdrop-blur-md bg-white/80 border border-white/10 shadow-2xl relative"
      >
        <h2 className="text-green-600 font-semibold">Fixed Code</h2>

        <button
          onClick={handleCopy}
          className="absolute top-4 right-4 flex items-center gap-2 text-xs bg-black text-white px-3 py-1 rounded-full active:scale-90 transition"
        >
          <Copy size={14} />
          {copied ? "Copied" : "Copy"}
        </button>

        <pre className="mt-3 font-mono text-sm whitespace-pre-wrap">
          {fixed}
        </pre>
      </motion.div>

    </div>
  );
}