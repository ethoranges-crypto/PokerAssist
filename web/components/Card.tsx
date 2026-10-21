const SUIT_SYMBOL: Record<string, string> = { s: "♠", h: "♥", d: "♦", c: "♣" };
const SUIT_COLOR: Record<string, string> = {
  s: "text-slate-900 dark:text-slate-100",
  h: "text-red-600 dark:text-red-400",
  d: "text-blue-600 dark:text-sky-400",
  c: "text-emerald-700 dark:text-emerald-400",
};

export function CardFace({ card, small }: { card: string | null; small?: boolean }) {
  const size = small ? "h-8 w-6 text-xs" : "h-11 w-8 text-sm";
  if (!card)
    return <span className={`${size} inline-flex items-center justify-center rounded border border-dashed border-slate-400 dark:border-slate-600`} />;
  return (
    <span className={`${size} inline-flex flex-col items-center justify-center rounded border border-slate-300 bg-white font-bold leading-none dark:border-slate-600 dark:bg-slate-800 ${SUIT_COLOR[card[1]]}`}>
      {card[0]}
      <span>{SUIT_SYMBOL[card[1]]}</span>
    </span>
  );
}

export const suitSymbol = (s: string) => SUIT_SYMBOL[s];
export const suitColor = (s: string) => SUIT_COLOR[s];
