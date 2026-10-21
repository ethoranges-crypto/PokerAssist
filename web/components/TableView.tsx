"use client";
import { Derived, POSITIONS, fmt } from "@/lib/hand";
import { HandState, VillainType } from "@/lib/types";

const TYPES: VillainType[] = ["unknown", "tight", "loose", "passive", "aggressive"];

/** Oval table; seats are laid out clockwise with the hero at the bottom. */
export function TableView({ hand, d, onHero, onStack, onType }: {
  hand: HandState;
  d: Derived;
  onHero: (p: string) => void;
  onStack: (p: string, v: number) => void;
  onType: (p: string, t: VillainType) => void;
}) {
  const seats = POSITIONS[hand.players];
  const heroIdx = seats.indexOf(hand.hero);
  return (
    <div className="relative mx-auto aspect-[2/1] w-full max-w-2xl" data-testid="table">
      <div className="absolute inset-[14%] rounded-[50%] border-4 border-emerald-900 bg-emerald-800/70 shadow-inner" />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="rounded-lg bg-black/40 px-3 py-1 text-center text-sm text-white" data-testid="pot">
          Pot {fmt(d.pot, 0)} <span className="opacity-70">({fmt(d.pot / hand.bb)} BB)</span>
          {d.toCall > 0 && <div className="text-xs text-amber-300">To call {fmt(d.toCall, 0)}</div>}
        </div>
      </div>
      {seats.map((p, i) => {
        const k = (i - heroIdx + seats.length) % seats.length;
        const angle = Math.PI / 2 + (2 * Math.PI * k) / seats.length;
        const x = 50 + 44 * Math.cos(angle);
        const y = 50 + 40 * Math.sin(angle);
        const isHero = p === hand.hero;
        const folded = d.folded.has(p);
        const next = d.nextToAct === p;
        return (
          <div
            key={p}
            className={`absolute w-24 -translate-x-1/2 -translate-y-1/2 rounded-lg border p-1 text-center text-xs shadow sm:w-28 ${isHero ? "border-amber-400 bg-amber-100 dark:bg-amber-900/60" : "border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900"} ${folded ? "opacity-40" : ""} ${next ? "ring-2 ring-sky-400" : ""}`}
            style={{ left: `${x}%`, top: `${y}%` }}
            data-testid={`seat-${p}`}
          >
            <button className="w-full font-bold" onClick={() => onHero(p)} title="Set as hero">
              {p} {isHero && "★"}
            </button>
            <input
              className="input mt-0.5 py-0.5 text-center text-xs"
              type="number"
              aria-label={`${p} stack`}
              value={hand.stacks[p] ?? 0}
              onChange={(e) => onStack(p, Number(e.target.value))}
            />
            <div className="mt-0.5 text-[10px] text-slate-500">
              behind {fmt(d.behind[p], 0)}
              {d.inStreet[p] > 0 && <span className="text-amber-600 dark:text-amber-300"> · in {fmt(d.inStreet[p], 0)}</span>}
            </div>
            {!isHero && (
              <select
                className="mt-0.5 w-full rounded bg-transparent text-[10px]"
                value={hand.types[p] ?? "unknown"}
                aria-label={`${p} type`}
                onChange={(e) => onType(p, e.target.value as VillainType)}
              >
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            )}
          </div>
        );
      })}
    </div>
  );
}
