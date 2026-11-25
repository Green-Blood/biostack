"use client";
import { useCallback, useEffect, useRef, useState } from "react";

/** Measured width of a container, so the SVG is drawn at real pixel size (crisp text, no horizontal scroll). */
export function useChartWidth(initial = 640): [(el: HTMLDivElement | null) => void, number] {
  const [width, setWidth] = useState(initial);
  const observer = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: HTMLDivElement | null) => {
    observer.current?.disconnect();
    observer.current = null;
    if (!el) return;
    setWidth(Math.round(el.getBoundingClientRect().width) || initial);
    observer.current = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width) || initial));
    observer.current.observe(el);
  }, [initial]);
  useEffect(() => () => observer.current?.disconnect(), []);
  return [ref, width];
}
