"use client";
import { useState } from "react";
import { fmt } from "@/lib/hand";
import { Recommendation } from "@/lib/types";
import { RangeGrid } from "./RangeGrid";

const VERB: Record<string, string> = { fold: "Fold", check: "Check", call: "Call", bet: "Bet", raise: "Raise", allin: "All-in" };
const CONF: Record<string, string> = {
  high: "bg-emerald-600 text-white",
  medium: "bg-amber-500 text-black",
  low: "bg-rose-600 text-white",
};
const pct = (x: number | null | undefined) => (x == null ? "–" : `${Math.round(x * 100)}%`);

export function ResultCard({ rec, bb, sng }: { rec: Recommendation; bb: number; sng: boolean }) {
  const [open, setOpen] = useState(true);
  const [villain, setVillain] = useState(0);
  const v = rec.villains[villain] ?? rec.villains[0];
  const size =
    rec.size_bb != null && rec.action !== "fold" && rec.action !== "check"
      ? ` ${fmt(rec.size_bb)} BB${rec.action === "bet" && rec.size_pct_pot ? ` — ${rec.size_pct_pot}% pot` : ""}`
      : "";
  return (
    <div className="panel space-y-3" data-testid="result">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-3xl font-black tracking-tight" data-testid="result-action">
            {VERB[rec.action]}
            {size}
          </div>
          <div className="text-sm text-slate-500">
            {rec.hand_description} · {rec.mode.replace("_", " ")}
            {rec.size_chips != null && rec.action !== "fold" && rec.action !== "check" ? ` · ${fmt(rec.size_chips, 0)} chips` : ""}
          </div>
        </div>
        <span className={`rounded-full px-2 py-0.5 text-xs font-bold uppercase ${CONF[rec.confidence]}`} data-testid="confidence">
          {rec.confidence}
        </span>
      </div>

      {rec.alternatives.length > 0 && (
        <div className="text-sm" data-testid="mixed">
          Mixed:{" "}
          {rec.alternatives.map((a) => `${VERB[a.action]}${a.size_bb && a.action !== "call" ? ` ${fmt(a.size_bb)} BB` : ""} ${Math.round(a.frequency * 100)}%`).join(", ")}
        </div>
      )}

      <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <Num label="Equity" value={pct(rec.equity)} />
        <Num label="Pot odds" value={rec.pot_odds == null ? "–" : `${fmt(rec.pot_odds)} : 1`} />
        <Num label="Needed" value={rec.pot_odds == null ? "–" : pct(rec.required_equity)} />
        <Num label="SPR" value={fmt(rec.spr)} />
        {sng && rec.icm && <Num label="Bubble factor" value={String(rec.icm.bubble_factor ?? "–")} />}
        {sng && rec.icm?.icm_required_equity != null && <Num label="ICM needed" value={pct(Number(rec.icm.icm_required_equity))} />}
      </dl>

      <table className="w-full text-sm" data-testid="options">
        <thead className="label text-left">
          <tr><th>Option</th><th className="text-right">EV (BB)</th>{sng && <th className="text-right">$EV</th>}<th className="text-right">Fold eq.</th></tr>
        </thead>
        <tbody>
          {rec.options.map((o) => (
            <tr key={o.id} className={o.id === rec.option_id ? "font-bold text-emerald-600 dark:text-emerald-400" : ""}>
              <td>{VERB[o.action]}{o.size_bb != null && o.action !== "fold" ? ` ${fmt(o.size_bb)}` : ""}</td>
              <td className="text-right">{fmt(o.ev_bb, 2)}</td>
              {sng && <td className="text-right">{fmt(o.ev_dollars, 2)}</td>}
              <td className="text-right">{pct(o.fold_equity)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div>
        <button className="label" onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} Why</button>
        {open && (
          <div className="mt-1 space-y-1 text-sm" data-testid="explanation">
            <p>{rec.explanation}</p>
            <p className="text-xs text-slate-500">
              {rec.explanation_source === "llm" ? "Explained by Claude from engine numbers." : "Engine explanation."}
              {rec.validation.overridden && " Claude disagreed with the engine; engine choice kept."}
              {rec.validation.numbers_rejected.length > 0 && " Claude's text was rejected for unsupported numbers."}
            </p>
            {rec.notes.map((n) => <p key={n} className="text-xs text-slate-500">• {n}</p>)}
          </div>
        )}
      </div>

      {v && (
        <div>
          <div className="mb-1 flex items-center gap-2">
            <span className="label">Villain range</span>
            {rec.villains.length > 1 && (
              <select className="rounded bg-transparent text-xs" value={villain} onChange={(e) => setVillain(Number(e.target.value))}>
                {rec.villains.map((x, i) => <option key={x.position} value={i}>{x.position}</option>)}
              </select>
            )}
            <span className="text-xs text-slate-500">{v.position} · {v.pct_of_hands}% · {v.source}</span>
          </div>
          <RangeGrid grid={v.grid} />
        </div>
      )}
      <div className="text-right text-[10px] text-slate-500">
        engine {fmt(rec.timing_ms.engine, 0)} ms · llm {fmt(rec.timing_ms.llm, 0)} ms · 1 BB = {bb}
      </div>
    </div>
  );
}

function Num({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-100 p-2 dark:bg-slate-800">
      <dt className="label">{label}</dt>
      <dd className="text-lg font-semibold">{value}</dd>
    </div>
  );
}
