"use client";

import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

// Initialize once per page load. `strict` security blocks any HTML/script in the
// diagram source — content is researcher-authored, but defense-in-depth is cheap.
let initialized = false;

/**
 * Renders a Mermaid diagram (flowchart, sequence, pie/xychart, etc.) from its text
 * source. Used by `ContentBlockRenderer` for code blocks whose language is "mermaid".
 * On a parse error it degrades to showing the raw source rather than breaking the page.
 */
export function MermaidDiagram({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!initialized) {
      mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict" });
      initialized = true;
    }
    const id = `mmd-${Math.random().toString(36).slice(2)}`;
    mermaid
      .render(id, chart)
      .then(({ svg }) => {
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
          setFailed(false);
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [chart]);

  if (failed) {
    return (
      <pre className="rounded-md bg-surface p-4 overflow-x-auto">
        <code className="font-mono text-sm text-foreground">{chart}</code>
      </pre>
    );
  }

  return <div ref={ref} className="my-4 flex justify-center [&_svg]:h-auto [&_svg]:max-w-full" />;
}
