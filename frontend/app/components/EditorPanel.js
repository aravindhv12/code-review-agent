"use client";

import Editor from "@monaco-editor/react";
import Tilt from "react-parallax-tilt";

export default function EditorPanel({ code, setCode }) {
  return (
    <Tilt scale={1.02} glareEnable>
      <div className="rounded-3xl overflow-hidden backdrop-blur-md bg-white/60 border border-white/20 shadow-2xl">

        <Editor
          height="500px"
          defaultLanguage="python"
          theme="vs-light"
          value={code}
          onChange={(v) => setCode(v)}
        />

      </div>
    </Tilt>
  );
}