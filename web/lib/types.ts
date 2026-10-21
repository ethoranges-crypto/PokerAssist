export type Format = "cash" | "sng";
export type Street = "preflop" | "flop" | "turn" | "river";
export type ActionKind = "fold" | "check" | "call" | "bet" | "raise" | "allin";
export type VillainType = "unknown" | "tight" | "loose" | "passive" | "aggressive";

export const STREETS: Street[] = ["preflop", "flop", "turn", "river"];
export const BOARD_COUNT: Record<Street, number> = { preflop: 0, flop: 3, turn: 4, river: 5 };

export interface ActionEntry {
  street: Street;
  position: string;
  action: ActionKind;
  amount?: number; // bet/raise: total "to" amount on this street (chips)
}

export interface HandState {
  format: Format;
  sb: number;
  bb: number;
  ante: number;
  players: number;
  hero: string;
  heroHand: (string | null)[];
  board: (string | null)[];
  stacks: Record<string, number>; // starting stacks (chips), every seat incl. hero
  types: Record<string, VillainType>;
  actions: ActionEntry[];
  street: Street;
  payouts: number[];
}

export interface OptionEV {
  id: string;
  action: ActionKind;
  size_chips: number | null;
  size_bb: number | null;
  size_pct_pot: number | null;
  ev_chips: number;
  ev_bb: number;
  ev_dollars: number | null;
  fold_equity: number | null;
  equity_when_called: number | null;
}

export interface VillainRange {
  position: string;
  villain_type: VillainType;
  combos: number;
  pct_of_hands: number;
  grid: number[][];
  source: string;
}

export interface Recommendation {
  action: ActionKind;
  option_id: string;
  size_chips: number | null;
  size_bb: number | null;
  size_pct_pot: number | null;
  alternatives: { option: string; action: string; size_bb: number | null; frequency: number; ev_bb: number }[];
  ev_bb: number;
  ev_dollars: number | null;
  equity: number;
  pot_odds: number | null;
  required_equity: number;
  spr: number;
  confidence: "high" | "medium" | "low";
  explanation: string;
  explanation_source: "llm" | "engine";
  hand_description: string;
  mode: string;
  villains: VillainRange[];
  options: OptionEV[];
  icm: Record<string, number | string | null> | null;
  chart: Record<string, unknown> | null;
  notes: string[];
  validation: { llm_option: string | null; overridden: boolean; numbers_rejected: string[]; error: string | null };
  timing_ms: Record<string, number>;
  hand_id: number | null;
}

export interface HandSummary {
  id: number;
  created_at: string;
  format: Format;
  hero_position: string;
  hero_hand: string[];
  board: string[];
  action: string;
  size_bb: number | null;
  confidence: string;
  notes: string;
}
