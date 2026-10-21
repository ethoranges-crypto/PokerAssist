"""Compact notation for test spots -> HandInput.

actions: "[street:] POS action [amount]", e.g. "CO raise 250", "flop: BB check".
stacks: one number for everyone, or {position: stack}. in_hand: villains still in.
"""

from engine.positions import positions
from engine.schema import HandInput


def parse_actions(lines):
    out = []
    for line in lines:
        street = "preflop"
        if ":" in line:
            street, line = (x.strip() for x in line.split(":", 1))
        parts = line.split()
        a = {"street": street, "position": parts[0], "action": parts[1]}
        if len(parts) > 2:
            a["amount"] = float(parts[2])
        out.append(a)
    return out


def build(spot: dict) -> HandInput:
    n, hero = spot["players"], spot["hero"]
    stacks = spot.get("stacks", 10000)
    types = spot.get("types", {})
    seats = [
        {
            "position": p,
            "stack": stacks[p] if isinstance(stacks, dict) else stacks,
            "in_hand": p in spot["in_hand"],
            "villain_type": types.get(p, "unknown"),
        }
        for p in positions(n)
        if p != hero
    ]
    sb, bb = spot.get("blinds", [50, 100])
    return HandInput(
        format=spot.get("format", "cash"),
        small_blind=sb,
        big_blind=bb,
        ante=spot.get("ante", 0),
        players=n,
        hero_position=hero,
        hero_hand=spot["hand"],
        board=spot.get("board", ""),
        pot=spot["pot"],
        to_call=spot.get("to_call", 0),
        hero_stack=spot.get("hero_stack", 10000),
        seats=seats,
        actions=parse_actions(spot.get("actions", [])),
        payouts=spot.get("payouts"),
    )
