# Extraction spec — Primal Instinct call audit

Every worker agent follows this exactly. The single most important rule:
**use the controlled vocabularies below verbatim.** If thirty agents invent
their own category names the rollups collapse into noise. When something
genuinely does not fit, use the `other` value and put your proposed label in
the free-text `text` field — clustering happens later, centrally.

---

## 1. What you produce

For each transcript, write ONE file to `data/calls/<call_id>.json`.

`call_id` = `<YYYY-MM-DD>_<prospect-slug>_<rep-slug>`
e.g. `2026-07-23_robyn-stillwater_andrew-musial`
Slugs are lowercase, spaces → hyphens, punctuation stripped.

Use full real names in these files. Pseudonymisation happens later in the
build, never at extraction time.

---

## 2. Reading the transcript

Format is Fathom-style: `HH:MM:SS - Speaker Name` then the text.

**Speaker resolution — the rep is the speaker labelled `(Primal Instinct)`.
Every other speaker label is the prospect.** This handles two real problems:

1. **Diarization swaps lines.** In every pilot call, short turns were
   attributed to the wrong speaker; in one, whole passages inverted. So
   **read role from content, never from the label.** If a line asks a
   discovery question it is the rep, whatever the label says.
2. **A prospect can change identity mid-call.** One rejoined from a phone and
   became "Paco's iPhone 17". Both labels are the same person.

Because line-level attribution is unreliable, **never** record talk-ratio,
word counts, or "who said it first". Record only role-level facts: an
objection occurred, a phase was run, a pillar was presented.

If more than one `(Primal Instinct)` speaker appears, the one with the most
turns is the closer; list the others in `rep.additional_reps`.

**Junk:** files under 2,000 bytes are failed recordings. Skip them and report
the id — do not write a record.

**Non-sales calls:** some transcripts are internal (rep × rep, "Gameplan"
sessions, manager check-ins). If neither participant is a prospect, set
`call.stage` to `"internal"`, fill what you can, and leave goals/pains/
objections empty. Do not force it into a sales shape.

---

## 3. The record

```jsonc
{
  "call_id": "2026-07-23_robyn-stillwater_andrew-musial",
  "source": {
    "drive_file_id": "...",
    "drive_folder": "Andrew Musial",        // rep folder it came from
    "original_title": "...",                // VERBATIM, including KFS/KL/DH suffixes
    "display_title": "...",                 // original + " — Closed" / " — Follow Up" / " — Lost" / " — Undetermined"
    "file_size_bytes": 41325
  },
  "call": {
    "date": "2026-07-23",                   // from the MM/DD/YYYY title prefix
    "stage": "closer",                      // setter | closer | onboarding | internal
    "sequence_position": 1,                 // 2+ if the transcript references a previous call
    "sequence_note": "...",                 // only if sequence_position > 1
    "duration_min_est": 47,                 // final timestamp, rounded to minutes
    "prospect_named_in_title": true,
    "prospect_name_recovered_from_transcript": false
  },
  "rep": { "name": "Andrew Musial", "role": "closer", "location": "Poland" },
  "setter": {
    "code": "KFS",                          // KFS | KL | DH | null — from the title suffix
    "name": "Kim Forbes-Sobers",            // KFS=Kim Forbes-Sobers, KL=Kyla, DH=unknown
    "confidence": "high",
    "evidence": "quote where the prospect names the setter, or null"
  },
  "prospect": {
    "name": "Robyn Stillwater",
    "aka": null,                            // device label or nickname, if any
    "name_source": "title",                 // title | transcript
    "location": "Emigration Canyon / Salt Lake City, Utah, USA",
    "age": null,
    "occupation": "Not currently working",
    "family_status": "...",
    "height_in": 65, "weight_lb": 144,
    "bodyfat_pct_self_reported": null,
    "training_background": "...",
    "kettlebell_experience": "none",        // none | some | experienced
    "medical": "..."                        // null if nothing disclosed
  },
  "avatar": { "assigned": "the_warm_referral", "confidence": 0.95, "signals": ["...", "..."] },
  "goals":  [ { "text": "verbatim-ish paraphrase", "category": "<from vocab>" } ],
  "pains":  [ { "text": "...", "category": "<from vocab>", "severity": "low|medium|high|critical" } ],
  "objections": [
    {
      "type": "<from vocab>",
      "raw_quote": "exact words from the transcript",
      "timestamp": "00:33:37",
      "rep_response": "what the rep actually did",
      "response_tactic": "snake_case label",
      "resolved": true
    }
  ],
  "offer": {
    "presented": true,
    "presented_on_prior_call": false,
    "tiers": [ { "months": 6, "price_usd": 6000 } ],
    "recommended_tier_months": 6,
    "payment_plan_offered": false,
    "payment_plan_structured_live": false,
    "payment_plan_terms": null,
    "guarantee_mentioned": "quote or paraphrase of the guarantee AS STATED, or null",
    "prospect_financials": null             // {available_now_usd, monthly_surplus_usd, has_savings, credit_score} if disclosed
  },
  "outcome": {
    "disposition": "closed",                // closed | follow_up | lost | undetermined
    "confidence": 0.98,                     // 0-1, your honest certainty
    "close_rule_applied": null,             // "verbal_agreement_plus_link_sent" when that rule decided it
    "evidence": ["...", "..."],             // include counter-evidence too
    "cash_collected_usd": 6000,             // payment plan → contract value; note it in cash_collection_basis
    "cash_collection_basis": null,          // "payment_plan_total" when applicable
    "next_step": "..."
  },
  "notable": { "note": "anything a manager would want flagged" },
  "quality": {
    "diarization_reliability": "medium",    // high | medium | low
    "speaker_label_swaps_detected": true,
    "notes": "where and how badly"
  }
}
```

