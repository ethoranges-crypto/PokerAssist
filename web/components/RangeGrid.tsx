import { RANKS } from "@/lib/hand";

/** 13x13 villain range: pairs on the diagonal, suited above, offsuit below. */
export function RangeGrid({ grid }: { grid: number[][] }) {
  return (
    <div className="grid gap-px text-[9px] sm:text-[10px]" style={{ gridTemplateColumns: "repeat(13, minmax(0, 1fr))" }} data-testid="range-grid">
      {grid.flatMap((row, i) =>
        row.map((w, j) => {
          const label = i === j ? RANKS[i] + RANKS[j] : i < j ? RANKS[i] + RANKS[j] + "s" : RANKS[j] + RANKS[i] + "o";
          return (
            <div
              key={label}
              title={`${label}: ${Math.round(w * 100)}%`}
              className="flex aspect-square items-center justify-center rounded-sm text-slate-900"
              style={{ background: w > 0 ? `rgba(16, 185, 129, ${0.15 + 0.85 * w})` : "rgba(100, 116, 139, 0.15)" }}
            >
              <span className={w > 0.4 ? "text-white" : "text-slate-500"}>{label}</span>
            </div>
          );
        }),
      )}
    </div>
  );
}
