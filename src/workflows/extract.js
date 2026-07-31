export const meta = {
  name: 'primal-extract',
  description: 'Extract + score Primal Instinct call transcripts, one agent per batch',
  whenToUse: 'Run the Primal Instinct corpus extraction. Pass batch ids as args, or omit for all pending batches.',
  phases: [
    { title: 'Extract', detail: 'one agent per batch: read transcripts, write extraction + scoring files' },
  ],
}

// args may arrive as an array, a JSON-encoded string, or a comma/space list.
// Normalise all three rather than assuming, since a bad shape kills the run
// before a single agent starts.
function resolveBatches(a) {
  let v = a
  if (typeof v === 'string') {
    try { v = JSON.parse(v) } catch { v = v.split(/[,\s]+/).filter(Boolean) }
  }
  if (typeof v === 'string') v = [v]
  if (!Array.isArray(v)) v = []
  return v.filter(x => typeof x === 'string' && x.startsWith('batch_'))
}

const BATCHES = resolveBatches(args)
if (!BATCHES.length) throw new Error('No batch ids supplied. Pass e.g. ["batch_001","batch_002"].')

const SCHEMA = {
  type: 'object',
  required: ['batch_id', 'attempted', 'written', 'calls'],
  properties: {
    batch_id: { type: 'string' },
    attempted: { type: 'number' },
    written: { type: 'number', description: 'calls with all 4 files written' },
    calls: {
      type: 'array',
      items: {
        type: 'object',
        required: ['call_id', 'prospect', 'rep', 'disposition'],
        properties: {
          call_id: { type: 'string' },
          prospect: { type: 'string' },
          rep: { type: 'string' },
          disposition: { type: 'string' },
          confidence: { type: 'number' },
          avatar: { type: 'string' },
          stage: { type: 'string' },
          adherence_note: { type: 'string' },
        },
      },
    },
    internal: { type: 'number', description: 'internal calls routed out of the sales corpus' },
    flags: {
      type: 'object',
      description: 'count of integrity flags written, by severity',
      properties: {
        critical: { type: 'number' }, high: { type: 'number' },
        medium: { type: 'number' }, low: { type: 'number' },
      },
    },
    skipped: { type: 'array', items: { type: 'string' }, description: 'file ids skipped and why' },
    anomalies: { type: 'array', items: { type: 'string' }, description: 'only things NOT already captured as a flag' },
  },
}

