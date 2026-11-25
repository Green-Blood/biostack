export type Verdict = "low" | "ok" | "warn" | "high" | null;
export const VERDICT_HEX: Record<NonNullable<Verdict>, string> = { ok: "#34d399", low: "#ffb020", warn: "#ffb020", high: "#ff4d6d" };

const R = 34, C = 2 * Math.PI * R;

/** A circular readout: the arc is the value on a 0..max scale, the faint green arc behind it is the standard range. */
export function RingGauge({ value, text, unit, max, range, label, verdict, verdictLabel }:
  { value: number; text: string; unit: string; max: number; range: [number, number] | null; label: string; verdict: Verdict; verdictLabel: string | null }) {
  const color = verdict ? VERDICT_HEX[verdict] : "#38bdf8";
  const v = Math.max(0, Math.min(1, value / max));
  return (
    <div className="flex flex-col items-center text-center">
      <svg viewBox="0 0 84 84" className="size-[76px]" role="img" aria-label={`${label}: ${text} ${unit}${verdictLabel ? `, ${verdictLabel}` : ""}`}>
        <g transform="rotate(-90 42 42)" fill="none" strokeLinecap="round">
          <circle cx="42" cy="42" r={R} stroke="#38bdf8" strokeOpacity="0.14" strokeWidth="7" />
          {range && <circle cx="42" cy="42" r={R} stroke="#34d399" strokeOpacity="0.35" strokeWidth="7" strokeLinecap="butt" strokeDasharray={`${((range[1] - range[0]) / max) * C} ${C}`} strokeDashoffset={-(range[0] / max) * C} />}
          <circle cx="42" cy="42" r={R} stroke={color} strokeWidth="3.5" strokeDasharray={`${v * C} ${C}`} style={{ filter: `drop-shadow(0 0 3px ${color})` }} />
        </g>
        <text x="42" y="43" textAnchor="middle" fontSize="16" fontWeight="600" fill="#fff" className="tnum">{text}</text>
        <text x="42" y="56" textAnchor="middle" fontSize="8.5" fill="#8fb0d6">{unit}</text>
      </svg>
      <span className="mt-1 text-[11px] leading-tight text-[#b9d4f2]">{label}</span>
      {verdictLabel && <span className="text-[11px] font-medium leading-tight" style={{ color }}>{verdictLabel}</span>}
    </div>
  );
}
