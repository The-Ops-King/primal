# Session Handoff

## Last Updated
2026-08-01, end of second session

## Second Session — condensing the dashboard

The page was an enumeration. It listed every prospect per ICP band, every
per-prospect assessment, all 422 rep/guarantee pairs, 60 individual price
anchors and 51 pain/goal accordions. Measured: **70,650 px, 147 accordions,
698 table rows — 78 screens.** It is now **23,664 px / 26 screens**, same
findings, no identities, no per-observation lists.

What changed:

- **New bucket layer** in `build_db.py` (`build_buckets`, plus the
  `ANCHOR_THEMES` / `UNMET_THEMES` / `PAIN_GROUPS` / `GOAL_GROUPS` /
  `OBJECTION_GROUPS` / `ICP_CRITERIA` maps). Three extracted vocabularies came
  back as free text — anchor `type` had **852 distinct strings** across 1,524
  anchors, unmet `want` was 1,288 distinct sentences. First-hit keyword maps
  fold them into 6–10 themes. Unmatched items land in a reported `other`
  bucket rather than being dropped: anchors 21%, unmet 27%. A growing `other`
  is the signal the map needs another theme.
- **Every rate is computed over the full corpus**, then the underlying list is
  discarded. Previously `slim_payload` shipped 60 of 1,524 anchors, so any
  rate read off the table was a sample statistic wearing a population label.
- **All per-prospect lists removed** from both page and payload: ICP `who` +
  assessments, funnel `deals_died`, per-rep guarantees, pillar quotes,
  pain/goal items, avatar names, the per-call duration list. Payload
  1.31 MB → 942 KB.
- Seven script-adherence accordions (one table each) → one ranked
  **twelve least-run moves** table. Discriminator tables 14 rows → 6.
  Critical-flag sample 20 → 8; the systemic clusters already carry that story.

### Two real bugs found and fixed

1. **Redaction was corrupting the whole payload.** Prospects recorded as
   "Jason S" (single-letter surname) put `subs["S"] = "S."`, and redaction is a
   blind whole-blob `str.replace` — so *every capital S, R and L in the
   payload* was rewritten. "Sport" → "S.port", "Stephanie" → "S.tephanie".
   Visible in the old screenshots. Surnames under three characters are now
   skipped, the rest match on a word boundary, and surnames that are ordinary
   words (`GENERIC_SURNAMES`) are skipped in the standalone-surname pass only.
2. **`standalone.html` had been shipping broken.** `build_standalone.py`
   matched the loader with `fetch\("\./data\.json"\)[\s\S]*?\}\);` — the first
   `});` after the fetch is *inside* `render()`, so the build ate the opening
   of the render function. The committed standalone contained no `render`
   at all. Now anchored on explicit `/* LOADER:START */` … `/* LOADER:END */`
   markers in `index.html`, with an assertion that `render` survives, and
   `render(DATA)` appended before `</script>` (calling it inline hit a temporal
   dead zone on `PAGE_SIZE`).

**Not yet deployed** — `npx vercel --prod --yes` still to run.

