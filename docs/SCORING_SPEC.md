# Scoring spec — adherence, pillars, anchors, unmet demand

Second half of the worker job. Same transcript read as `EXTRACTION_SPEC.md`,
three more output files. Read that spec first.

**On bias:** you are scoring process and outcome from the same transcript, so
this is *independent* scoring, not blind scoring — the ending is visible to
you. Score the process on what the rep demonstrably did, not on how it turned
out. A sloppy call that closed still scores badly. A textbook call that lost
still scores well. A separate audit re-scores a random subsample without the
outcome to measure how much this leaks; your job is to make that gap small.

---

## A. Adherence → `data/scores/parts/<call_id>.adherence.json`

Score against the Kettlebell Body sales process. Full check text is in
`data/playbook.json` — read it once at the start.

| Phase | Name | Weight |
|-------|------|--------|
| P1 | Open & Frame | 10 |
| P2 | Baseline | 15 |
| P3 | Goals — Surface to Deep | 20 |
| P4 | Past Attempts & Root Cause | 15 |
| P5 | Consequence Frame | 20 |
| P6 | Commitment Check | 20 |
| P11 | Payment & Onboarding | 20 |

Every check scores `hit` · `partial` · `miss` · `not_applicable`.

- **`hit`** — the rep demonstrably ran the move.
- **`partial`** — attempted, incomplete, or a weaker variant. Example: a
  three-part frame where the script asks for four.
- **`miss`** — applicable and not done. **If the prospect volunteers the
  information unprompted and the rep never asked, that is a `miss`.** The
  script credits asking, not luck.
- **`not_applicable`** — the call could not reach it. A follow-up call has no
  Baseline; a call with no close attempt has no P11. N/A drops out of the
  denominator so nobody is penalised for an unreachable phase.

Phase `score` is your holistic read of its checks, same four values.

```jsonc
{
  "call_id": "...",
  "rep": "Andrew Musial",
  "disposition": "closed",
  "phases": {
    "P1": { "score": "partial",
            "checks": { "P1a": "miss", "P1b": "hit", "P1c": "hit", "P1d": "hit" },
            "evidence": "what happened, with a short quote" }
    // ... P2, P3, P4, P5, P6, P11
  },
  "objection_plays": [
    { "play": "OC", "trigger_present": true, "ran": "partial",
      "detail": "which scripted moves ran and which did not, specifically" }
  ],
  "notes": "one or two sentences a coach could act on"
}
```

**Objection plays** (definitions in `playbook.json`):
`OA` think about it · `OB` talk to my wife · `OC` money/open-wallet ·
`OD` not the right time · `OE` fear/doubt

- `trigger_present` — did the prospect raise it, in substance? "Might not be
  the right time for me" is OD even without those exact words.
- `ran` — `hit` (played it through), `partial` (started, abandoned), `miss`
  (trigger landed, no play).
- If an objection has **no** scripted play (clinical fit, a cheaper substitute
  that worked), record `"play": "none"`, `trigger_present: true`, and describe
  it. Those are gaps in the script, not rep failures, and we want them.

---

## B. Signals → `data/scores/parts/<call_id>.signals.json`

```jsonc
{
  "call_id": "...",
  "pillar_reactions": [
    { "pillar": "training_mobility", "reaction": "confused", "evidence": "quote + what happened" },
    { "pillar": "nutrition",         "reaction": "accepted",  "evidence": "..." },
    { "pillar": "accountability",    "reaction": "clarifying","evidence": "..." }
  ],
  "anchors": [
    { "type": "competitor_price", "raw": "exact quote",
      "direction": "undercuts_price", "competitor": "name or null",
      "note": "why it matters" }
  ],
  "unmet_demand": [
    { "want": "what they asked for",
      "why_unmet": "why the offer does not do it",
      "verdict": "product_gap" }
  ]
}
```

**Pillars** — the three the reps present: `training_mobility`, `nutrition`,
`accountability`. Reactions:

- `enthusiastic` — volunteers a positive reaction or ties it to their own goal
- `accepted` — understood, agreed, no questions
- `clarifying` — asked questions to understand the mechanics
- `confused` — misunderstood and needed correcting, or asked twice
- `objected` — pushed back on the substance
- `not_presented` — never delivered on this call

**Anchor `direction`** — `supports_price` or `undercuts_price`. An anchor is
whatever number or product is already in the prospect's head when they hear
$6,000: a cheaper competitor, an existing trainer, a subscription expectation,
or on the supportive side, a partner already enrolled or a habit of paying for
coaching.

**`unmet_demand.verdict`:**
- `product_gap` — they want something the programme genuinely does not do
- `positioning_gap` — the programme probably does do it, nobody said so
- `out_of_icp` — they want a fundamentally different kind of product
- `unvalidated` — unclear whether it is served; flag for a human

Empty arrays are fine and expected. Do not manufacture anchors or gaps.

---

## C. ICP → `data/scores/parts/<call_id>.icp.json`

Criteria come from the ICP as stated on a live call (`data/icp.json`):
`successful` · `income` · `neglected_health` · `good_to_great` ·
`not_deconditioned`.

```jsonc
{
  "call_id": "...",
  "fit": "core",                    // core | edge | outside
  "matches": ["successful", "income"],
  "misses":  ["good_to_great"],
  "note": "one or two sentences on why"
}
```

`core` = meets essentially all of it. `edge` = meets some, misses at least one
material criterion. `outside` = misses most. Judge against the criteria as
written, **not** against whether they bought. Someone outside the ICP who
closes is a finding, and flattening that to "they bought so they must fit"
destroys the whole point of the comparison.

---

## D. Output discipline

Four files per call: the extraction, plus these three under
`data/scores/parts/`. Then return a **compact** summary — call_id, prospect,
rep, disposition, adherence headline, and anything anomalous.

Never paste transcript text or full JSON into your final message.
