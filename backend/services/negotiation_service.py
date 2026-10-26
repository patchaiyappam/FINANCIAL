# =============================================================================
# NEGOTIATION RULES ENGINE (ADR-014)
# =============================================================================
# THIS FILE DECIDES THE MONEY. Nothing else does.
#
# ADR-003 binding constraint: the AI extracts intent and voices replies; it never
# determines a financial outcome. Every rupee below is computed from seeded,
# reproducible rules so that two players in the same situation making the same
# offer always get the same result, regardless of how well either writes English.
#
# NO NETWORK CALLS IN THIS MODULE. That is what makes the event-day fallback real.

import hashlib
import random

from models.constants import (
    NEGOTIATION_MAX_ROUNDS, NEGOTIATION_MIN_ROUND_TO_ACCEPT,
    SATISFACTION_START, SATISFACTION_MIN, SATISFACTION_MAX,
    SATISFACTION_DELTA, negotiation_min_ratio, ARCHETYPES,
)
from models.negotiation_intents import (
    ACCEPT_PROPOSAL, COUNTER_OFFER, REQUEST_DELAY,
    PROPOSE_ALTERNATIVE, ASK_QUESTION, REFUSE,
)

# ── Built-in proposal catalogue ──────────────────────────────────────────────
# Admin rows in public.spouse_proposals override these; this is the offline
# default so the feature works before anyone authors content.
#
# Note the design intent from ADR-014 §1.1: she is NOT always asking to overspend.
# Three of the four wives raise proposals that are financially SOUND, so
# "always haggle her down" is a losing strategy and each month is a real judgment.
DEFAULT_PROPOSALS = {
    "earner": {
        "kind": "lifestyle", "title": "A proper housewarming function",
        "description": "Her side of the family expects us to host. Venue, catering and outfits.",
        "amount_min": 28000, "amount_max": 42000,
        "ev_note": "Pure consumption. Nothing comes back financially — but refusing hurts her."
    },
    "investor": {
        "kind": "investment", "title": "Put money into the market now",
        "description": "She has been tracking a fund and wants to move household cash into equity this month.",
        "amount_min": 25000, "amount_max": 40000,
        "ev_note": "Cash converts to stocks 1:1. Worth it if the market rises, costly if it stalls."
    },
    "saver": {
        "kind": "saving", "title": "Restructure the household budget",
        "description": "She wants to switch providers and renegotiate bills. Costs money upfront to set up.",
        "amount_min": 12000, "amount_max": 20000,
        "ev_note": "Permanently cuts monthly expenses. Strongly positive the earlier it happens."
    },
    "anchor": {
        "kind": "protection", "title": "Top up the emergency fund",
        "description": "She is uneasy about how thin the buffer is and wants to build it up now.",
        "amount_min": 20000, "amount_max": 32000,
        "ev_note": "Cash moves to the emergency fund 1:1 and earns interest. Saves you in a shock month."
    },
}

# Permanent monthly saving delivered by a 'saving' proposal, as a share of the
# agreed amount. 0.18 => a Rs20,000 restructure saves Rs3,600/month thereafter.
SAVING_MONTHLY_RETURN = 0.18


def _seed(user_id: str, month: int, salt: str = "") -> random.Random:
    """Per-player, per-month, reproducible. Same inputs => same proposal, always."""
    h = hashlib.sha256(f"{user_id}:{month}:negotiation:{salt}".encode()).hexdigest()
    return random.Random(int(h, 16))


def generate_proposal(user_id: str, month: int, archetype_id: str,
                      catalogue: list = None) -> dict:
    """
    Build this month's proposal. Deterministic: re-calling with the same
    arguments returns an identical proposal, so a page refresh cannot reroll it.
    """
    rng = _seed(user_id, month, "proposal")

    row = None
    if catalogue:
        matching = [c for c in catalogue
                    if c.get("archetype_id") == archetype_id
                    and (c.get("month") in (None, month))]
        if matching:
            row = matching[rng.randrange(len(matching))]

    if row is None:
        base = DEFAULT_PROPOSALS.get(archetype_id)
        if not base:
            return None
        row = dict(base, archetype_id=archetype_id)

    lo = float(row["amount_min"])
    hi = float(row["amount_max"])
    ask = int(round((lo + rng.random() * (hi - lo)) / 500.0) * 500)

    return {
        "archetype_id": archetype_id,
        "kind": row["kind"],
        "title": row["title"],
        "description": row["description"],
        "ev_note": row.get("ev_note", ""),
        "ask": ask,
        "month": month,
    }


