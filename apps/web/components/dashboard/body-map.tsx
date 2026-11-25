"use client";
import { useMemo, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, FlaskConical, MapPin, ScanLine, Scale, Stethoscope, type LucideIcon } from "lucide-react";
import { RANK, type Finding, type Level, type Region } from "./body-map-model";
import { ANCHOR, Legs, LEGS, ORDER, SHAPES, SKEL, SKEL_ANCHOR, SKEL_SHAPES, SKELETAL, TORSO } from "./anatomy";

const OX = 170, OY = 10, W = 640, H = 680, EDGE_L = 190, EDGE_R = 450;

const HEX: Record<Level, string> = { high: "#ff4d6d", warn: "#ffb020", ok: "#34d399", info: "#38bdf8" };
const DOT: Record<Level, string> = { high: "bg-[#ff4d6d]", warn: "bg-[#ffb020]", ok: "bg-[#34d399]", info: "bg-[#38bdf8]" };
const KIND_ICON: Record<Finding["kind"], LucideIcon> = { diagnosis: Stethoscope, markers: FlaskConical, scan: ScanLine, visceral: Scale, waist: Scale };
const LEVELS: Level[] = ["high", "warn", "ok", "info"];

/** Push labels apart so none overlap, keeping them in range. */
function spread(items: { r: Region; y: number }[], min = 44, lo = 26, hi = 654) {
  const s = [...items].sort((a, b) => a.y - b.y);
  s.forEach((it, i) => { it.y = Math.max(it.y, i === 0 ? lo : s[i - 1].y + min); });
  for (let i = s.length - 1; i >= 0; i--) s[i].y = Math.min(s[i].y, hi - (s.length - 1 - i) * min);
  return s;
}

export type BodyMapProps = {
  findings: Finding[]; names: Record<Region, string>; where: Record<Region, string>; levelNames: Record<Level, string>;
  layerNames: { organs: string; skeleton: string }; label: string; openLabel: string; emptyLabel: string; whereLabel: string; side: ReactNode;
};

