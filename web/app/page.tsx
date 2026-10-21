"use client";

import { useEffect, useMemo, useState } from "react";
import { ActionBar } from "@/components/ActionBar";
import { CardFace } from "@/components/Card";
import { CardPicker } from "@/components/CardPicker";
import { ResultCard } from "@/components/ResultCard";
import { TableView } from "@/components/TableView";
import { POSITIONS, addAction, defaultHand, derive, foldToHero, fmt, toRequest, usedCards, withPlayers } from "@/lib/hand";
import { ActionKind, BOARD_COUNT, HandState, HandSummary, Recommendation, STREETS, Street } from "@/lib/types";

type Slot = { kind: "hero" | "board"; index: number };
const PRESET_KEY = "pokerassist.presets";

interface Preset {
  name: string;
  format: HandState["format"];
  sb: number;
  bb: number;
  ante: number;
  players: number;
  stack: number;
  payouts: number[];
}

const BUILTIN: Preset[] = [
  { name: "6-max cash 100BB", format: "cash", sb: 50, bb: 100, ante: 0, players: 6, stack: 10000, payouts: [] },
  { name: "9-max SnG, 1500 start, 50/30/20", format: "sng", sb: 10, bb: 20, ante: 0, players: 9, stack: 1500, payouts: [50, 30, 20] },
];

