"use client";

import { useEffect, useState } from "react";
import { intlLocale, useT } from "@/lib/i18n";
import { formatMs } from "./format";

type Point = { at: string; count: number; avg_ms: number; p95_ms: number };

const H = 160;

function useElementWidth(): [(el: HTMLDivElement | null) => void, number] {
  const [element, setElement] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(640);
  useEffect(() => {
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return [setElement, width];
}
const PAD = { top: 12, right: 12, bottom: 22, left: 52 };

/** Média e p95 ao longo do tempo. Uma escala só (ms); p95 contínuo, média tracejada. */
export function TimelineChart({ points, bucketMinutes }: { points: Point[]; bucketMinutes: number }) {
  const t = useT();
  const [hover, setHover] = useState<number | null>(null);
  const [container, width] = useElementWidth();
  if (!points.length) {
    return <p className="py-10 text-center text-[13px] text-foreground-muted">{t("Sem requisições nesta janela.")}</p>;
  }
  const max = Math.max(...points.map((p) => p.p95_ms), 1) * 1.1;
  const innerW = Math.max(width - PAD.left - PAD.right, 10);
  const innerH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  const line = (key: "avg_ms" | "p95_ms") => points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p[key])}`).join(" ");
  const ticks = [0, max / 2, max];
  const time = new Intl.DateTimeFormat(intlLocale(t.locale), {
    ...(bucketMinutes >= 24 * 60 ? { dateStyle: "short" } : { hour: "2-digit", minute: "2-digit" }),
  });
  const hovered = hover === null ? null : points[hover];
  const step = points.length > 1 ? innerW / (points.length - 1) : innerW;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-4 text-xs text-foreground-muted">
        <span className="flex items-center gap-1.5">
          <svg width="18" height="4" aria-hidden><line x1="0" y1="2" x2="18" y2="2" stroke="var(--color-accent)" strokeWidth="2" /></svg>
          p95
        </span>
        <span className="flex items-center gap-1.5">
          <svg width="18" height="4" aria-hidden>
            <line x1="0" y1="2" x2="18" y2="2" stroke="var(--color-accent)" strokeWidth="2" strokeDasharray="4 3" />
          </svg>
          {t("Média")}
        </span>
      </div>
      <div className="relative" ref={container}>
        <svg width={width} height={H} role="img" aria-label={t("Tempo das requisições ao longo do tempo")} className="block">
          {ticks.map((v) => (
            <g key={v}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} stroke="var(--color-border)" strokeWidth="1" />
              <text x={PAD.left - 8} y={y(v)} dy="0.32em" textAnchor="end" className="fill-foreground-subtle text-[11px]">
                {formatMs(v, t.locale)}
              </text>
            </g>
          ))}
          <text x={PAD.left} y={H - 6} className="fill-foreground-subtle text-[11px]">{time.format(new Date(points[0].at))}</text>
          <text x={width - PAD.right} y={H - 6} textAnchor="end" className="fill-foreground-subtle text-[11px]">
            {time.format(new Date(points[points.length - 1].at))}
          </text>
          <path d={line("avg_ms")} fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeDasharray="4 3" />
          <path d={line("p95_ms")} fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinejoin="round" />
          {hovered && (
            <g>
              <line x1={x(hover!)} x2={x(hover!)} y1={PAD.top} y2={PAD.top + innerH} stroke="var(--color-border-strong)" />
              <circle cx={x(hover!)} cy={y(hovered.p95_ms)} r="4" fill="var(--color-accent)" stroke="var(--color-surface)" strokeWidth="2" />
            </g>
          )}
          {points.map((p, i) => (
            <rect
              key={p.at}
              x={x(i) - step / 2}
              y={PAD.top}
              width={Math.max(step, 6)}
              height={innerH}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
        </svg>
        {hovered && (
          <div
            className="pointer-events-none absolute top-0 z-10 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs shadow-sm"
            style={{ left: Math.min(x(hover!) + 10, width - 170) }}
          >
            <div className="font-medium">{new Date(hovered.at).toLocaleString(intlLocale(t.locale))}</div>
            <div className="text-foreground-muted">
              p95 {formatMs(hovered.p95_ms, t.locale)} · {t("Média")} {formatMs(hovered.avg_ms, t.locale)}
            </div>
            <div className="text-foreground-muted">{t.plural(hovered.count, "{n} requisição", "{n} requisições")}</div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Distribuição das durações de uma simulação (histograma de barras finas). */
export function DurationHistogram({ durations }: { durations: number[] }) {
  const t = useT();
  if (!durations.length) return null;
  const min = Math.min(...durations);
  const max = Math.max(...durations);
  const bins = Math.min(20, Math.max(5, Math.ceil(Math.sqrt(durations.length))));
  const size = (max - min) / bins || 1;
  const counts = new Array<number>(bins).fill(0);
  for (const d of durations) counts[Math.min(bins - 1, Math.floor((d - min) / size))]++;
  const top = Math.max(...counts);
  return (
    <div className="flex flex-col gap-1">
      <div className="flex h-24 items-end gap-0.5" role="img" aria-label={t("Distribuição das durações")}>
        {counts.map((c, i) => {
          const from = min + i * size;
          return (
            <div
              key={i}
              title={`${formatMs(from, t.locale)} – ${formatMs(from + size, t.locale)}: ${c}`}
              className="flex-1 rounded-t-[4px] bg-accent"
              style={{ height: c ? `${Math.max((c / top) * 100, 4)}%` : 0 }}
            />
          );
        })}
      </div>
      <div className="flex justify-between text-[11px] text-foreground-subtle">
        <span>{formatMs(min, t.locale)}</span>
        <span>{formatMs(max, t.locale)}</span>
      </div>
    </div>
  );
}