export function BodyMap({ findings, names, where, levelNames, layerNames, label, openLabel, emptyLabel, whereLabel, side }: BodyMapProps) {
  const levelOf = (r: Region): Level | null => findings.filter((f) => f.region === r).sort((a, b) => RANK[a.level] - RANK[b.level])[0]?.level ?? null;
  const active = ORDER.filter((r) => levelOf(r));
  const chips = [...active].sort((a, b) => RANK[levelOf(a)!] - RANK[levelOf(b)!]);
  const [sel, setSel] = useState<Region | null>(chips[0] ?? null);
  const [layer, setLayer] = useState<"organs" | "skeleton">("organs");
  // Joints and the spine show on both layers once they have a finding; the skeleton layer also draws the bones and the quiet joints.
  const pick = (r: Region) => { setSel(r); if (layer === "skeleton" && !SKELETAL.has(r)) setLayer("organs"); };
  const counts = LEVELS.map((l) => ({ l, n: active.filter((r) => levelOf(r) === l).length })).filter((c) => c.n > 0);
  const press = (r: Region) => (e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(r); } };
  const selLevel = sel ? levelOf(sel) : null;
  const anchor = layer === "skeleton" ? SKEL_ANCHOR : ANCHOR;
  const shapeOf = (r: Region) => (layer === "skeleton" ? SKEL_SHAPES[r] : SHAPES[r]);
  const shown = ORDER.filter((r) => (layer === "skeleton" ? SKELETAL.has(r) : !SKELETAL.has(r) || levelOf(r) !== null));

  const callouts = useMemo(() => {
    const out: { r: Region; ax: number; ay: number; ly: number; side: "L" | "R" }[] = [];
    for (const side of ["L", "R"] as const) {
      const items = shown.filter((r) => levelOf(r) && anchor[r].side === side).map((r) => ({ r, y: anchor[r].y + OY }));
      for (const it of spread(items)) out.push({ r: it.r, ax: anchor[it.r].x + OX, ay: anchor[it.r].y + OY, ly: it.y, side });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layer, findings]);

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="order-2 min-w-0 space-y-4">
        {active.length === 0 ? <p className="holo-panel p-4 text-sm text-[#8fb0d6]">{emptyLabel}</p> : (
          <>
            <ul className="grid grid-cols-4 gap-2">
              {counts.map(({ l, n }) => (
                <li key={l} className="holo-panel px-3 py-2" style={{ boxShadow: `inset 0 -2px 0 ${HEX[l]}` }}>
                  <span className="block text-2xl font-semibold leading-none tnum" style={{ color: HEX[l] }}>{n}</span>
                  <span className="mt-1 block text-[11px] leading-tight text-[#8fb0d6]">{levelNames[l]}</span>
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-1.5">
              {chips.map((r) => (
                <button key={r} type="button" onClick={() => pick(r)} aria-pressed={sel === r}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors ${sel === r ? "border-cyan-300 bg-cyan-400/15 text-white" : "border-cyan-400/25 text-[#b9d4f2] hover:bg-cyan-400/10"}`}>
                  <span className={`size-1.5 rounded-full ${DOT[levelOf(r)!]}`} aria-hidden />{names[r]}
                </button>
              ))}
            </div>
            {sel && selLevel && (
              <div aria-live="polite" className="holo-panel space-y-3 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-lg font-semibold text-white">{names[sel]}</h3>
                  <span className="rounded-full px-2.5 py-0.5 text-xs font-medium" style={{ color: HEX[selLevel], background: `${HEX[selLevel]}1f` }}>{levelNames[selLevel]}</span>
                </div>
                <p className="flex gap-2 text-sm leading-snug text-[#8fb0d6]"><MapPin className="mt-0.5 size-4 shrink-0 text-cyan-300" aria-hidden /><span><span className="font-medium text-[#d7e8ff]">{whereLabel}. </span>{where[sel]}</span></p>
                <ul className="divide-y divide-cyan-400/15 overflow-hidden rounded-lg border border-cyan-400/20">
                  {findings.filter((f) => f.region === sel).map((f) => {
                    const Icon = KIND_ICON[f.kind];
                    return (
                      <li key={f.id}>
                        <Link href={f.href} className="flex items-start gap-3 px-3 py-2.5 transition-colors hover:bg-cyan-400/10 focus-visible:bg-cyan-400/10 focus-visible:outline-none">
                          <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md" style={{ color: HEX[f.level], background: `${HEX[f.level]}1f` }}><Icon className="size-4" aria-hidden /></span>
                          <span className="min-w-0 flex-1">
                            <span className="block text-sm font-medium leading-snug text-white">{f.label}</span>
                            {f.sub && <span className="mt-0.5 block text-xs leading-snug text-[#8fb0d6]">{f.sub}</span>}
                          </span>
                          <span className="mt-1 inline-flex shrink-0 items-center gap-1 text-xs text-cyan-300">{openLabel}<ArrowRight className="size-3.5" aria-hidden /></span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </>
        )}
      </div>

      <div className="relative order-1 mx-auto w-full max-w-[760px]">
        <div role="group" aria-label={label} className="relative mx-auto aspect-[300/680] w-full max-w-[250px] overflow-hidden sm:aspect-[640/680] sm:max-w-none sm:overflow-visible">
          <svg viewBox={`0 0 ${W} ${H}`} className="absolute left-1/2 top-0 h-full w-[213.3%] -translate-x-1/2 overflow-visible sm:inset-0 sm:left-0 sm:size-full sm:translate-x-0">
            <defs>
              <linearGradient id="hb-fade" x1="0" y1={TORSO.y} x2="0" y2={TORSO.y + TORSO.h} gradientUnits="userSpaceOnUse"><stop offset="0" stopColor="#fff" /><stop offset="0.86" stopColor="#fff" /><stop offset="1" stopColor="#000" /></linearGradient>
              <linearGradient id="hb-legfade" x1="0" y1="326" x2="0" y2="380" gradientUnits="userSpaceOnUse"><stop offset="0" stopColor="#000" /><stop offset="1" stopColor="#fff" /></linearGradient>
              <mask id="hb-torso" maskUnits="userSpaceOnUse" x="0" y="0" width="300" height="660"><rect x={TORSO.x} y={TORSO.y} width={TORSO.w} height={TORSO.h} fill="url(#hb-fade)" /></mask>
              <mask id="hb-legs" maskUnits="userSpaceOnUse" x="0" y="0" width="300" height="660"><rect x="0" y="326" width="300" height="334" fill="url(#hb-legfade)" /></mask>
              <mask id="hb-shape" maskUnits="userSpaceOnUse" x="-30" y="0" width="360" height="660" style={{ maskType: "alpha" }}>
                {layer === "skeleton" ? <image href={SKEL.src} x={SKEL.x} y={SKEL.y} width={SKEL.w} height={SKEL.h} /> : <><image href={TORSO.src} x={TORSO.x} y={TORSO.y} width={TORSO.w} height={TORSO.h} mask="url(#hb-torso)" /><path d={LEGS} mask="url(#hb-legs)" fill="#fff" /></>}
              </mask>
              <linearGradient id="hb-beam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#22d3ee" stopOpacity="0" /><stop offset="1" stopColor="#67e8f9" stopOpacity="0.55" /></linearGradient>
              <radialGradient id="hb-pad" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stopColor="#22d3ee" stopOpacity="0.35" /><stop offset="1" stopColor="#22d3ee" stopOpacity="0" /></radialGradient>
              <filter id="hb-glow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
              <filter id="hb-soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="1.6" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
            </defs>

            <g aria-hidden fill="none" stroke="#38bdf8">
              <circle cx="320" cy="230" r="172" strokeOpacity="0.14" /><circle cx="320" cy="230" r="212" strokeOpacity="0.1" strokeDasharray="2 6" />
              <g className="holo-spin"><circle cx="320" cy="230" r="192" strokeOpacity="0.35" strokeDasharray="30 14 4 14" /></g>
              <ellipse cx="320" cy="652" rx="150" ry="20" fill="url(#hb-pad)" stroke="none" />
              <ellipse cx="320" cy="652" rx="130" ry="15" strokeOpacity="0.7" /><ellipse cx="320" cy="652" rx="104" ry="11" strokeOpacity="0.45" /><ellipse cx="320" cy="652" rx="150" ry="19" strokeOpacity="0.2" strokeDasharray="3 5" />
            </g>

            <g transform={`translate(${OX} ${OY})`}>
              <g aria-hidden style={{ filter: "drop-shadow(0 0 5px rgba(56,189,248,.55))" }}>
                {layer === "skeleton" ? <image href={SKEL.src} x={SKEL.x} y={SKEL.y} width={SKEL.w} height={SKEL.h} /> : (
                  <>
                    <image href={TORSO.src} x={TORSO.x} y={TORSO.y} width={TORSO.w} height={TORSO.h} mask="url(#hb-torso)" />
                    <g mask="url(#hb-legs)"><Legs /></g>
                  </>
                )}
              </g>
              <g aria-hidden mask="url(#hb-shape)"><rect x="-30" y="0" width="360" height="660" fill="url(#hb-lines)" /></g>
              {shown.map((r) => {
                const lv = levelOf(r);
                if (!lv) return layer === "skeleton" || SKELETAL.has(r) ? null : <g key={r} aria-hidden fill="#38bdf8" fillOpacity={0.06} stroke="#7dd3fc" strokeOpacity={0.35} strokeWidth={0.8}>{SHAPES[r]}</g>;
                const on = sel === r;
                const style: CSSProperties = { color: HEX[lv] };
                return (
                  <g key={r} role="button" tabIndex={0} aria-label={`${names[r]}: ${levelNames[lv]}`} aria-pressed={on} onClick={() => pick(r)} onKeyDown={press(r)} style={style}
                    className="cursor-pointer outline-none transition-[fill-opacity] duration-200 hover:[fill-opacity:0.75] focus-visible:stroke-white"
                    fill="currentColor" fillOpacity={r === "abdomen" ? (on ? 0.3 : 0.12) : on ? 0.5 : lv === "high" ? 0.3 : 0.24} stroke="currentColor" strokeWidth={on ? 2.2 : 1.4} filter="url(#hb-glow)">
                    <title>{`${names[r]} · ${levelNames[lv]}`}</title>
                    {lv === "high" && <g className="animate-pulse motion-reduce:animate-none" fill="none" strokeWidth={6} strokeOpacity={0.3}>{shapeOf(r)}</g>}
                    {shapeOf(r)}
                    <g fill="transparent" stroke="transparent" strokeWidth={14} pointerEvents="all">{shapeOf(r)}</g>
                  </g>
                );
              })}
              <g aria-hidden mask="url(#hb-shape)"><g className="holo-scan"><rect x="-6" y="-60" width="312" height="60" fill="url(#hb-beam)" /><rect x="-6" y="-1.5" width="312" height="3" fill="#a5f3fc" opacity="0.95" /></g></g>
            </g>

            <g aria-hidden fill="none" strokeWidth="1.2" className="max-sm:hidden">
              {callouts.map((c) => {
                const lv = levelOf(c.r)!, edge = c.side === "L" ? EDGE_L : EDGE_R, bend = c.side === "L" ? EDGE_L + 26 : EDGE_R - 26;
                return (
                  <g key={c.r} stroke={HEX[lv]} strokeOpacity={sel === c.r ? 1 : 0.6}>
                    <path d={`M${c.ax} ${c.ay} L${bend} ${c.ly} H${edge}`} />
                    <circle cx={c.ax} cy={c.ay} r="3" fill={HEX[lv]} stroke="none" /><circle cx={c.ax} cy={c.ay} r="7" strokeOpacity="0.5" />
                  </g>
                );
              })}
            </g>
          </svg>

          {callouts.map((c) => {
            const lv = levelOf(c.r)!, on = sel === c.r;
            return (
              <button key={c.r} type="button" onClick={() => pick(c.r)} aria-pressed={on}
                style={{ top: `${(c.ly / H) * 100}%`, [c.side === "L" ? "right" : "left"]: `${c.side === "L" ? ((W - EDGE_L) / W) * 100 : (EDGE_R / W) * 100}%`, borderColor: `${HEX[lv]}${on ? "ff" : "80"}`, boxShadow: on ? `0 0 14px ${HEX[lv]}66` : undefined }}
                className={`absolute w-max max-w-[29%] -translate-y-1/2 max-sm:hidden rounded-md border px-1.5 py-0.5 text-[10px] leading-tight backdrop-blur-sm transition-colors sm:px-2 sm:py-1 sm:text-xs ${c.side === "L" ? "text-right" : "text-left"} ${on ? "bg-cyan-400/20 text-white" : "bg-[#06142e]/75 text-[#d7e8ff] hover:bg-cyan-400/10"}`}>
                <span className="block font-medium">{names[c.r]}</span>
                <span className="block text-[9px] sm:text-[10px]" style={{ color: HEX[lv] }}>{levelNames[lv]}</span>
              </button>
            );
          })}

          <div className="absolute left-0 top-0 inline-flex rounded-lg border border-cyan-400/30 bg-[#06142e]/70 p-0.5 text-xs backdrop-blur-sm" role="group">
            {(["organs", "skeleton"] as const).map((k) => (
              <button key={k} type="button" aria-pressed={layer === k} onClick={() => setLayer(k)}
                className={`rounded-md px-2.5 py-1 transition-colors ${layer === k ? "bg-cyan-400/25 text-white" : "text-[#8fb0d6] hover:text-white"}`}>{layerNames[k]}</button>
            ))}
          </div>
        </div>
      </div>

      <div className="order-3 min-w-0 lg:col-span-2">{side}</div>
    </div>
  );
}