function loadPresets(): Preset[] {
  try {
    return JSON.parse(localStorage.getItem(PRESET_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export default function Page() {
  const [hand, setHand] = useState<HandState>(() => defaultHand());
  const [slot, setSlot] = useState<Slot | null>({ kind: "hero", index: 0 });
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<HandSummary[] | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const d = useMemo(() => derive(hand), [hand]);
  const used = usedCards(hand);

  useEffect(() => setPresets(loadPresets()), []);

  const update = (patch: Partial<HandState>) => {
    setHand((h) => ({ ...h, ...patch }));
    setRec(null);
  };

  const pick = (c: string) => {
    if (!slot) return;
    setHand((h) => {
      const next = { ...h, heroHand: [...h.heroHand], board: [...h.board] };
      (slot.kind === "hero" ? next.heroHand : next.board)[slot.index] = c;
      return next;
    });
    setRec(null);
    // advance to the next empty slot that is visible on this street
    const order: Slot[] = [
      { kind: "hero", index: 0 },
      { kind: "hero", index: 1 },
      ...[0, 1, 2, 3, 4].map((i) => ({ kind: "board" as const, index: i })),
    ];
    const filled = (s: Slot) =>
      (s.kind === "hero" && s.index === slot.index && slot.kind === "hero") ||
      (s.kind === "board" && s.index === slot.index && slot.kind === "board") ||
      (s.kind === "hero" ? hand.heroHand[s.index] : hand.board[s.index]);
    const visible = (s: Slot) => s.kind === "hero" || s.index < BOARD_COUNT[hand.street];
    setSlot(order.find((s) => visible(s) && !filled(s)) ?? null);
  };

  const setStreet = (street: Street) => {
    update({ street });
    const firstEmpty = hand.board.findIndex((c, i) => !c && i < BOARD_COUNT[street]);
    if (firstEmpty >= 0) setSlot({ kind: "board", index: firstEmpty });
  };

  const onAction = (pos: string, action: ActionKind, amount?: number) => {
    setHand((h) => addAction(h, { position: pos, action, amount: action === "bet" || action === "raise" ? amount : undefined }));
    setRec(null);
  };

  const analyze = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(toRequest(hand)),
      });
      const body = await res.json();
      if (!res.ok) {
        const detail = Array.isArray(body.detail) ? body.detail.map((x: { msg: string }) => x.msg).join("; ") : body.detail;
        throw new Error(String(detail ?? res.statusText).replace(/^Value error, /, ""));
      }
      setRec(body);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const openHistory = async () => {
    const res = await fetch("/api/hands");
    setHistory(res.ok ? await res.json() : []);
  };

  const loadHand = async (id: number) => {
    const res = await fetch(`/api/hands/${id}`);
    if (!res.ok) return;
    const h = await res.json();
    const inp = h.input;
    const seats = POSITIONS[inp.players];
    // Rebuild starting stacks: chips behind + what the action log put in.
    const restored: HandState = {
      ...defaultHand(inp.players),
      format: inp.format,
      sb: inp.small_blind,
      bb: inp.big_blind,
      ante: inp.ante,
      hero: inp.hero_position,
      heroHand: inp.hero_hand,
      board: [...inp.board, null, null, null, null, null].slice(0, 5),
      actions: inp.actions.map((a: { street: Street; position: string; action: ActionKind; amount: number | null }) => ({ ...a, amount: a.amount ?? undefined })),
      street: (["preflop", "", "", "flop", "turn", "river"][inp.board.length] || "preflop") as Street,
      payouts: inp.payouts ?? [50, 30, 20],
      types: Object.fromEntries(inp.seats.map((s: { position: string; villain_type: string }) => [s.position, s.villain_type])),
      stacks: Object.fromEntries(seats.map((p) => [p, 0])),
    };
    const behindNow: Record<string, number> = { [inp.hero_position]: inp.hero_stack };
    for (const s of inp.seats) behindNow[s.position] = s.stack;
    const probe = derive({ ...restored, stacks: Object.fromEntries(seats.map((p) => [p, 1e12])) });
    restored.stacks = Object.fromEntries(seats.map((p) => [p, Math.round(behindNow[p] + (1e12 - probe.behind[p]))]));
    setHand(restored);
    setRec(h.recommendation);
    setHistory(null);
  };

  const applyPreset = (p: Preset) => {
    const base = withPlayers({ ...hand, format: p.format, sb: p.sb, bb: p.bb, ante: p.ante, payouts: p.payouts.length ? p.payouts : hand.payouts }, p.players);
    update({ ...base, stacks: Object.fromEntries(POSITIONS[p.players].map((s) => [s, p.stack])) });
  };

  const savePreset = () => {
    const name = prompt("Preset name?");
    if (!name) return;
    const p: Preset = { name, format: hand.format, sb: hand.sb, bb: hand.bb, ante: hand.ante, players: hand.players, stack: hand.stacks[hand.hero], payouts: hand.payouts };
    const next = [...presets.filter((x) => x.name !== name), p];
    setPresets(next);
    try {
      localStorage.setItem(PRESET_KEY, JSON.stringify(next));
    } catch {
      /* storage unavailable: keep for this session only */
    }
  };

  const reset = () => {
    setHand((h) => ({ ...h, heroHand: [null, null], board: [null, null, null, null, null], actions: [], street: "preflop" }));
    setSlot({ kind: "hero", index: 0 });
    setRec(null);
  };

  const toggleTheme = () => document.documentElement.classList.toggle("dark");
  const ready = hand.heroHand.every(Boolean) && hand.board.slice(0, BOARD_COUNT[hand.street]).every(Boolean);

  return (
    <main className="mx-auto max-w-6xl space-y-3 p-3 sm:p-4">
      <header className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-black">PokerAssist</h1>
        <div className="flex overflow-hidden rounded-md" role="group" aria-label="format">
          {(["cash", "sng"] as const).map((f) => (
            <button key={f} data-testid={`format-${f}`} className={`btn rounded-none ${hand.format === f ? "bg-emerald-600 text-white" : "bg-slate-200 dark:bg-slate-800"}`} onClick={() => update({ format: f })}>
              {f === "cash" ? "Cash" : "Sit & Go"}
            </button>
          ))}
        </div>
        <select className="input !w-auto" aria-label="presets" value="" onChange={(e) => {
          const p = [...BUILTIN, ...presets].find((x) => x.name === e.target.value);
          if (p) applyPreset(p);
        }}>
          <option value="">Presets…</option>
          {[...BUILTIN, ...presets].map((p) => <option key={p.name}>{p.name}</option>)}
        </select>
        <button className="btn-ghost" onClick={savePreset}>Save preset</button>
        <button className="btn-ghost" data-testid="history-open" onClick={openHistory}>History</button>
        <button className="btn-ghost" onClick={toggleTheme} aria-label="toggle theme">◐</button>
      </header>

      <section className="panel grid grid-cols-2 gap-2 sm:grid-cols-7">
        <Field label="Small blind"><input className="input" type="number" value={hand.sb} onChange={(e) => update({ sb: Number(e.target.value) })} /></Field>
        <Field label="Big blind"><input className="input" type="number" value={hand.bb} onChange={(e) => update({ bb: Number(e.target.value) })} /></Field>
        <Field label="Ante"><input className="input" type="number" value={hand.ante} onChange={(e) => update({ ante: Number(e.target.value) })} /></Field>
        <Field label="Players">
          <select className="input" data-testid="players" value={hand.players} onChange={(e) => update(withPlayers(hand, Number(e.target.value)))}>
            {[2, 3, 4, 5, 6, 7, 8, 9].map((n) => <option key={n}>{n}</option>)}
          </select>
        </Field>
        <Field label="Hero stack (BB)">
          <input className="input" type="number" data-testid="hero-stack-bb" value={fmt(hand.stacks[hand.hero] / hand.bb)} onChange={(e) => update({ stacks: { ...hand.stacks, [hand.hero]: Number(e.target.value) * hand.bb } })} />
        </Field>
        <Field label="All stacks">
          <button className="btn-ghost w-full" data-testid="stacks-equal" onClick={() => update({ stacks: Object.fromEntries(POSITIONS[hand.players].map((p) => [p, hand.stacks[hand.hero]])) })}>= hero</button>
        </Field>
        {hand.format === "sng" && (
          <Field label="Payouts">
            <input className="input" data-testid="payouts" defaultValue={hand.payouts.join("/")} onBlur={(e) => update({ payouts: e.target.value.split(/[/,\s]+/).map(Number).filter((x) => x > 0) })} />
          </Field>
        )}
      </section>

      <div className="grid gap-3 lg:grid-cols-[1fr_380px]">
        <div className="space-y-3">
          <TableView
            hand={hand}
            d={d}
            onHero={(p) => update({ hero: p, actions: [] })}
            onStack={(p, v) => update({ stacks: { ...hand.stacks, [p]: v } })}
            onType={(p, t) => update({ types: { ...hand.types, [p]: t } })}
          />

          <section className="panel space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-1">
                <span className="label mr-1">Hero</span>
                {[0, 1].map((i) => (
                  <button key={i} data-testid={`slot-hero-${i}`} className={slot?.kind === "hero" && slot.index === i ? "rounded ring-2 ring-sky-400" : ""} onClick={() => setSlot({ kind: "hero", index: i })}>
                    <CardFace card={hand.heroHand[i]} />
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1">
                <span className="label mr-1">Board</span>
                {[0, 1, 2, 3, 4].map((i) => (
                  <button key={i} data-testid={`slot-board-${i}`} disabled={i >= BOARD_COUNT[hand.street]} className={`${i >= BOARD_COUNT[hand.street] ? "opacity-30" : ""} ${slot?.kind === "board" && slot.index === i ? "rounded ring-2 ring-sky-400" : ""}`} onClick={() => setSlot({ kind: "board", index: i })}>
                    <CardFace card={hand.board[i]} />
                  </button>
                ))}
              </div>
              <button className="btn-ghost ml-auto" onClick={reset}>New hand</button>
            </div>
            <CardPicker used={used} onPick={pick} />
          </section>

          <section className="panel space-y-2">
            <nav className="flex gap-1" aria-label="streets">
              {STREETS.map((s) => (
                <button key={s} data-testid={`street-${s}`} className={`btn capitalize ${hand.street === s ? "bg-sky-600 text-white" : "bg-slate-200 dark:bg-slate-800"}`} onClick={() => setStreet(s)}>
                  {s}
                </button>
              ))}
            </nav>
            <ActionBar hand={hand} d={d} onAction={onAction} onFoldToHero={() => { setHand(foldToHero); setRec(null); }} />
            <ol className="space-y-0.5 text-sm" data-testid="action-log">
              {hand.actions.map((a, i) => (
                <li key={i} className={STREETS.indexOf(a.street) > STREETS.indexOf(hand.street) ? "opacity-40" : ""}>
                  <span className="label mr-1">{a.street}</span>
                  <b>{a.position}</b> {a.action}
                  {a.amount ? ` ${a.amount}` : ""}
                </li>
              ))}
            </ol>
            {hand.actions.length > 0 && (
              <button className="btn-ghost" onClick={() => update({ actions: hand.actions.slice(0, -1) })}>Undo</button>
            )}
          </section>
        </div>

        <aside className="space-y-3">
          <button className="btn-primary w-full py-3 text-lg" data-testid="analyze" disabled={busy || !ready} onClick={analyze}>
            {busy ? "Analyzing…" : ready ? "Analyze" : "Pick hero cards and board"}
          </button>
          {error && <div className="panel border-rose-500 text-sm text-rose-500" data-testid="error">{error}</div>}
          {rec && <ResultCard rec={rec} bb={hand.bb} sng={hand.format === "sng"} />}
        </aside>
      </div>

      {history && (
        <div className="fixed inset-0 z-10 flex justify-end bg-black/40" onClick={() => setHistory(null)}>
          <div className="h-full w-full max-w-md overflow-y-auto bg-white p-3 dark:bg-slate-900" onClick={(e) => e.stopPropagation()} data-testid="history">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="font-bold">Saved hands</h2>
              <button className="btn-ghost" onClick={() => setHistory(null)}>Close</button>
            </div>
            {history.length === 0 && <p className="text-sm text-slate-500">No hands yet.</p>}
            <ul className="space-y-1">
              {history.map((h) => (
                <li key={h.id}>
                  <button className="w-full rounded-md p-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800" onClick={() => loadHand(h.id)}>
                    <div className="flex items-center gap-1">
                      {h.hero_hand.map((c) => <CardFace key={c} card={c} small />)}
                      <span className="mx-1 text-slate-400">|</span>
                      {h.board.map((c) => <CardFace key={c} card={c} small />)}
                    </div>
                    <div className="text-xs text-slate-500">
                      {h.created_at.replace("T", " ").slice(0, 16)} · {h.format} · {h.hero_position} → <b>{h.action}</b>
                      {h.size_bb ? ` ${h.size_bb} BB` : ""} · {h.confidence}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-0.5">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}
