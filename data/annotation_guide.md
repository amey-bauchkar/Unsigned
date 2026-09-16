# Unsigned — annotation guide (two annotators, independent, then adjudicate)

Label every text. Do not look at the author code while labelling.

## distress (what the *writer* is feeling, not how bad the event sounds)
- **0 none** — no personal distress expressed (mundane complaints; neutral reports about others)
- **1 low** — discomfort, irritation, "not a big deal but…", mild worry
- **2 high** — fear, helplessness, exhaustion, panic, "please help", sleeplessness, sarcasm masking a serious incident

Sarcasm rule: a sarcastic text about a serious incident ("great tradition, 3 hours standing") is **high** distress.

## urgency (how soon someone should act)
- **routine** — no immediate risk; pattern information
- **soon** — ongoing situation, should be looked at within days
- **immediate** — physical harm, sexual harassment, threats, recording/sharing of humiliating content, sleep deprivation right now

## types (multi-label; pick all that apply; `none` for mundane)
verbal_abuse · physical · coercion_forced_acts (standing, intros, dances, errands, sleep deprivation) ·
exclusion_social · sexual_harassment · extortion_financial (money, treats, recharges) · cyber (recording, groups, DMs) · none

## sarcasm — 1 if the complaint uses irony/sarcasm to make its point, else 0
## mundane — 1 if the complaint is not about ragging at all
## spans — copy the exact words that name the place / time / who (blank if absent)

Report Cohen's κ per field on the slide. Adjudicate disagreements by discussion; keep a note of hard cases.
