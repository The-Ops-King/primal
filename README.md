# Primal Instinct — Call Integrity Audit

Breaks every 2026 Primal Instinct sales call into its component parts, stores them locally in a
queryable form, scores each call against the Kettlebell Body sales script, and publishes a dashboard.

Live at **primal.jtylerray.com** (Vercel, static).

## Layout

```
data/
  calls/*.json        one structured extraction per call — SOURCE OF TRUTH
  scores/adherence.json  script adherence scoring, one entry per call
  playbook.json       the Kettlebell Body sales process, machine-readable
  primal.db           generated SQLite (gitignored — rebuild it)
  raw/                raw transcripts (gitignored — client data)
src/build_db.py       builds primal.db + web/data.json from the JSON above
web/                  the dashboard (static; index.html + generated data.json)
```

## Rebuild

```bash
python3 src/build_db.py
```

Drops and recreates every table, then writes `web/data.json`. The JSON files stay the single
source of truth — nothing is authored directly in the database.

## Query it

```bash
sqlite3 data/primal.db "
  SELECT a.rep_name, a.adherence_pct, a.disposition
  FROM adherence a ORDER BY a.adherence_pct DESC;"
```

Tables: `calls`, `goals`, `pains`, `objections`, `offer_tiers`,
`adherence`, `phase_scores`, `check_scores`, `objection_plays`.

## Known limits — read before quoting a number

1. **Outcomes are inferred from transcript language, not CRM-verified.** A call that ends
   "let me think about it" and closes by text three days later is scored as a follow-up forever.
   Every call carries an `outcome.confidence`. Joining a CRM or payments export is the single
   highest-value upgrade available.
2. **Adherence and outcome were scored in the same pass**, so the perfect rank correlation between
   them is exposed to halo bias. Blind scoring against verified outcomes is needed before the
   correlation means anything.
3. **Fathom diarization is unreliable in all five pilot calls** — speaker labels swap on short turns
   and, in one call, invert for long stretches. Do not build talk-ratio or who-said-it metrics on raw
   labels without a repair pass.
4. **A deal is not a call.** Multi-call sequences exist in the corpus; the pilot contains one
   explicitly (`2026-07-18_tyron-giuliani_michael-brideau` is call two of two).
5. **n=5.** This is a schema validation pilot, not a finding set.

## Pilot sample

Five calls, five reps, five outcomes — deliberately spread across named and untitled
("Impromptu Zoom Meeting") files to prove prospect-name recovery works on both.