## What This Is
Integrity audit of Primal Instinct sales calls. Transcripts live in a Google
Drive folder shared by info@primalinstinct.net ("Sales Call Recording
Transcripts", 8 rep subfolders). Pipeline extracts each call into structured
JSON, scores it against the Kettlebell Body sales script, and renders a
dashboard at **primal.jtylerray.com**.

Repo: https://github.com/The-Ops-King/primal (pushed, current)

## What Was Accomplished

- **422 sales calls extracted and scored** → 388 deals, window 2026-05-01 to
  2026-07-31. Plus 116 internal calls reviewed for findings and excluded from
  every sales metric.
- **Local store**: `data/calls/*.json` (source of truth) + `data/primal.db`
  (SQLite, 10 tables incl. 15,667 script checks). Rebuild with
  `python3 src/build_db.py`.
- **Dashboard live** at primal.jtylerray.com, deployed via Vercel CLI.
  11 sections. Brand tokens measured off primalinstinctcoaching.com
  (cyan #1ABBD7, black, Anton + Montserrat) — see `web/brand.css` and
  `web/style-guide.html`.
- **Integrity flags**: 2,663 total, 204 critical, 21 systemic clusters.
- **Rename manifest** generated (`data/rename_manifest.csv`, `docs/rename.gs`)
  but **deliberately NOT run** — see Decisions below.

## Key Findings (all at n=422 unless noted)

- Close rate **19.4%**
- **Consequence Frame (script phase 5) runs at 20.6%** — every other phase is
  46–59%. Biggest single coaching gap.
- **Skeptical Bargain Hunter avatar: 56 deals, 1.8% close rate.** One close in
  56. Optimizer is 111 deals at 30.6%.
- **Payment plan structured live: 52% of closes vs 30% of non-closes.**
- Call length is an inverted U: 60–74 min closes at 30%, **75+ min at 8%**,
  under 20 min at 9%.
- Objection plays barely executed: Money (OC) triggered 312×, run in full 24×.
- **149 critical clinical_risk flags** — prospects disclosing cancer, recent
  surgery, spinal injury, EDS, active treatment, then sold loaded ballistic
  kettlebell work with no clinician clearance sought. There is no medical
  screening step anywhere in the process.
- **33 critical conduct flags** including: repeated offers to falsify invoice
  descriptions for tax write-offs; advising a prospect to buy before a divorce
  settlement so his ex-wife wouldn't get half; a sales manager instructing reps
  to take a card on file from prospects who said they can't pay.
- **PCI exposure**: a full card number, name, email and home address dictated
  onto a recording and preserved in the stored transcript (Richard Claessen,
  2026-06-23).
- Recordings are stopped at the moment of payment — cuts both ways, some closes
  missing and at least one recorded "close" where no payment was ever made.

## Decisions Made

- **Scope**: trailing 3 months only. Set in `data/rules.json` →
  `corpus_window`. 97 Feb–Apr calls are extracted and on disk but excluded from
  metrics; widening is a one-line change, zero re-extraction.
- **Close rule**: verbal agreement + payment link sent = closed.
- **Internal calls**: routed to `data/internal_calls/`, never in a close-rate
  denominator, but still flagged.
- **No identities on the dashboard.** Prospect and closer names removed from
  every section. Payload is also pseudonymised (first name + last initial),
  financials banded, locations coarsened to state/country.
- **Drive renames NOT run.** The files belong to info@primalinstinct.net, not
  us. Manifest and Apps Script are ready if that changes.

## In Progress / Not Started

Nothing is half-finished. Extraction is complete for the window.

## Next Up (in rough priority order)

1. **Controlled tactic vocabulary + re-score.** `response_tactic` was left as
   free text in `docs/SCORING_SPEC.md`, so agents phrased each one differently
   and almost nothing reaches a countable threshold. The objections table has a
   caveat saying so. Fixing it needs a fixed vocabulary and a re-score pass
   (re-reads transcripts — real cost). Only worth it if "which rebuttal
   actually works" matters.
2. **Flag threshold recalibration.** Every single call carries at least one
   flag. Clusters are trustworthy; individual medium/low flags are probably
   over-flagged. Worth a calibration pass before anyone acts on raw counts.
3. **Halo bias measurement.** Adherence and outcome were scored in the same
   pass. Re-score a random ~60-call subsample with agents that never see the
   outcome, compare, and publish the delta.
4. Optionally widen the window back to February (one line in
   `data/rules.json`).

## Blockers / Decisions Needed

- **The 204 critical flags need a human decision**, particularly the clinical
  screening gap and the invoicing pitch. The first is a process fix (one
  screening question with a stop rule). The second is not a training issue.
- **primal.jtylerray.com is publicly reachable.** Vercel project is set to
  `ssoProtection: all_except_custom_domains`. No identities on the page now, so
  risk is low, but it is a deliberate choice — flip to `all` to gate it.
- Vercel is **not** connected to the repo for auto-deploy. Deploys are manual:
  `npx vercel --prod --yes` from the project root.

## Key Files

| Path | What |
|---|---|
| `docs/EXTRACTION_SPEC.md` | Worker contract + controlled vocabularies. Read first. |
| `docs/SCORING_SPEC.md` | Adherence, pillars, anchors, unmet demand, ICP, flags |
| `docs/rename.gs` | Drive rename Apps Script (dryRun / apply / revert) — unrun |
| `data/rules.json` | Corpus window, close rule, junk floor, speaker resolution |
| `data/playbook.json` | Kettlebell Body sales script, machine-readable |
| `data/icp.json` | ICP quoted from a live call + per-call fit |
| `data/manifest.json` | All 837 Drive files with ids, sizes, dates |
| `src/build_db.py` | Builds SQLite + web payload. All rollups live here. |
| `src/make_batches.py` | Splits manifest into worker batches; resumable |
| `src/workflows/extract.js` | The fan-out workflow (1 agent per 12-call batch) |
| `web/index.html` | Dashboard |
| `web/brand.css` | Brand tokens measured from the live site |

## How To Resume A Run

```bash
python3 src/make_batches.py     # only emits what is still outstanding
# then Workflow({scriptPath: "src/workflows/extract.js", args: ["batch_001", ...]})
python3 src/build_db.py
python3 src/build_standalone.py
git add -A && git commit && git push
npx vercel --prod --yes
```

## Gotchas Learned The Hard Way

- Agents emit type variation constantly — strings where numbers belong, nulls
  in required fields. `_num()` in build_db coerces; treat every numeric field
  from an extraction as untrusted.
- The web payload was 24 MB before slimming. `slim_payload()` caps illustrative
  lists; computed rates still use the full data. Don't remove the caps.
- ~5% of Drive titles name the **wrong prospect**. Deal merging is unaffected
  (it keys on the transcript-derived name) but anything joining on title is not.
- The speaker label `Andrew Jin (Primal Instinct)` is Andrew Musial. Rep
  attribution must come from folder + content, never the Fathom label.
- Reps are sequential cohorts, not a concurrent team — rep comparison is
  confounded with time period except for the Apr–May and Jun–Jul overlaps.