---

## 4. Controlled vocabularies

### `outcome.disposition`
- `closed` — paid, OR **verbally agreed to move forward AND a payment link was
  sent**. This is a client-agreed rule; apply it even when the transcript ends
  before payment confirms. Set `close_rule_applied` when you use it.
- `follow_up` — no decision, conversation continues
- `lost` — explicit no, or the rep disqualified them
- `undetermined` — genuinely cannot tell; use sparingly and say why

### `pains[].category`
`injury` · `medical` · `mental_health` · `sleep` · `aging` · `consistency` ·
`motivation` · `accountability_gap` · `nutrition_habit` ·
`training_dissatisfaction` · `training_barrier` · `competence_anxiety` ·
`fragmented_solutions` · `program_fit` · `time_scarcity` · `emotional` ·
`confidence` · `relationship` · `work_stress` · `other`

### `goals[].category`
`fat_loss` · `muscle_gain` · `mobility` · `endurance` · `strength` ·
`longevity_function` · `longevity_family` · `family_role_model` ·
`hobby_performance` · `energy_performance` · `injury_prevention` ·
`injury_confidence` · `consistency` · `sustainability` · `confidence` ·
`relationship` · `pregnancy_prep` · `convenience` · `appearance` · `other`

### `objections[].type`
`price` · `affordability` · `timing_cashflow` · `timing_medical` ·
`timing_other` · `value_vs_cheaper_alternative` · `value_at_reduced_scope` ·
`spouse_consult` · `think_about_it` · `fear_doubt` · `risk_of_harm` ·
`medical_program_fit` · `unfamiliar_modality` · `program_longevity_proof` ·
`icp_mismatch` · `life_event_conflict` · `trust_provider` · `other`

### `avatar.assigned`
- `the_optimizer` — already fit and successful, wants good → great, price is
  a quality signal not a barrier
- `the_rebuilder` — lost ground to illness, injury or a hard season; wants a
  former self back; often carries visible regret
- `the_warm_referral` — arrives pre-sold via a partner or friend already in
  the programme; price pre-framed; little resistance
- `skeptical_bargain_hunter` — self-directed and capable, anchored to a cheap
  alternative that genuinely worked
- `the_medically_constrained` — high intent, no price resistance, blocked by
  a clinician or an injury the programme cannot work around
- `other` — put a proposed label and reasoning in `avatar.signals[0]`

---

## 5. Judgement rules

- **Quote, don't paraphrase, in `raw_quote`.** Everything else can be tightened.
- **`resolved` is strict.** True only if the prospect visibly moved on. "Let me
  think about it" after a rebuttal is NOT resolved.
- **Record counter-evidence in `outcome.evidence`.** A confident-looking close
  that cuts off mid-call must say so.
- **Confidence is honest, not flattering.** 0.6 is a fine score.
- **Never invent.** Absent → `null`. Do not infer an age, a job, or a price
  that was never said.
- **The offer is $6,000 / 6 months and $9,000 / 12 months.** If you see other
  numbers, record them exactly — a pricing deviation is a finding.

---

## 6. Output discipline

Write the JSON file. Return a compact summary only: call_id, prospect, rep,
disposition, confidence, and any anomaly worth escalating. **Never paste
transcript text or the full JSON into your final message** — it floods the
orchestrator's context and the file on disk is the deliverable.
