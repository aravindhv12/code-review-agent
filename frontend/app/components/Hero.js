"use client";

import { motion } from "framer-motion";

export default function Hero({ scrollToEditor }) {
  return (
    <section className="h-[80vh] flex flex-col items-center justify-center text-center px-6">

      <motion.h1
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-6xl font-bold tracking-tighter"
      >
        AI Code Reviewer
      </motion.h1>

      <p className="text-gray-500 mt-4 max-w-xl">
        Analyze, fix, and improve your code instantly with AI.
      </p>

      <motion.button
        whileHover={{ scale: 1.1 }}
        onClick={scrollToEditor}
        className="mt-8 px-8 py-3 rounded-full bg-black text-white shadow-2xl"
      >
        Start Reviewing
      </motion.button>

    </section>
  );
}