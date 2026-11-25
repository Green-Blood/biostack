import type { ReactNode } from "react";
import type { Region } from "./body-map-model";

// The figure is two public-domain anatomical illustrations (Wikimedia Commons: "Adult male diagram template" and
// "Human skeleton front"), recoloured into a hologram sprite. Organ hotspots are drawn over them in a 300x660 box.
// The body's right side is on the viewer's left (liver, gallbladder).
export const TORSO = { src: "/anatomy/torso.webp", x: 48, y: 10, w: 231, h: 334.2 };
export const SKEL = { src: "/anatomy/skeleton.webp", x: -4, y: 6, w: 335.7, h: 648.3 };

const HALF_LEGS = "M150 326 L212 326 C215 344 216 356 214 366 C214 400 212 424 208 448 C206 462 204 474 202 486 C202 506 206 528 206 548 C206 570 198 592 194 612 C193 624 196 632 202 638 C208 644 214 650 208 654 L172 654 C170 640 171 626 172 612 C174 590 172 566 170 548 C168 524 166 504 166 488 C166 470 164 450 163 430 C160 400 158 372 156 350 C154 346 152 344 150 344";

/** One closed outline from the right half: the half itself, then its mirror image walked backwards. */
function fullPath(d: string): string {
  const toks = d.match(/[MLC]|-?\d+(?:\.\d+)?/g)!;
  let i = 0, start: number[] = [];
  const segs: { t: string; p: number[] }[] = [];
  while (i < toks.length) {
    const c = toks[i++], n = c === "C" ? 6 : 2, p = toks.slice(i, i + n).map(Number);
    i += n;
    if (c === "M") start = p; else segs.push({ t: c, p });
  }
  const pts = [start, ...segs.map((s) => s.p.slice(-2))];
  let out = `M${start[0]} ${start[1]}`;
  for (const s of segs) out += s.t === "L" ? ` L${s.p[0]} ${s.p[1]}` : ` C${s.p.join(" ")}`;
  const end = pts[pts.length - 1];
  out += ` L${300 - end[0]} ${end[1]}`;
  for (let k = segs.length - 1; k >= 0; k--) {
    const s = segs[k], from = pts[k];
    out += s.t === "L" ? ` L${300 - from[0]} ${from[1]}` : ` C${300 - s.p[2]} ${s.p[3]} ${300 - s.p[0]} ${s.p[1]} ${300 - from[0]} ${from[1]}`;
  }
  return `${out}Z`;
}
export const LEGS = fullPath(HALF_LEGS);
const MIRROR = "matrix(-1 0 0 1 300 0)";

const LINE = { fill: "none", strokeLinecap: "round", strokeLinejoin: "round" } as const;
const thin = { ...LINE, strokeWidth: 1, strokeOpacity: 0.8 } as const;

/** Legs below the pelvis, drawn as a hologram outline that dissolves into the torso illustration. */
export const Legs = () => {
  const half = (
    <g {...LINE} stroke="#7dd3fc" strokeOpacity={0.7} strokeWidth={0.9}>
      <path d="M158 352 C176 346 206 350 214 366 C214 396 210 430 204 456 C194 462 180 460 170 452 C162 424 158 388 158 352Z" fill="#38bdf8" fillOpacity={0.12} />
      <path d="M178 352 V440 M208 360 C196 392 184 424 175 452" />
      <ellipse cx="185" cy="466" rx="8" ry="10" />
      <path d="M170 484 C182 478 200 484 205 500 C207 540 202 580 195 606 C187 608 179 608 174 598 C171 562 169 520 170 484Z" fill="#38bdf8" fillOpacity={0.12} />
      <path d="M192 490 C202 508 205 540 198 580 M176 500 C178 540 178 572 180 598" />
      <path d="M180 653 V641 M188 654 V640 M196 653 V640 M203 650 V638" />
    </g>
  );
  return (
    <g aria-hidden>
      <path d={LEGS} fill="#38bdf8" fillOpacity={0.1} stroke="#a5f3fc" strokeOpacity={0.9} strokeWidth={1.2} strokeLinejoin="round" />
      {half}<g transform={MIRROR}>{half}</g>
    </g>
  );
};

// --- Hotspots -------------------------------------------------------------------------------------------------
const joint = (cx: number, cy: number, r: number) => <><circle cx={cx} cy={cy} r={r} /><circle cx={cx} cy={cy} r={r * 0.5} fill="none" strokeOpacity={0.6} /></>;
const vertebrae = (y0: number, step: number, n: number, x = 146) => Array.from({ length: n }, (_, i) => <rect key={i} x={x} y={y0 + i * step} width="8" height="6" rx="2.5" />);

