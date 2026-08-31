"use client";

/**
 * Recharts measures the DOM to size itself, so its output differs between the
 * server render and the first client render. Mounting it only after hydration
 * removes that mismatch class entirely, at the cost of one frame.
 */

import { useEffect, useState, type ReactNode } from "react";

export function ChartFrame({
  height = 220,
  children,
}: {
  height?: number;
  children: ReactNode;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <div
        style={{ height }}
        className="flex items-center justify-center text-xs text-ink-faint"
        aria-hidden
      />
    );
  }
  return <div style={{ height }}>{children}</div>;
}

export const CHART_COLORS = [
  "#1d4e89",
  "#4a7fb5",
  "#7aa5cd",
  "#a8c4de",
  "#cbd2dc",
  "#8a5a00",
];