const PROMPT = bid => `
You are extracting sales-call data for the Primal Instinct call audit.

REPO: /Users/user/kettlebell   (all paths below are relative to it)

STEP 1 — read these in full before touching any transcript:
  docs/EXTRACTION_SPEC.md    the record schema + controlled vocabularies
  docs/SCORING_SPEC.md       adherence, pillars, anchors, unmet demand, ICP
  data/playbook.json         the sales script you score against
  data/icp.json              the "stated" block only — the ICP criteria

STEP 2 — read your batch: data/batches/${bid}.json
It lists Drive file ids, titles, rep folder, call dates and sizes.

STEP 3 — load the Drive reader:
  ToolSearch with query "select:mcp__claude_ai_Google_Drive__read_file_content"

STEP 4 — for EACH file in the batch, in order:
  a. read_file_content with its Drive file id
  b. decide: is this a SALES call or an INTERNAL call?

  SALES CALL → five files:
    data/calls/<call_id>.json                     (EXTRACTION_SPEC section 3)
    data/scores/parts/<call_id>.adherence.json    (SCORING_SPEC section A)
    data/scores/parts/<call_id>.signals.json      (SCORING_SPEC section B)
    data/scores/parts/<call_id>.icp.json          (SCORING_SPEC section C)
    data/scores/parts/<call_id>.flags.json        (SCORING_SPEC section D)

  INTERNAL CALL → two files, and NOTHING in data/calls/:
    data/internal_calls/<call_id>.json            (EXTRACTION_SPEC, non-sales block)
    data/scores/parts/<call_id>.flags.json        (SCORING_SPEC section D)

  Roughly a quarter of this corpus is internal — team meetings, closing
  training, manager 1-1s, tool demos, setter debriefs. Tells: two
  "(Primal Instinct)" speakers and no prospect, a title naming two staff,
  "1-1", "training", "Sales Team Meeting", "Gameplan", a tool demo. Getting
  this wrong poisons every close rate, so decide deliberately.

  Use the Write tool. Every file must be valid JSON — no trailing commas, no
  comments, no markdown fences.

  Take source.drive_file_id, source.original_title (VERBATIM, including any
  trailing spaces or HTML entities), source.drive_folder and
  source.file_size_bytes from the batch record. Take call.date from call_date.

CRITICAL RULES — this is where quality is won or lost:
  * Use the controlled vocabularies EXACTLY. Never invent a category name. If
    nothing fits use "other" and put your proposed label in the text field.
  * Read speaker ROLE FROM CONTENT, not from the speaker label. Diarization
    swaps speakers constantly in this corpus. The rep is whoever is running
    the call, whatever the label says.
  * Files under 2000 bytes are junk — skip, list in "skipped", write nothing.
  * Some transcripts are internal (rep x rep, "Gameplan", manager syncs). Set
    call.stage to "internal", fill what you can, leave goals/pains/objections
    empty. Do not force a sales shape onto them.
  * disposition "closed" = paid OR (verbally agreed AND payment link sent).
  * Never invent a fact. Absent means null.
  * Score the process on what the rep DID, not on how the call ended. A sloppy
    call that closed still scores badly.
  * WRITE THE FLAGS FILE FOR EVERY CALL, empty if nothing applies. Integrity
    flags are the audit half of this job and the highest-value output. Pay
    particular attention to clinical_risk: a prospect disclosing cancer,
    recent surgery, spinal injury, a connective-tissue disorder, uncontrolled
    hypertension or active treatment, who is then sold or moved toward loaded
    ballistic kettlebell work with nobody asking whether a clinician cleared
    it. Flag it every time. Do not soften it because the rep was warm or the
    prospect was enthusiastic. Also flag any price other than $6,000/6mo or
    $9,000/12mo, exactly as it arose.

STEP 5 — return the structured summary. Keep "adherence_note" to one short
clause. NEVER paste transcript text or full JSON into your response — the
files on disk are the deliverable.
`

phase('Extract')

const results = await parallel(BATCHES.map(bid => () => agent(PROMPT(bid), {
  label: `extract:${bid}`,
  phase: 'Extract',
  schema: SCHEMA,
})))

const ok = results.filter(Boolean)
const attempted = ok.reduce((s, r) => s + (r.attempted || 0), 0)
const written = ok.reduce((s, r) => s + (r.written || 0), 0)
const internal = ok.reduce((s, r) => s + (r.internal || 0), 0)
const calls = ok.flatMap(r => r.calls || [])
const tally = (arr, key) => arr.reduce((a, c) => { a[c[key]] = (a[c[key]] || 0) + 1; return a }, {})
const flags = ok.reduce((a, r) => {
  for (const k of ['critical', 'high', 'medium', 'low']) a[k] = (a[k] || 0) + ((r.flags || {})[k] || 0)
  return a
}, {})

log(`${written}/${attempted} written · ${internal} internal · ` +
    `flags: ${flags.critical || 0} critical, ${flags.high || 0} high`)
if (ok.length < BATCHES.length) log(`WARNING: ${BATCHES.length - ok.length} batch(es) returned nothing`)

// Anomalies are capped — they are free text and a long run can return
// hundreds. Flags on disk are the durable record; this is just a heads-up.
const anomalies = ok.flatMap(r => r.anomalies || [])

return {
  batches_requested: BATCHES.length,
  batches_returned: ok.length,
  failed_batches: BATCHES.filter((b, i) => !results[i]),
  attempted,
  written,
  internal,
  flag_counts: flags,
  dispositions: tally(calls, 'disposition'),
  avatars: tally(calls, 'avatar'),
  stages: tally(calls, 'stage'),
  anomalies_sample: anomalies.slice(0, 12),
  anomalies_total: anomalies.length,
  skipped: ok.flatMap(r => r.skipped || []),
}
