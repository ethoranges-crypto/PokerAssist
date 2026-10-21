"use client";
import { useEffect, useState } from "react";
import { Derived, fmt } from "@/lib/hand";
import { ActionKind, HandState } from "@/lib/types";

/** Quick buttons for whoever is next to act; the amount is the "raise to" total. */
export function ActionBar({ hand, d, onAction, onFoldToHero }: {
  hand: HandState;
  d: Derived;
  onAction: (pos: string, action: ActionKind, amount?: number) => void;
  onFoldToHero: () => void;
}) {
  const who = d.nextToAct;
  const maxIn = Math.max(...Object.values(d.inStreet));
  const facing = who ? maxIn - (d.inStreet[who] ?? 0) : 0;
  const pre = hand.street === "preflop";
  const sizes: [string, number][] = pre
    ? [["2.5x", 2.5 * Math.max(maxIn, hand.bb)], ["3x", 3 * Math.max(maxIn, hand.bb)], ["4x", 4 * Math.max(maxIn, hand.bb)]]
    : maxIn === 0
      ? [["⅓", d.pot / 3], ["½", d.pot / 2], ["¾", (d.pot * 3) / 4], ["pot", d.pot]]
      : [["2.5x", 2.5 * maxIn], ["3.5x", 3.5 * maxIn]];
  const [amount, setAmount] = useState<number>(0);
  useEffect(() => setAmount(Math.round(sizes[0][1])), [who, hand.street, hand.actions.length]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!who) return <div className="text-sm text-slate-500">Betting closed on the {hand.street}. Pick the next street tab.</div>;
  const heroTurn = who === hand.hero;
  const aggressive = maxIn === 0 || (pre && maxIn <= hand.bb && facing <= hand.bb) ? (pre ? "raise" : "bet") : "raise";
  return (
    <div className="space-y-1">
    {heroTurn && (
      <div className="text-sm font-medium text-amber-600 dark:text-amber-300" data-testid="hero-to-act">
        Hero ({hand.hero}) to act{d.toCall > 0 ? ` – ${fmt(d.toCall, 0)} to call` : ""}. Press Analyze, or record hero's action to continue the hand.
      </div>
    )}
    <div className="flex flex-wrap items-center gap-1.5" data-testid="action-bar">
      <span className="mr-1 text-sm font-semibold" data-testid="next-to-act">{who}:</span>
      <button className="btn-ghost" data-testid="act-fold" onClick={() => onAction(who, "fold")}>Fold</button>
      <button className="btn-ghost" data-testid="act-call" onClick={() => onAction(who, facing > 0 ? "call" : "check")}>
        {facing > 0 ? `Call ${fmt(facing, 0)}` : "Check"}
      </button>
      <input className="input w-20" type="number" value={amount} aria-label="amount" data-testid="act-amount" onChange={(e) => setAmount(Number(e.target.value))} />
      {sizes.map(([label, v]) => (
        <button key={label} className="btn-ghost px-2" onClick={() => setAmount(Math.round(v))}>{label}</button>
      ))}
      <button className="btn-ghost" data-testid="act-raise" onClick={() => onAction(who, aggressive as ActionKind, amount)}>
        {aggressive === "bet" ? "Bet" : "Raise to"} {fmt(amount, 0)}
      </button>
      <button className="btn-ghost" data-testid="act-allin" onClick={() => onAction(who, "allin")}>All-in</button>
      {hand.street === "preflop" && !heroTurn && (
        <button className="btn-ghost" data-testid="fold-to-hero" onClick={onFoldToHero}>Fold to hero</button>
      )}
    </div>
    </div>
  );
}