def evaluate(intent: str, params: dict, proposal: dict, round_no: int,
             satisfaction: float, player_cash: float,
             argument_features: dict = None, previous_category: str = None) -> dict:
    """
    Decide the outcome of one negotiation turn.

    Returns:
        {
          resolved: bool,          # is the negotiation over?
          outcome: str,            # accepted_full | accepted_counter | refused |
                                   # delayed | auto_resolved | continue | invalid
          agreed_amount: float,
          satisfaction_delta: int,
          effects: dict,           # financial deltas for the caller to apply
          reason: str,             # why, in plain language (shown to the player)
          required_minimum: float, # what she would have accepted this round
          character_eval: dict     # evaluated character features & floor ratio (Stage 3B)
        }
    """
    ask = float(proposal["ask"])
    arch = proposal["archetype_id"]

    char_eval = None
    if argument_features is not None:
        from services.spouse_character_service import evaluate_spouse_character
        char_eval = evaluate_spouse_character(
            arch, argument_features, satisfaction, round_no, previous_category
        )
        min_ratio = char_eval["effective_floor_ratio"]
    else:
        min_ratio = negotiation_min_ratio(arch, satisfaction)

    required = round(ask * min_ratio, 2)

    def out(resolved, outcome, amount, delta, effects, reason):
        res = {
            "resolved": resolved, "outcome": outcome,
            "agreed_amount": round(amount, 2),
            "satisfaction_delta": delta, "effects": effects,
            "reason": reason, "required_minimum": required,
        }
        if char_eval:
            res["character_eval"] = char_eval
        return res

    # ── Free actions: no money, no resolution ──
    if intent == ASK_QUESTION:
        return out(False, "continue", 0, 0, {},
                   "She explains her reasoning. Asking costs you nothing.")

    if intent == ACCEPT_PROPOSAL:
        if player_cash < ask:
            return out(False, "invalid", 0, 0, {},
                       f"You do not have Rs{ask:,.0f} in cash. Counter with what you can afford.")
        return out(True, "accepted_full", ask, SATISFACTION_DELTA["accepted_full"],
                   _effects(proposal, ask), "You agreed to her figure in full.")

    if intent == REFUSE:
        return out(True, "refused", 0, SATISFACTION_DELTA["refused"], {},
                   "You turned her down flat. She is not happy about it.")

    if intent == REQUEST_DELAY:
        return out(True, "delayed", 0, SATISFACTION_DELTA["delayed"], {},
                   "She agrees to revisit it later, reluctantly.")

    if intent == PROPOSE_ALTERNATIVE:
        # An alternative is a structured way of asking for ~25% off.
        implied = round(ask * 0.75, 2)
        return _counter(implied, ask, required, round_no, proposal, player_cash, out,
                        prefix="She considers your alternative. ")

    if intent == COUNTER_OFFER:
        return _counter(float(params["amount"]), ask, required, round_no,
                        proposal, player_cash, out)

    return out(False, "invalid", 0, 0, {}, "That is not something she can respond to.")


def _counter(offer, ask, required, round_no, proposal, player_cash, out, prefix=""):
    if offer > player_cash:
        return out(False, "invalid", 0, 0, {},
                   f"{prefix}You only have Rs{player_cash:,.0f} in cash.")

    if offer >= ask:
        return out(True, "accepted_full", offer, SATISFACTION_DELTA["accepted_full"],
                   _effects(proposal, offer), f"{prefix}That is her full ask — she accepts happily.")

    # ── THE "no instant convincing" RULE (ADR-014 §2.2) ──
    # However good the first offer is, she does not settle on round 1. Persuasion
    # takes more than one message. This is the requirement, in code.
    if round_no < NEGOTIATION_MIN_ROUND_TO_ACCEPT:
        return out(False, "continue", 0, -1, {},
                   f"{prefix}She is not ready to settle yet — she wants to talk it through.")

    if round_no >= NEGOTIATION_MAX_ROUNDS:
        # Out of rounds. She proceeds at her own figure; stonewalling has a cost.
        if offer >= required:
            return out(True, "accepted_counter", offer, SATISFACTION_DELTA["accepted_counter"],
                       _effects(proposal, offer), f"{prefix}She accepts, on the last word.")
        return out(True, "auto_resolved", ask, SATISFACTION_DELTA["auto_resolved"],
                   _effects(proposal, ask),
                   f"{prefix}You could not agree, so she went ahead at Rs{ask:,.0f}.")

    if offer >= required:
        return out(True, "accepted_counter", offer, SATISFACTION_DELTA["accepted_counter"],
                   _effects(proposal, offer), f"{prefix}She thinks about it, then agrees.")

    gap = required - offer
    hint = "close" if gap <= ask * 0.10 else "not close"
    return out(False, "continue", 0, -1, {},
               f"{prefix}She will not go that low. You are {hint} to what she would take.")


def _effects(proposal: dict, amount: float) -> dict:
    """
    Financial consequence of an agreed proposal. The player always pays `amount`
    in cash; what they get back depends on the KIND — which is the lesson.
    """
    kind = proposal["kind"]
    eff = {"cash": -amount}

    if kind == "investment":
        eff["stocks"] = amount            # 1:1 into equity; value follows the market
    elif kind == "protection":
        eff["emergency_fund"] = amount    # 1:1 into the buffer; earns interest
    elif kind == "saving":
        # Permanent reduction in monthly household costs.
        eff["household_expense_modifier"] = -round(amount * SAVING_MONTHLY_RETURN, 2)
    # 'lifestyle' returns nothing financially — that is the point of it.

    return eff


def clamp_satisfaction(value: float) -> int:
    return int(max(SATISFACTION_MIN, min(SATISFACTION_MAX, round(value))))

DEFAULT_PROPOSALS.update({"teacher": dict(DEFAULT_PROPOSALS["saver"]), "healthcare": dict(DEFAULT_PROPOSALS["anchor"])})
