// Pure hand bookkeeping: positions, pot, amount to call, stacks behind, next to act,
// and the request body for /api/analyze.
import { ActionEntry, BOARD_COUNT, HandState, STREETS, Street } from "./types";

export const POSITIONS: Record<number, string[]> = {
  2: ["SB", "BB"],
  3: ["BTN", "SB", "BB"],
  4: ["CO", "BTN", "SB", "BB"],
  5: ["HJ", "CO", "BTN", "SB", "BB"],
  6: ["UTG", "HJ", "CO", "BTN", "SB", "BB"],
  7: ["UTG", "LJ", "HJ", "CO", "BTN", "SB", "BB"],
  8: ["UTG", "UTG1", "LJ", "HJ", "CO", "BTN", "SB", "BB"],
  9: ["UTG", "UTG1", "UTG2", "LJ", "HJ", "CO", "BTN", "SB", "BB"],
};

export const RANKS = "AKQJT98765432".split("");
export const SUITS = ["s", "h", "d", "c"];

/** Action order on a street: preflop as dealt; postflop the blinds first, button last. */
export function streetOrder(players: number, street: Street): string[] {
  const seats = POSITIONS[players];
  if (street === "preflop") return seats;
  if (players === 2) return ["BB", "SB"];
  return [...seats.slice(-2), ...seats.slice(0, -2)];
}

export interface Derived {
  pot: number;
  toCall: number;
  behind: Record<string, number>;
  folded: Set<string>;
  inStreet: Record<string, number>;
  nextToAct: string | null; // null when the street's betting is closed
  heroToAct: boolean;
}

export function derive(h: HandState): Derived {
  const seats = POSITIONS[h.players];
  const behind: Record<string, number> = {};
  const folded = new Set<string>();
  let pot = 0;
  for (const p of seats) {
    const a = Math.min(h.ante, h.stacks[p] ?? 0);
    behind[p] = (h.stacks[p] ?? 0) - a;
    pot += a;
  }
  let inStreet: Record<string, number> = {};
  let nextToAct: string | null = null;
  const upto = STREETS.indexOf(h.street);
  for (const street of STREETS.slice(0, upto + 1)) {
    inStreet = Object.fromEntries(seats.map((p) => [p, 0]));
    if (street === "preflop") {
      const post = (p: string, amt: number) => {
        const x = Math.min(amt, behind[p]);
        inStreet[p] += x;
        behind[p] -= x;
        pot += x;
      };
      post(seats[seats.length - 2], h.sb);
      post(seats[seats.length - 1], h.bb);
    }
    const order = streetOrder(h.players, street);
    const active = () => order.filter((p) => !folded.has(p) && behind[p] > 0);
    let need = new Set(active());
    let last = -1;
    let maxIn = Math.max(...Object.values(inStreet));
    for (const a of h.actions.filter((x) => x.street === street)) {
      const p = a.position;
      let add = 0;
      if (a.action === "fold") folded.add(p);
      else if (a.action === "call") add = Math.min(maxIn - inStreet[p], behind[p]);
      else if (a.action === "bet" || a.action === "raise") add = Math.min((a.amount ?? 0) - inStreet[p], behind[p]);
      else if (a.action === "allin") add = behind[p];
      add = Math.max(0, add);
      inStreet[p] += add;
      behind[p] -= add;
      pot += add;
      if (inStreet[p] > maxIn) {
        maxIn = inStreet[p];
        need = new Set(active().filter((x) => x !== p));
      } else need.delete(p);
      last = order.indexOf(p);
    }
    const live = order.filter((p) => !folded.has(p));
    if (live.length > 1 && need.size > 0) {
      for (let i = 1; i <= order.length; i++) {
        const p = order[(last + i + order.length) % order.length];
        if (need.has(p)) {
          nextToAct = p;
          break;
        }
      }
    } else nextToAct = null;
  }
  const maxIn = Math.max(...Object.values(inStreet));
  const toCall = Math.max(0, Math.min(maxIn - inStreet[h.hero], behind[h.hero]));
  return { pot, toCall, behind, folded, inStreet, nextToAct, heroToAct: nextToAct === h.hero };
}

/** Cards used anywhere in the hand (for greying out the picker). */
export function usedCards(h: HandState): Set<string> {
  return new Set([...h.heroHand, ...h.board].filter((c): c is string => !!c));
}

export function visibleBoard(h: HandState): string[] {
  return h.board.slice(0, BOARD_COUNT[h.street]).filter((c): c is string => !!c);
}

/** Body for POST /api/analyze. Stacks are chips behind; pot and to-call come from the log. */
export function toRequest(h: HandState) {
  const d = derive(h);
  const seats = POSITIONS[h.players]
    .filter((p) => p !== h.hero)
    .map((p) => ({ position: p, stack: d.behind[p], in_hand: !d.folded.has(p), villain_type: h.types[p] ?? "unknown" }));
  const upto = STREETS.indexOf(h.street);
  return {
    format: h.format,
    small_blind: h.sb,
    big_blind: h.bb,
    ante: h.ante,
    players: h.players,
    hero_position: h.hero,
    hero_hand: h.heroHand,
    board: visibleBoard(h),
    pot: d.pot,
    to_call: d.toCall,
    hero_stack: d.behind[h.hero],
    seats,
    actions: h.actions.filter((a) => STREETS.indexOf(a.street) <= upto),
    payouts: h.format === "sng" ? h.payouts : null,
  };
}

export function defaultHand(players = 6, stack = 10000): HandState {
  const seats = POSITIONS[players];
  return {
    format: "cash",
    sb: 50,
    bb: 100,
    ante: 0,
    players,
    hero: seats[Math.max(0, seats.length - 3)] ?? seats[0],
    heroHand: [null, null],
    board: [null, null, null, null, null],
    stacks: Object.fromEntries(seats.map((p) => [p, stack])),
    types: {},
    actions: [],
    street: "preflop",
    payouts: [50, 30, 20],
  };
}

/** Change table size, keeping what still makes sense. */
export function withPlayers(h: HandState, players: number): HandState {
  const seats = POSITIONS[players];
  const stack = h.stacks[h.hero] ?? 10000;
  return {
    ...h,
    players,
    hero: seats.includes(h.hero) ? h.hero : seats[Math.max(0, seats.length - 3)],
    stacks: Object.fromEntries(seats.map((p) => [p, h.stacks[p] ?? stack])),
    actions: [],
  };
}

/** Everyone still to act folds until it is hero's turn (or the street closes). */
export function foldToHero(h: HandState): HandState {
  let cur = h;
  for (let guard = 0; guard < 20; guard++) {
    const d = derive(cur);
    if (!d.nextToAct || d.nextToAct === cur.hero) break;
    cur = { ...cur, actions: [...cur.actions, { street: cur.street, position: d.nextToAct, action: "fold" }] };
  }
  return cur;
}

export function addAction(h: HandState, a: Omit<ActionEntry, "street">): HandState {
  return { ...h, actions: [...h.actions, { ...a, street: h.street }] };
}

export const fmt = (x: number | null | undefined, digits = 1) =>
  x == null ? "–" : Number.isInteger(x) ? String(x) : x.toFixed(digits);