/** Organ layer: shapes sit on the torso illustration (and the legs below it). */
export const SHAPES: Record<Region, ReactNode> = {
  abdomen: <><path d="M106 262 C100 286 104 312 120 328 C136 340 164 340 182 328 C198 312 202 286 196 262 C176 270 126 270 106 262Z" strokeDasharray="3 2.5" />
    <path d="M114 284 C130 290 172 290 190 284" {...thin} strokeDasharray="2 3" /></>,
  spine: <>{vertebrae(128, 9.6, 21, 148)}</>,
  kidneys: <>
    <path d="M127 256 C119 258 116 272 119 280 C124 284 132 278 133 268 C134 262 131 256 127 256Z" />
    <path d="M173 256 C181 258 184 272 181 280 C176 284 168 278 167 268 C166 262 169 256 173 256Z" />
  </>,
  lungs: <>
    <path d="M158 150 C140 144 122 158 117 186 C113 212 118 230 130 236 C146 238 158 232 160 220 C158 200 160 170 158 150Z" />
    <path d="M163 152 C180 146 197 166 197 196 C197 212 190 224 178 226 C168 224 163 214 163 198Z" />
    <path d="M153 130 V160 M153 160 C147 166 139 172 131 182 M153 160 C159 166 169 172 179 182" {...thin} />
  </>,
  liver: <><path d="M114 226 C118 214 136 212 152 216 C160 220 162 232 156 246 C148 258 128 262 120 254 C112 246 110 236 114 226Z" />
    <path d="M150 218 C150 230 146 242 138 252" {...thin} /></>,
  pancreas: <path d="M152 252 C165 246 180 244 192 240 C196 244 192 250 182 254 C170 258 158 258 152 256Z" />,
  intestine: <><path d="M112 272 C108 292 112 316 128 322 C145 326 156 322 172 322 C190 318 204 300 202 276 C198 262 180 262 150 264 C128 264 116 264 112 272Z" />
    <path d="M122 280 H180 M120 296 H184 M126 310 H176" {...thin} strokeDasharray="3 2" /></>,
  stomach: <path d="M154 234 C172 228 194 238 196 250 C195 262 178 266 164 262 C154 258 150 246 154 234Z" />,
  spleen: <path d="M184 212 C194 214 200 226 196 236 C190 238 182 230 180 222Z" />,
  bladder: <path d="M138 323 C142 318 158 318 164 323 C168 331 160 339 151 339 C142 339 134 331 138 323Z" />,
  gallbladder: <path d="M133 245 C128 247 128 257 133 260 C138 259 139 250 133 245Z" />,
  heart: <path d="M150 170 C158 160 178 162 184 176 C188 192 180 208 168 214 C156 214 146 200 144 186 C143 178 146 173 150 170Z" />,
  thyroid: <path d="M143 118 C138 120 137 130 142 134 C147 134 150 130 150 126 C151 130 154 134 159 134 C164 130 163 120 158 118 C154 120 151 122 150 124 C149 122 146 120 143 118Z" />,
  brain: <><path d="M153 22 C173 20 183 32 182 46 C180 58 168 62 153 61 C138 62 126 58 124 46 C123 32 133 20 153 22Z" /><path d="M153 24 V60" {...thin} /></>,
  eyes: <><ellipse cx="142" cy="61" rx="6" ry="3.2" /><ellipse cx="164" cy="61" rx="6" ry="3.2" /></>,
  shoulders: <>{joint(88, 172, 10)}{joint(224, 174, 10)}</>,
  elbows: <>{joint(82, 271, 8)}{joint(239, 274, 8)}</>,
  hips: <>{joint(112, 354, 11)}{joint(190, 354, 11)}</>,
  knees: <>{joint(116, 463, 11)}{joint(184, 463, 11)}</>,
  ankles: <>{joint(121, 600, 7)}{joint(179, 600, 7)}</>,
};

/** Skeleton layer: joints and the spine sit on the skeleton illustration. */
export const SKEL_SHAPES: Partial<Record<Region, ReactNode>> = {
  spine: <>{vertebrae(112, 9.6, 19)}</>,
  shoulders: <>{joint(86, 134, 10)}{joint(218, 140, 10)}</>,
  elbows: <>{joint(60, 240, 8)}{joint(237, 240, 8)}</>,
  hips: <>{joint(99, 314, 11)}{joint(201, 313, 11)}</>,
  knees: <>{joint(130, 458, 11)}{joint(170, 458, 11)}</>,
  ankles: <>{joint(134, 609, 7)}{joint(165, 609, 7)}</>,
};

export const SKELETAL = new Set<Region>(["spine", "shoulders", "elbows", "hips", "knees", "ankles"]);
export const ORDER: Region[] = ["abdomen", "spine", "kidneys", "lungs", "liver", "pancreas", "intestine", "stomach", "spleen", "bladder", "gallbladder", "heart", "thyroid", "brain", "eyes", "shoulders", "elbows", "hips", "knees", "ankles"];

type Anchors = Record<Region, { x: number; y: number; side: "L" | "R" }>;
// Where a callout line touches the body, and which side its label sits on.
export const ANCHOR: Anchors = {
  brain: { x: 168, y: 34, side: "R" }, eyes: { x: 140, y: 61, side: "L" }, thyroid: { x: 160, y: 126, side: "R" }, shoulders: { x: 80, y: 172, side: "L" },
  lungs: { x: 124, y: 184, side: "L" }, heart: { x: 176, y: 186, side: "R" }, spine: { x: 152, y: 150, side: "R" }, liver: { x: 122, y: 232, side: "L" },
  spleen: { x: 194, y: 224, side: "R" }, stomach: { x: 184, y: 248, side: "R" }, elbows: { x: 244, y: 274, side: "R" }, gallbladder: { x: 130, y: 252, side: "L" },
  pancreas: { x: 178, y: 250, side: "R" }, kidneys: { x: 120, y: 270, side: "L" }, abdomen: { x: 196, y: 300, side: "R" }, intestine: { x: 150, y: 296, side: "R" },
  bladder: { x: 156, y: 330, side: "R" }, hips: { x: 104, y: 354, side: "L" }, knees: { x: 192, y: 463, side: "R" }, ankles: { x: 114, y: 600, side: "L" },
};
export const SKEL_ANCHOR: Anchors = {
  ...ANCHOR,
  spine: { x: 152, y: 200, side: "R" }, shoulders: { x: 78, y: 134, side: "L" }, elbows: { x: 244, y: 240, side: "R" },
  hips: { x: 92, y: 314, side: "L" }, knees: { x: 178, y: 458, side: "R" }, ankles: { x: 128, y: 609, side: "L" },
};
