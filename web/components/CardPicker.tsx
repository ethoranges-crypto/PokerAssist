"use client";
import { RANKS, SUITS } from "@/lib/hand";
import { suitColor, suitSymbol } from "./Card";

/** 4x13 grid; cards already used elsewhere are greyed out. */
export function CardPicker({ used, onPick }: { used: Set<string>; onPick: (c: string) => void }) {
  return (
    <div className="grid grid-cols-13 gap-0.5" style={{ gridTemplateColumns: "repeat(13, minmax(0, 1fr))" }} data-testid="card-picker">
      {SUITS.map((s) =>
        RANKS.map((r) => {
          const c = r + s;
          const taken = used.has(c);
          return (
            <button
              key={c}
              data-testid={`card-${c}`}
              disabled={taken}
              onClick={() => onPick(c)}
              className={`rounded py-1 text-xs font-bold sm:text-sm ${taken ? "bg-slate-200 text-slate-400 dark:bg-slate-800 dark:text-slate-600" : `bg-white hover:bg-emerald-100 dark:bg-slate-800 dark:hover:bg-slate-700 ${suitColor(s)}`}`}
            >
              {r}
              {suitSymbol(s)}
            </button>
          );
        }),
      )}
    </div>
  );
}
