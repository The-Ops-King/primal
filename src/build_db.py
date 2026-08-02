#!/usr/bin/env python3
"""
Build the Primal Instinct call-intelligence store.

Reads every extraction in data/calls/*.json and produces:
  - data/primal.db   : normalized SQLite, one row per entity, for ad-hoc SQL
  - web/data.json    : the denormalized payload the dashboard renders

Re-runnable. Drops and rebuilds every table on each run, so the JSON files
stay the single source of truth.
"""
import json
import pathlib
import re
import sqlite3
import sys
from math import comb
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
CALLS_DIR = ROOT / "data" / "calls"
DB_PATH = ROOT / "data" / "primal.db"
WEB_DATA = ROOT / "web" / "data.json"

SCHEMA = """
DROP TABLE IF EXISTS calls;
DROP TABLE IF EXISTS goals;
DROP TABLE IF EXISTS pains;
DROP TABLE IF EXISTS objections;
DROP TABLE IF EXISTS offer_tiers;
DROP TABLE IF EXISTS adherence;
DROP TABLE IF EXISTS phase_scores;
DROP TABLE IF EXISTS check_scores;
DROP TABLE IF EXISTS objection_plays;

CREATE TABLE calls (
    call_id                 TEXT PRIMARY KEY,
    call_date               TEXT NOT NULL,
    stage                   TEXT,
    sequence_position       INTEGER,
    duration_min_est        INTEGER,

    rep_name                TEXT,
    rep_role                TEXT,
    rep_location            TEXT,

    setter_code             TEXT,
    setter_name             TEXT,

    prospect_name           TEXT,
    prospect_name_source    TEXT,
    prospect_location       TEXT,
    prospect_age            INTEGER,
    prospect_occupation     TEXT,
    prospect_json           TEXT,

    avatar                  TEXT,
    avatar_confidence       REAL,

    disposition             TEXT,
    outcome_confidence      REAL,
    cash_collected_usd      REAL,
    cash_expected_usd       REAL,
    next_step               TEXT,

    offer_presented         INTEGER,
    payment_plan_offered    INTEGER,
    payment_plan_live       INTEGER,

    original_title          TEXT,
    display_title           TEXT,
    drive_file_id           TEXT,
    drive_folder            TEXT,
    file_size_bytes         INTEGER,

    diarization_reliability TEXT,
    quality_notes           TEXT
);

CREATE TABLE goals (
    call_id  TEXT NOT NULL REFERENCES calls(call_id),
    text     TEXT,
    category TEXT
);

CREATE TABLE pains (
    call_id  TEXT NOT NULL REFERENCES calls(call_id),
    text     TEXT,
    category TEXT,
    severity TEXT
);

CREATE TABLE objections (
    call_id         TEXT NOT NULL REFERENCES calls(call_id),
    type            TEXT,
    raw_quote       TEXT,
    ts              TEXT,
    rep_response    TEXT,
    response_tactic TEXT,
    resolved        INTEGER
);

CREATE TABLE offer_tiers (
    call_id   TEXT NOT NULL REFERENCES calls(call_id),
    months    INTEGER,
    price_usd REAL
);

CREATE TABLE adherence (
    call_id       TEXT PRIMARY KEY REFERENCES calls(call_id),
    rep_name      TEXT,
    disposition   TEXT,
    adherence_pct REAL,
    points_earned REAL,
    points_possible REAL,
    notes         TEXT
);

CREATE TABLE phase_scores (
    call_id    TEXT NOT NULL REFERENCES calls(call_id),
    phase_id   TEXT,
    phase_name TEXT,
    score      TEXT,
    score_num  REAL,
    weight     REAL,
    evidence   TEXT
);

CREATE TABLE check_scores (
    call_id  TEXT NOT NULL REFERENCES calls(call_id),
    phase_id TEXT,
    check_id TEXT,
    value    TEXT
);

CREATE TABLE objection_plays (
    call_id         TEXT NOT NULL REFERENCES calls(call_id),
    play            TEXT,
    trigger_present INTEGER,
    ran             TEXT,
    detail          TEXT
);

CREATE TABLE deals (
    deal_id       TEXT PRIMARY KEY,
    prospect_name TEXT,
    call_count    INTEGER,
    first_date    TEXT,
    last_date     TEXT,
    reps          TEXT,
    avatar        TEXT,
    disposition   TEXT,
    cash_usd      REAL,
    call_ids      TEXT
);

CREATE INDEX idx_deals_avatar ON deals(avatar);
CREATE INDEX idx_deals_disp ON deals(disposition);
CREATE INDEX idx_phase ON phase_scores(phase_id);
CREATE INDEX idx_play ON objection_plays(play, ran);
CREATE INDEX idx_obj_type ON objections(type);
CREATE INDEX idx_obj_resolved ON objections(resolved);
CREATE INDEX idx_calls_disp ON calls(disposition);
CREATE INDEX idx_calls_avatar ON calls(avatar);
CREATE INDEX idx_pains_cat ON pains(category);
CREATE INDEX idx_goals_cat ON goals(category);
"""


def flag(value):
    """SQLite has no bool. Preserve NULL rather than coercing unknown to false."""
    return None if value is None else int(bool(value))


def load_calls():
    files = sorted(CALLS_DIR.glob("*.json"))
    if not files:
        sys.exit(f"No extractions found in {CALLS_DIR}")
    out = []
    for f in files:
        with f.open() as fh:
            out.append(json.load(fh))
    return out


def insert(conn, rec):
    src = rec.get("source", {})
    call = rec.get("call", {})
    rep = rec.get("rep", {})
    setter = rec.get("setter", {})
    pros = rec.get("prospect", {})
    avatar = rec.get("avatar", {})
    outcome = rec.get("outcome", {})
    offer = rec.get("offer", {})
    quality = rec.get("quality", {})

    conn.execute(
        """INSERT INTO calls VALUES (
            :call_id, :call_date, :stage, :sequence_position, :duration_min_est,
            :rep_name, :rep_role, :rep_location,
            :setter_code, :setter_name,
            :prospect_name, :prospect_name_source, :prospect_location,
            :prospect_age, :prospect_occupation, :prospect_json,
            :avatar, :avatar_confidence,
            :disposition, :outcome_confidence, :cash_collected_usd,
            :cash_expected_usd, :next_step,
            :offer_presented, :payment_plan_offered, :payment_plan_live,
            :original_title, :display_title, :drive_file_id, :drive_folder,
            :file_size_bytes, :diarization_reliability, :quality_notes
        )""",
        {
            "call_id": rec["call_id"],
            "call_date": call.get("date"),
            "stage": call.get("stage"),
            "sequence_position": call.get("sequence_position"),
            "duration_min_est": call.get("duration_min_est"),
            "rep_name": rep.get("name"),
            "rep_role": rep.get("role"),
            "rep_location": rep.get("location"),
            "setter_code": setter.get("code"),
            "setter_name": setter.get("name"),
            "prospect_name": pros.get("name"),
            "prospect_name_source": pros.get("name_source"),
            "prospect_location": pros.get("location"),
            "prospect_age": pros.get("age"),
            "prospect_occupation": pros.get("occupation"),
            "prospect_json": json.dumps(pros),
            "avatar": avatar.get("assigned"),
            "avatar_confidence": avatar.get("confidence"),
            "disposition": outcome.get("disposition"),
            "outcome_confidence": outcome.get("confidence"),
            "cash_collected_usd": outcome.get("cash_collected_usd"),
            "cash_expected_usd": outcome.get("cash_expected_usd"),
            "next_step": outcome.get("next_step"),
            "offer_presented": flag(offer.get("presented")),
            "payment_plan_offered": flag(offer.get("payment_plan_offered")),
            "payment_plan_live": flag(offer.get("payment_plan_structured_live")),
            "original_title": src.get("original_title"),
            "display_title": src.get("display_title"),
            "drive_file_id": src.get("drive_file_id"),
            "drive_folder": src.get("drive_folder"),
            "file_size_bytes": src.get("file_size_bytes"),
            "diarization_reliability": quality.get("diarization_reliability"),
            "quality_notes": quality.get("notes"),
        },
    )

    cid = rec["call_id"]
    conn.executemany(
        "INSERT INTO goals VALUES (?,?,?)",
        [(cid, g.get("text"), g.get("category")) for g in rec.get("goals", [])],
    )
    conn.executemany(
        "INSERT INTO pains VALUES (?,?,?,?)",
        [(cid, p.get("text"), p.get("category"), p.get("severity")) for p in rec.get("pains", [])],
    )
    conn.executemany(
        "INSERT INTO objections VALUES (?,?,?,?,?,?,?)",
        [
            (cid, o.get("type"), o.get("raw_quote"), o.get("timestamp"),
             o.get("rep_response"), o.get("response_tactic"), flag(o.get("resolved")))
            for o in rec.get("objections", [])
        ],
    )
    conn.executemany(
        "INSERT INTO offer_tiers VALUES (?,?,?)",
        [(cid, _num(t.get("months")), _num(t.get("price_usd")))
         for t in offer.get("tiers", [])],
    )


SCORE_NUM = {"hit": 1.0, "partial": 0.5, "miss": 0.0}


def load_json(path):
    with path.open() as fh:
        return json.load(fh)


def merge_parts(base, suffix, key):
    """Fold per-call score files into the aggregate structure.

    Workers write one file per call under data/scores/parts/ rather than
    appending to a shared document — with dozens of agents running at once,
    a single file would race and lose writes. Later files win on call_id so a
    re-run of one call cleanly supersedes the earlier version.
    """
    parts_dir = ROOT / "data" / "scores" / "parts"
    merged = {e["call_id"]: e for e in base.get(key, []) if e.get("call_id")}
    if parts_dir.exists():
        for f in sorted(parts_dir.glob(f"*.{suffix}.json")):
            try:
                rec = load_json(f)
            except json.JSONDecodeError:
                print(f"  WARN unreadable, skipped: {f.name}")
                continue
            if rec.get("call_id"):
                merged[rec["call_id"]] = rec
    base[key] = list(merged.values())
    return base


def score_adherence(conn, playbook, adherence):
    """Weighted phase scoring. not_applicable phases drop out of the denominator
    so a rep is never penalised for a phase the call could not reach."""
    weights = {p["id"]: p["weight"] for p in playbook["phases"]}
    names = {p["id"]: p["name"] for p in playbook["phases"]}
    summary = {}

    for entry in adherence["calls"]:
        cid = entry["call_id"]
        earned = possible = 0.0

        for pid, pdata in entry["phases"].items():
            score = pdata.get("score")
            w = weights.get(pid, 0)
            num = SCORE_NUM.get(score)
            if num is not None:
                earned += num * w
                possible += w
            conn.execute(
                "INSERT INTO phase_scores VALUES (?,?,?,?,?,?,?)",
                (cid, pid, names.get(pid, pid), score, num, w, pdata.get("evidence")),
            )
            for chk_id, val in (pdata.get("checks") or {}).items():
                conn.execute("INSERT INTO check_scores VALUES (?,?,?,?)", (cid, pid, chk_id, val))

        for play in entry.get("objection_plays", []):
            conn.execute(
                "INSERT INTO objection_plays VALUES (?,?,?,?,?)",
                (cid, play.get("play"), flag(play.get("trigger_present")),
                 play.get("ran"), play.get("detail")),
            )

        pct = round(earned / possible * 100, 1) if possible else None
        conn.execute(
            "INSERT INTO adherence VALUES (?,?,?,?,?,?,?)",
            (cid, entry.get("rep"), entry.get("disposition"), pct,
             round(earned, 1), round(possible, 1), entry.get("notes")),
        )
        summary[cid] = {
            "adherence_pct": pct,
            "points_earned": round(earned, 1),
            "points_possible": round(possible, 1),
            "phases": entry["phases"],
            "objection_plays": entry.get("objection_plays", []),
            "notes": entry.get("notes"),
        }
    return summary


def canonical(name):
    """Deal key. Strips device suffixes and punctuation so a prospect who
    rejoins from a phone does not become a second person."""
    n = (name or "").lower()
    n = re.sub(r"['’]s (iphone|ipad|android|phone|laptop|computer)[\w\s]*", " ", n)
    n = re.sub(r"[^a-z\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def build_deals(conn, records):
    """Collapse calls into one deal per prospect, per rules.json. The deal takes
    the outcome of its last call chronologically — the furthest the conversation got."""
    groups = {}
    for r in records:
        groups.setdefault(canonical(r["prospect"]["name"]), []).append(r)

    deals = []
    for key, calls in sorted(groups.items()):
        calls.sort(key=lambda c: (c["call"]["date"], c["call"].get("sequence_position") or 0))
        last = calls[-1]
        cash = last["outcome"].get("cash_collected_usd") or 0
        deal = {
            "deal_id": key.replace(" ", "-"),
            "prospect_name": last["prospect"]["name"],
            "call_count": len(calls),
            "first_date": calls[0]["call"]["date"],
            "last_date": last["call"]["date"],
            "reps": sorted({c["rep"]["name"] for c in calls}),
            "avatar": last["avatar"]["assigned"],
            "disposition": last["outcome"]["disposition"],
            "cash_usd": cash,
            "call_ids": [c["call_id"] for c in calls],
        }
        deals.append(deal)
        conn.execute(
            "INSERT INTO deals VALUES (?,?,?,?,?,?,?,?,?,?)",
            (deal["deal_id"], deal["prospect_name"], deal["call_count"],
             deal["first_date"], deal["last_date"], ", ".join(deal["reps"]),
             deal["avatar"], deal["disposition"], deal["cash_usd"],
             ", ".join(deal["call_ids"])),
        )
    return deals


def build_rollups(records, deals, playbook, adherence):
    """Corpus-level aggregates. This is the point of the exercise — every number
    here answers 'how are we doing overall', not 'how did this one call go'."""
    phase_meta = {p["id"]: p for p in playbook["phases"]}
    check_text = {c["id"]: c["text"]
                  for p in playbook["phases"] for c in p.get("checks", [])}
    check_phase = {c["id"]: p["id"]
                   for p in playbook["phases"] for c in p.get("checks", [])}

    # ---- phase + check rollups ----
    phases, checks = {}, {}
    for entry in adherence["calls"]:
        for pid, pdata in entry["phases"].items():
            p = phases.setdefault(pid, {"hit": 0, "partial": 0, "miss": 0,
                                        "not_applicable": 0, "earned": 0.0, "possible": 0.0})
            s = pdata.get("score")
            if s in p:
                p[s] += 1
            num = SCORE_NUM.get(s)
            if num is not None:
                p["earned"] += num
                p["possible"] += 1
            for cid, val in (pdata.get("checks") or {}).items():
                c = checks.setdefault(cid, {"hit": 0, "partial": 0, "miss": 0, "not_applicable": 0})
                if val in c:
                    c[val] += 1

    phase_rollup = []
    for pid, meta in phase_meta.items():
        p = phases.get(pid)
        if not p:
            continue
        denom = p["earned"] and p["possible"] or p["possible"]
        pct = round(p["earned"] / p["possible"] * 100, 1) if p["possible"] else None
        kids = []
        for c in meta.get("checks", []):
            cs = checks.get(c["id"])
            if not cs:
                continue
            d = cs["hit"] + cs["partial"] + cs["miss"]
            kids.append({
                "check_id": c["id"], "text": c["text"], **cs,
                "pct": round((cs["hit"] + cs["partial"] * .5) / d * 100, 1) if d else None,
            })
        phase_rollup.append({
            "phase_id": pid, "name": meta["name"], "intent": meta["intent"],
            "weight": meta["weight"], "adherence_pct": pct,
            "hit": p["hit"], "partial": p["partial"], "miss": p["miss"],
            "not_applicable": p["not_applicable"],
            "calls_scored": int(p["possible"]), "checks": kids,
        })
    # Left in playbook order — these are sections of a script that runs in
    # sequence, so reordering them by score makes the table unreadable as a
    # process. The weakest is surfaced separately instead.
    ranked = sorted((p for p in phase_rollup if p["adherence_pct"] is not None),
                    key=lambda x: x["adherence_pct"])
    weakest_id = ranked[0]["phase_id"] if ranked else None

    # ---- objection play rollup ----
    play_meta = {p["id"]: p for p in playbook.get("objection_plays", [])}
    plays = {}
    for entry in adherence["calls"]:
        for pl in entry.get("objection_plays", []):
            if not pl.get("trigger_present") or pl.get("play") in (None, "none"):
                continue
            k = pl["play"]
            r = plays.setdefault(k, {"play": k, "trigger": play_meta.get(k, {}).get("trigger", k),
                                     "triggered": 0, "hit": 0, "partial": 0, "miss": 0, "instances": []})
            r["triggered"] += 1
            if pl.get("ran") in r:
                r[pl["ran"]] += 1
            r["instances"].append({"rep": entry.get("rep"), "ran": pl.get("ran"),
                                   "detail": pl.get("detail")})
    play_rollup = sorted(plays.values(), key=lambda x: -x["triggered"])

    # ---- avatar rollup (deal-level, so close rate is real) ----
    av = {}
    for d in deals:
        a = av.setdefault(d["avatar"], {"avatar": d["avatar"], "deals": 0, "closed": 0,
                                        "follow_up": 0, "lost": 0, "cash": 0.0, "names": []})
        a["deals"] += 1
        if d["disposition"] in a:
            a[d["disposition"]] += 1
        a["cash"] += d["cash_usd"] or 0
        a["names"].append(d["prospect_name"])
    for a in av.values():
        a["close_rate"] = round(a["closed"] / a["deals"] * 100, 1) if a["deals"] else 0
    avatar_rollup = sorted(av.values(), key=lambda x: (-x["close_rate"], -x["deals"]))

    # ---- pain / goal rollups ----
    def bucket(kind):
        out = {}
        for r in records:
            for item in r.get(kind, []):
                cat = item.get("category") or "uncategorised"
                b = out.setdefault(cat, {"category": cat, "count": 0, "calls": set(),
                                         "severities": {}, "items": []})
                b["count"] += 1
                b["calls"].add(r["call_id"])
                sev = item.get("severity")
                if sev:
                    b["severities"][sev] = b["severities"].get(sev, 0) + 1
                b["items"].append({"text": item.get("text"), "severity": sev,
                                   "prospect": r["prospect"]["name"],
                                   "disposition": r["outcome"]["disposition"]})
        for b in out.values():
            b["calls"] = len(b["calls"])
        return sorted(out.values(), key=lambda x: -x["count"])

    # ---- demand rollup: what prospects actually want, for marketing ----
    # Deal-level so "close rate when present" is meaningful. This is the
    # targeting view: which stated goals and pains bring in people who buy.
    def demand(kind):
        by_deal = {}
        call_index = {r["call_id"]: r for r in records}
        for d in deals:
            cats = set()
            for cid in d["call_ids"]:
                for item in call_index[cid].get(kind, []):
                    if item.get("category"):
                        cats.add(item["category"])
            for cat in cats:
                b = by_deal.setdefault(cat, {"category": cat, "deals": 0, "closed": 0,
                                             "cash": 0.0, "names": []})
                b["deals"] += 1
                b["names"].append(d["prospect_name"])
                if d["disposition"] == "closed":
                    b["closed"] += 1
                    b["cash"] += d["cash_usd"] or 0
        n = len(deals) or 1
        for b in by_deal.values():
            b["share"] = round(b["deals"] / n * 100)
            b["close_rate"] = round(b["closed"] / b["deals"] * 100) if b["deals"] else 0
        return sorted(by_deal.values(), key=lambda x: (-x["deals"], -x["close_rate"]))

    return {
        "phases": phase_rollup,
        "weakest_phase_id": weakest_id,
        "objection_plays": play_rollup,
        "avatars": avatar_rollup,
        "pains": bucket("pains"),
        "goals": bucket("goals"),
        "demand_goals": demand("goals"),
        "demand_pains": demand("pains"),
    }


def fisher_right(a, b, c, d):
    """One-tailed Fisher exact: probability of a split at least this extreme
    under the null that the feature is unrelated to outcome. Exact, so it is
    valid at tiny n — which is the whole point here."""
    n, r1, c1 = a + b + c + d, a + b, a + c
    if not n or not c1 or r1 > n:
        return 1.0
    denom = comb(n, c1)
    return sum(comb(r1, x) * comb(n - r1, c1 - x)
               for x in range(a, min(r1, c1) + 1)) / denom


def build_discriminators(records, deals, playbook, adherence):
    """What actually separates closed from not-closed.

    Every feature is evaluated at DEAL level, because that is where outcome
    lives. A feature counts as present if it appears in any call of the deal.
    """
    check_text = {c["id"]: c["text"]
                  for p in playbook["phases"] for c in p.get("checks", [])}
    check_phase = {c["id"]: p["name"]
                   for p in playbook["phases"] for c in p.get("checks", [])}
    phase_name = {p["id"]: p["name"] for p in playbook["phases"]}
    adh = {e["call_id"]: e for e in adherence["calls"]}
    by_call = {r["call_id"]: r for r in records}

    # CIRCULAR FEATURES — excluded, not ranked.
    # Phase 11 is Payment & Onboarding. It is only reachable when a rep is
    # closing, and taking payment / booking onboarding is part of how a deal
    # gets marked closed in the first place. So "closed deals ran phase 11"
    # is a restatement of the close rule, not a finding about it. Leaving it
    # in would put a guaranteed 100%-vs-0% row at the top of the table and
    # crowd out the features that actually carry information.
    CIRCULAR_PHASES = {"P11"}
    circular = {("phase", p) for p in CIRCULAR_PHASES} | \
               {("phase_full", p) for p in CIRCULAR_PHASES} | \
               {("check", cid) for cid, pid in
                {c["id"]: p["id"] for p in playbook["phases"] for c in p.get("checks", [])}.items()
                if pid in CIRCULAR_PHASES}

    # feature sets per deal
    feats, outcome = {}, {}
    for d in deals:
        did = d["deal_id"]
        outcome[did] = d["disposition"]
        f = feats.setdefault(did, set())
        for cid in d["call_ids"]:
            r = by_call[cid]
            for p in r.get("pains", []):
                f.add(("pain", p.get("category")))
            for g in r.get("goals", []):
                f.add(("goal", g.get("category")))
            for o in r.get("objections", []):
                f.add(("objection", o.get("type")))
                if o.get("resolved"):
                    f.add(("objection_resolved", o.get("type")))
            off = r.get("offer", {})
            if off.get("payment_plan_offered"):
                f.add(("structural", "payment_plan_offered"))
            if off.get("payment_plan_structured_live"):
                f.add(("structural", "payment_plan_structured_live"))
            if r.get("setter", {}).get("name"):
                f.add(("structural", "came_via_setter"))
            if (r["call"].get("sequence_position") or 1) > 1:
                f.add(("structural", "multi_call_sequence"))
            if not r["call"].get("prospect_named_in_title"):
                f.add(("structural", "untitled_recording"))
            e = adh.get(cid)
            if e:
                for pid, pdata in e["phases"].items():
                    if pdata.get("score") in ("hit", "partial"):
                        f.add(("phase", pid))
                    if pdata.get("score") == "hit":
                        f.add(("phase_full", pid))
                    for chk, val in (pdata.get("checks") or {}).items():
                        if val == "hit":
                            f.add(("check", chk))
                for pl in e.get("objection_plays", []):
                    if pl.get("trigger_present") and pl.get("play") not in (None, "none"):
                        if pl.get("ran") in ("hit", "partial"):
                            f.add(("play", pl["play"]))

    closed = [d for d in outcome if outcome[d] == "closed"]
    other = [d for d in outcome if outcome[d] != "closed"]
    lost = [d for d in outcome if outcome[d] == "lost"]

    LABELS = {
        "pain": lambda k: f"Pain: {k.replace('_',' ')}",
        "goal": lambda k: f"Goal: {k.replace('_',' ')}",
        "objection": lambda k: f"Objection raised: {k.replace('_',' ')}",
        "objection_resolved": lambda k: f"Objection resolved: {k.replace('_',' ')}",
        "phase": lambda k: f"Ran section: {phase_name.get(k,k)}",
        "phase_full": lambda k: f"Ran section IN FULL: {phase_name.get(k,k)}",
        "check": lambda k: f"{check_phase.get(k,'')} → {check_text.get(k,k)}",
        "play": lambda k: f"Ran objection play {k}",
        "structural": lambda k: k.replace("_", " ").capitalize(),
    }

    universe = sorted({f for s in feats.values() for f in s} - circular)
    rows = []
    for kind, key in universe:
        a = sum(1 for d in closed if (kind, key) in feats[d])
        b = len(closed) - a
        c = sum(1 for d in other if (kind, key) in feats[d])
        dd = len(other) - c
        if a + c == 0:
            continue
        cp = round(a / len(closed) * 100) if closed else 0
        op = round(c / len(other) * 100) if other else 0
        lost_with = sum(1 for d in lost if (kind, key) in feats[d])

        if cp == 100 and op == 0:
            stmt = (f"Every closed deal ({a}/{len(closed)}) had this. "
                    f"No non-closed deal did (0/{len(other)}).")
        elif op == 100 and cp == 0:
            stmt = (f"Every non-closed deal ({c}/{len(other)}) had this. "
                    f"No closed deal did (0/{len(closed)}).")
        else:
            stmt = (f"{cp}% of closed ({a}/{len(closed)}) vs "
                    f"{op}% of non-closed ({c}/{len(other)}).")

        rows.append({
            "kind": kind, "key": key,
            "label": LABELS.get(kind, lambda k: k)(key),
            "closed_with": a, "closed_n": len(closed),
            "other_with": c, "other_n": len(other),
            "lost_with": lost_with, "lost_n": len(lost),
            "closed_pct": cp, "other_pct": op, "diff": cp - op,
            "support": a + c,
            "p_enriched": round(fisher_right(a, b, c, dd), 4),
            "p_depleted": round(fisher_right(c, dd, a, b), 4),
            "perfect": (cp == 100 and op == 0) or (op == 100 and cp == 0),
            "statement": stmt,
        })

    rows.sort(key=lambda r: (-abs(r["diff"]), -r["support"]))
    perfect = [r for r in rows if r["perfect"]]

    # How many perfect separators would we expect from noise alone? For a
    # feature present in k of n deals, the chance it lands exactly on the
    # closed set is 1/C(n,k). Summing that over the real prevalence profile
    # gives the expected false-positive count — the honest denominator.
    n_deals = len(deals)
    expected_noise = 0.0
    for r in rows:
        k = r["closed_with"] + r["other_with"]
        if 0 < k < n_deals:
            expected_noise += 1 / comb(n_deals, k) if k == len(closed) else 0
    # The best p-value the current group sizes can physically produce. A
    # perfectly clean separator still only reaches 1/C(n, n_closed). If that
    # floor is above .05, NOTHING in this section can reach significance no
    # matter how clean it looks, and the honest move is to say so up front.
    p_floor = 1 / comb(n_deals, len(closed)) if 0 < len(closed) < n_deals else 1.0

    # Deals needed before a perfect separator could clear p<.05, holding the
    # observed close rate. Answers "how much more data do I need".
    rate = len(closed) / n_deals if n_deals else .4
    deals_needed = None
    for cand in range(n_deals + 1, 400):
        k = max(1, round(cand * rate))
        if k < cand and 1 / comb(cand, k) <= .05:
            deals_needed = cand
            break

    return {
        "groups": {"closed": len(closed), "not_closed": len(other), "lost": len(lost)},
        "features_tested": len(rows),
        "perfect_separators": len(perfect),
        "expected_perfect_by_chance": round(expected_noise, 1),
        "p_floor": round(p_floor, 4),
        "deals_needed_for_significance": deals_needed,
        "excluded_circular": sorted(
            {f"{phase_name.get(p, p)} (section {p})" for p in CIRCULAR_PHASES}),
        "min_p": min([r["p_enriched"] for r in rows], default=1.0),
        "top_favours_close": [r for r in rows if r["diff"] > 0][:40],
        "top_favours_loss": [r for r in rows if r["diff"] < 0][:40],
        "all": rows,
    }


FUNNEL = [
    ("connected",   "Call connected"),
    ("discovery",   "Discovery run"),
    ("deep_why",    "Deep why reached"),
    ("commitment",  "Commitment secured"),
    ("offer",       "Offer presented"),
    ("price",       "Price stated"),
    ("objection",   "Objection cleared"),
    ("close",       "Close attempted"),
    ("closed",      "Closed"),
]


def build_offer_signals(records, deals, playbook, adherence, signals, icp):
    """Offer-side and funnel rollups: where deals die, duration vs outcome,
    price anchors, pillar reactions, unmet demand, ICP fit and offer
    consistency."""
    adh = {e["call_id"]: e for e in adherence["calls"]}
    sig = {e["call_id"]: e for e in signals["calls"]}
    by_call = {r["call_id"]: r for r in records}

    def stage_of(call):
        """Furthest funnel stage a single call reached."""
        cid = call["call_id"]
        a = adh.get(cid, {}).get("phases", {})
        got = lambda pid, *ok: a.get(pid, {}).get("score") in ok
        offer = call.get("offer", {})
        objs = call.get("objections", [])
        reached = 1                                            # connected
        if got("P2", "hit", "partial") or got("P3", "hit", "partial"):
            reached = 2
        if got("P3", "hit"):
            reached = 3
        if got("P6", "hit", "partial"):
            reached = 4
        if offer.get("presented"):
            reached = max(reached, 5)
        if offer.get("tiers"):
            reached = max(reached, 6)
        blocking = [o for o in objs if not o.get("resolved")]
        if offer.get("tiers") and not blocking:
            reached = max(reached, 7)
        if a.get("P11", {}).get("score") not in (None, "not_applicable"):
            reached = max(reached, 8)
        if call["outcome"]["disposition"] == "closed":
            reached = 9
        return reached

    # deal-level furthest stage = best any of its calls got to
    deal_stage = {}
    for d in deals:
        deal_stage[d["deal_id"]] = max(stage_of(by_call[c]) for c in d["call_ids"])

    funnel = []
    total = len(deals) or 1
    for i, (key, label) in enumerate(FUNNEL, start=1):
        reached = sum(1 for s in deal_stage.values() if s >= i)
        died = sum(1 for s in deal_stage.values() if s == i) if i < len(FUNNEL) else 0
        funnel.append({
            "stage": i, "key": key, "label": label,
            "reached": reached, "pct": round(reached / total * 100),
            "died_here": died,
            "deals_died": [d["prospect_name"] for d in deals
                           if deal_stage[d["deal_id"]] == i and i < len(FUNNEL)],
        })

    # ---- objection rollup: type -> top tactics, with resolve rate each ----
    # Rendering every tactic string produced an unreadable wall; what matters
    # is which handful of responses get used and which of them actually work.
    obj = {}
    for r in records:
        for o in r.get("objections", []):
            t = o.get("type") or "other"
            b = obj.setdefault(t, {"type": t, "n": 0, "resolved": 0, "tactics": {}})
            b["n"] += 1
            if o.get("resolved"):
                b["resolved"] += 1
            tac = (o.get("response_tactic") or "unspecified").replace("_", " ")
            tb = b["tactics"].setdefault(tac, {"tactic": tac, "n": 0, "resolved": 0})
            tb["n"] += 1
            if o.get("resolved"):
                tb["resolved"] += 1
    objection_rollup = []
    for b in obj.values():
        tacs = list(b["tactics"].values())
        for t in tacs:
            t["rate"] = round(t["resolved"] / t["n"] * 100) if t["n"] else 0
        # "none" and "unspecified" record the absence of a tactic, not a
        # tactic — ranking them as a best response is meaningless.
        NON_TACTIC = {"none", "unspecified", "n/a", "na", "-", ""}
        common = [t for t in tacs
                  if t["n"] >= 3 and t["tactic"].strip().lower() not in NON_TACTIC]
        common.sort(key=lambda x: (-x["rate"], -x["n"]))
        objection_rollup.append({
            "type": b["type"], "n": b["n"], "resolved": b["resolved"],
            "rate": round(b["resolved"] / b["n"] * 100) if b["n"] else 0,
            "distinct_tactics": len(tacs),
            "best": common[:3],
            "worst": [t for t in reversed(common)][:3],
        })
    objection_rollup.sort(key=lambda x: -x["n"])

    # ---- duration buckets ----
    BUCKETS = [(0, 20, "Under 20 min"), (20, 30, "20–29 min"), (30, 45, "30–44 min"),
               (45, 60, "45–59 min"), (60, 75, "60–74 min"), (75, 10**6, "75+ min")]
    dur_buckets = []
    for lo, hi, label in BUCKETS:
        grp = [r for r in records
               if (r["call"].get("duration_min_est") or 0) >= lo
               and (r["call"].get("duration_min_est") or 0) < hi]
        if not grp:
            continue
        closed_n = sum(1 for r in grp if r["outcome"]["disposition"] == "closed")
        dur_buckets.append({
            "label": label, "lo": lo, "n": len(grp), "closed": closed_n,
            "close_rate": round(closed_n / len(grp) * 100),
            "share": round(len(grp) / len(records) * 100),
        })

    # ---- duration vs outcome ----
    duration = sorted(
        ({"prospect": r["prospect"]["name"], "rep": r["rep"]["name"],
          "minutes": r["call"].get("duration_min_est"),
          "disposition": r["outcome"]["disposition"],
          "stage": stage_of(r)}
         for r in records if r["call"].get("duration_min_est")),
        key=lambda x: -x["minutes"])
    closed_mins = [x["minutes"] for x in duration if x["disposition"] == "closed"]
    other_mins = [x["minutes"] for x in duration if x["disposition"] != "closed"]
    duration_summary = {
        "closed_avg": round(sum(closed_mins) / len(closed_mins)) if closed_mins else None,
        "other_avg": round(sum(other_mins) / len(other_mins)) if other_mins else None,
        "longest": duration[0] if duration else None,
        "shortest": duration[-1] if duration else None,
    }

    # ---- pillar reactions ----
    pmeta = {p["id"]: p for p in signals["pillars"]}
    pill = {}
    for e in signals["calls"]:
        disp = by_call[e["call_id"]]["outcome"]["disposition"]
        for pr in e.get("pillar_reactions", []):
            b = pill.setdefault(pr["pillar"], {
                "pillar": pr["pillar"], "name": pmeta[pr["pillar"]]["name"],
                "order": pmeta[pr["pillar"]]["order"], "reactions": {}, "items": []})
            b["reactions"][pr["reaction"]] = b["reactions"].get(pr["reaction"], 0) + 1
            b["items"].append({**pr, "disposition": disp,
                               "prospect": by_call[e["call_id"]]["prospect"]["name"]})
    for b in pill.values():
        shown = sum(v for k, v in b["reactions"].items() if k != "not_presented")
        friction = b["reactions"].get("confused", 0) + b["reactions"].get("objected", 0)
        b["presented"] = shown
        b["friction"] = friction
        b["friction_pct"] = round(friction / shown * 100) if shown else 0
        b["clean_pct"] = round((b["reactions"].get("accepted", 0)
                                + b["reactions"].get("enthusiastic", 0)) / shown * 100) if shown else 0
    pillars = sorted(pill.values(), key=lambda x: x["order"])

    # ---- anchors ----
    anchors = []
    for e in signals["calls"]:
        r = by_call[e["call_id"]]
        for a in e.get("anchors", []):
            anchors.append({**a, "prospect": r["prospect"]["name"],
                            "disposition": r["outcome"]["disposition"]})
    anchor_dirs = {}
    for a in anchors:
        k = a["direction"]
        g = anchor_dirs.setdefault(k, {"direction": k, "n": 0, "closed": 0})
        g["n"] += 1
        if a["disposition"] == "closed":
            g["closed"] += 1
    for g in anchor_dirs.values():
        g["close_rate"] = round(g["closed"] / g["n"] * 100) if g["n"] else 0

    # ---- unmet demand ----
    unmet = []
    for e in signals["calls"]:
        r = by_call[e["call_id"]]
        for u in e.get("unmet_demand", []):
            unmet.append({**u, "prospect": r["prospect"]["name"],
                          "disposition": r["outcome"]["disposition"]})
    unmet_by_verdict = {}
    for u in unmet:
        unmet_by_verdict.setdefault(u["verdict"], []).append(u)

    # ---- offer consistency ----
    guarantees, tiers_seen = [], {}
    for r in records:
        g = r.get("offer", {}).get("guarantee_mentioned")
        guarantees.append({"rep": r["rep"]["name"], "guarantee": g,
                           "presented": bool(r.get("offer", {}).get("presented"))})
        for t in r.get("offer", {}).get("tiers", []):
            # Agents occasionally emit a tier with a null or string months /
            # price. Coerce, and drop anything that still will not resolve —
            # a malformed tier must not take the whole build down.
            months, price = _num(t.get("months")), _num(t.get("price_usd"))
            if months is None or price is None:
                continue
            months = int(months)
            tiers_seen.setdefault(months, {"months": months,
                                           "price_usd": price, "calls": 0})
            tiers_seen[months]["calls"] += 1
    distinct_g = {g["guarantee"] for g in guarantees if g["guarantee"]}
    consistency = {
        "guarantees": guarantees,
        "distinct_versions": len(distinct_g),
        "never_mentioned": sum(1 for g in guarantees if not g["guarantee"]),
        "calls_with_offer": sum(1 for g in guarantees if g["presented"]),
        "tiers": sorted(tiers_seen.values(), key=lambda x: x["months"]),
        "total_calls": len(records),
    }

    # ---- ICP ----
    fit_counts = {}
    for a in icp["assessments"]:
        cid = a["call_id"]
        disp = by_call[cid]["outcome"]["disposition"] if cid in by_call else None
        b = fit_counts.setdefault(a["fit"], {"fit": a["fit"], "n": 0, "closed": 0, "who": []})
        b["n"] += 1
        b["who"].append(by_call[cid]["prospect"]["name"] if cid in by_call else cid)
        if disp == "closed":
            b["closed"] += 1
    for b in fit_counts.values():
        b["close_rate"] = round(b["closed"] / b["n"] * 100) if b["n"] else 0
    icp_out = {
        "stated": icp["stated"],
        "fit_counts": sorted(fit_counts.values(),
                             key=lambda x: {"core": 0, "edge": 1, "outside": 2}.get(x["fit"], 3)),
        "assessments": [{**a,
                         "prospect": by_call[a["call_id"]]["prospect"]["name"]
                         if a["call_id"] in by_call else a["call_id"],
                         "disposition": by_call[a["call_id"]]["outcome"]["disposition"]
                         if a["call_id"] in by_call else None}
                        for a in icp["assessments"]],
        "observations": icp["observations"],
    }

    return {
        "funnel": funnel,
        "duration": duration[:40],
        "duration_buckets": dur_buckets,
        "objection_types": objection_rollup,
        "duration_summary": duration_summary,
        "pillars": pillars,
        "anchors": anchors,
        "anchor_directions": sorted(anchor_dirs.values(), key=lambda x: -x["n"]),
        "unmet_demand": unmet,
        "unmet_by_verdict": unmet_by_verdict,
        "offer_consistency": consistency,
        "icp": icp_out,
    }


# ---------------------------------------------------------------------------
# Buckets.
#
# Three of the extracted vocabularies came back as free text: anchor `type`
# (852 distinct strings across 1,513 anchors), unmet-demand `want` (1,283
# distinct across 1,283 records) and, less severely, the pain and goal
# categories (26 and 25). At that cardinality nothing reaches a countable
# threshold and every table becomes an enumeration. These maps fold the long
# tail into a handful of themes so the page can show buckets with rates.
#
# Matching is first-hit over an ordered list, so the more specific themes are
# listed first. Anything that matches nothing lands in "other" — which is
# reported, not hidden, because a large "other" is the signal that the map
# needs another theme rather than that the tail is small.
# ---------------------------------------------------------------------------

ANCHOR_THEMES = [
    ("our_own_tier", "Our own cheaper tier",
     "They were shown, or found out about, a lower Primal price point and "
     "anchored to that instead of the one being sold.",
     ("internal_lower_tier", "own_lower_tier", "lower_tier", "own_product",
      "one_month_tier", "internal_", "in_house", "rep_introduced_discount",
      "rep_offered")),
    ("cheaper_competitor", "A named competitor's price",
     "A specific rival coach, app or programme with a number attached. The "
     "hardest anchor to move, because it is concrete.",
     ("competitor", "rival", "incumbent", "named_", "other_provider",
      "market_rate", "industry_", "alternative_provider", "competitive_process",
      "local_market", "peer_comparison")),
    ("free_or_diy", "Free or do-it-yourself",
     "YouTube, a spreadsheet, an app they already own, or simply doing it "
     "themselves. The comparison is against $0, not against a competitor.",
     ("free", "diy", "self_directed", "self_serve", "self_suffic", "youtube",
      "content", "information", "substitute", "app_", "self_programming",
      "owned_alternative", "employer_provided", "never_paid")),
    ("pays_for_coaching", "Already pays for coaching",
     "Prior or current spend on coaches, mentors or health. This anchor "
     "supports the price — it establishes that paying an expert is normal.",
     ("existing_", "prior_", "current_", "precedent", "self_investment",
      "paid_coaching", "health_spend", "coaching_spend", "tax", "founder_",
      "social_proof", "sunk", "willingness", "reframe_upward", "peer_proof",
      "value_acceptance", "habitual_coaching", "creator_", "quality_signal",
      "price_as_quality", "opportunity_cost", "write_off", "assets",
      "career_", "runs_his_own")),
    ("money_tight", "Money is tight or already committed",
     "Cash spoken for elsewhere, thin credit, or lumpy income. Not a value "
     "objection — a sequencing one, and it responds to terms, not to pitch.",
     ("competing_", "household", "capital", "discretionary", "commitment",
      "liquidity", "income_volatility", "cash", "membership", "debt",
      "credit", "financing", "affordability", "retirement_income",
      "income_cadence", "macro_conditions")),
    ("budget_ceiling", "A number they arrived with",
     "A price they had already decided was right before the call — a budget, "
     "a monthly figure, an expected pricing model.",
     ("price_expect", "expectation", "budget", "pricing_model", "subscription",
      "monthly", "currency", "ceiling", "quote", "stated_", "expected_price",
      "price_point", "price_scale", "unit_price", "no_reference",
      "cost_of_living", "own_pricing")),
]

UNMET_THEMES = [
    ("nutrition", "Nutrition and diet",
     "Food, macros and eating habits — asked for as part of the programme "
     "rather than as a separate thing.",
     ("nutrition", "diet", "macro", "meal", "food", "eating", "recipe",
      "calorie", "supplement")),
    ("clinical", "Injury, rehab and clinical scope",
     "Whether the programme can be run around a live medical constraint. This "
     "is the bucket that overlaps the clinical-risk flags.",
     ("injur", "rehab", "physio", "shoulder", "knee", "back pain", "surger",
      "hernia", "rotator", "labrum", "disc", "arthrit", "cancer", "thyroid",
      "medication", "pregnan", "postpartum", "menopaus", "clearance",
      "clinician", "doctor", "physical therap", "condition")),
    ("access", "More direct access to a coach",
     "One-to-one time, live form checks, technique correction, in-person "
     "contact. A request for a higher-touch version of what is already sold.",
     ("one-to-one", "one to one", "1:1", "in-person", "in person", "form check",
      "live call", "personal train", "face-to-face", "direct access",
      "weekly call", "video review", "check-in", "form", "technique",
      "live ", "feedback", "correction", "watch", "supervis", "accountab")),
    ("proof", "Evidence it works for someone like them",
     "Case studies, results, track record — proof at their age, their body "
     "type or their starting point. A trust request, not a product one.",
     ("evidence", "proof", "case stud", "testimonial", "track record",
      "results for", "people like", "someone like", "year-old", "success stor",
      "research", "science", "data on", "before and after", "credential")),
    ("integration", "Fit it around what they already do",
     "Run the programme alongside an existing sport, gym routine or coach "
     "rather than replacing it.",
     ("alongside", "integrat", "combine", "existing training", "existing "
      "routine", "supplement", "in addition to", "on top of", "current "
      "programme", "current program", "keep doing")),
    ("partner", "Include a partner or family",
     "Train with a spouse, partner or family member, or get a household rate. "
     "A packaging question the offer has no answer for.",
     ("wife", "husband", "spouse", "partner ", "couple", "together", "family",
      "daughter", "son ", "household")),
    ("commercial", "Cheaper, shorter or more flexible terms",
     "Not a product request — a request to buy the same product differently. "
     "Almost always a positioning or packaging question.",
     ("price", "payment", "monthly", "subscription", "cheaper", "discount",
      "trial", "shorter", "month-to-month", "pause", "cancel", "refund",
      "guarantee", "instal", "deposit", "commit")),
    ("sport", "Sport or hobby specific programming",
     "Training that serves something they already do. The programme is "
     "general strength; they want it pointed at their thing.",
     ("running", "runner", "golf", "jiu", "bjj", "martial", "climb", "hik",
      "cycl", "swim", "danc", "tennis", "ski", "row", "sport", "marathon",
      "triathlon", "football", "soccer", "surf", "yoga", "pilates", "lifting")),
    ("logistics", "Equipment, travel and scheduling",
     "Practical delivery: what they own, where they train, when they can do "
     "it. Cheap to solve and often already solved.",
     ("equipment", "barbell", "dumbbell", "gym access", "travel", "schedul",
      "time zone", "offline", "app", "video", "weight set", "home gym")),
]

PAIN_GROUPS = [
    ("body", "The body has stopped cooperating",
     "Injury, medical constraint and age. The pain is physical and already "
     "diagnosed — they are not guessing that something is wrong.",
     ("injury", "medical", "aging", "mobility", "injury_prevention")),
    ("consistency", "Cannot stay consistent",
     "They know what to do and do not do it. Time, work and motivation "
     "collapse into one complaint: it never lasts.",
     ("consistency", "motivation", "accountability_gap", "time_scarcity",
      "work_stress")),
    ("guidance", "Do not know what to do",
     "Competence anxiety, a fragmented stack of apps and programmes, and "
     "dissatisfaction with what they are currently running.",
     ("competence_anxiety", "confidence", "program_fit", "fragmented_solutions",
      "training_barrier", "training_dissatisfaction", "fear_doubt")),
    ("diet_sleep", "Diet and recovery are the unsolved part",
     "Training is handled; what they eat and how they sleep is not.",
     ("nutrition_habit", "sleep")),
    ("spillover", "It is costing them outside the gym",
     "Mood, relationships, self-image and the things they used to be able to "
     "do. This is the emotional register — the copy source.",
     ("emotional", "mental_health", "relationship", "hobby_performance",
      "sustainability", "energy_performance")),
]

GOAL_GROUPS = [
    ("longevity", "Still be doing this at seventy",
     "Function, mobility and staying unbroken. The dominant want in this "
     "corpus and the one the offer is actually built for.",
     ("longevity_function", "longevity_family", "mobility", "injury_prevention",
      "sustainability", "aging", "injury_confidence")),
    ("look", "Look the part",
     "Fat loss, muscle and appearance. Stated less often than longevity but "
     "rarely absent underneath it.",
     ("fat_loss", "appearance", "muscle_gain")),
    ("perform", "Perform at something",
     "Strength, endurance and a sport or hobby they want to be better at.",
     ("strength", "hobby_performance", "energy_performance", "endurance",
      "pregnancy_prep")),
    ("identity", "Become someone who shows up",
     "Consistency, confidence and being the example at home. An identity "
     "goal, not an outcome one — and the one that sells a year, not a month.",
     ("consistency", "confidence", "family_role_model", "relationship",
      "accountability", "accountability_gap")),
    ("fit_in", "Make it fit a full life",
     "Convenience above all: it has to survive a real week.",
     ("convenience", "nutrition_habit", "sleep")),
]

OBJECTION_GROUPS = [
    ("money", "Money",
     "Price, affordability, cashflow timing and cheaper alternatives — every "
     "objection where the blocker is the number.",
     ("price", "affordability", "timing_cashflow", "value_vs_cheaper_alternative")),
    ("stall", "Not now",
     "No stated blocker, just deferral. The hardest group to resolve because "
     "there is nothing concrete to answer.",
     ("think_about_it", "timing_other", "life_event_conflict")),
    ("third_party", "Someone else decides",
     "A spouse, a partner or unresolved doubt about the provider. The "
     "decision is not the prospect's alone to make on the call.",
     ("spouse_consult", "trust_provider")),
    ("fit", "Will it work for me",
     "Medical fit, fear of harm, unfamiliarity with kettlebells, and whether "
     "it is worth it at reduced scope. A confidence problem, not a money one.",
     ("fear_doubt", "program_fit", "medical_program_fit", "risk_of_harm",
      "value_at_reduced_scope", "unfamiliar_modality", "program_longevity_proof",
      "timing_medical", "icp_mismatch")),
]

# Flag themes. Greedy Jaccard clustering on the summary text splits one
# systemic issue into five near-identical clusters whenever the agents phrase
# it differently — the page showed "Pricing deviation" five separate times,
# each with a per-incident sentence as its heading. These are the actual
# recurring problems, matched on keywords, so one issue reads as one row with
# a count no matter how it was worded.
FLAG_THEMES = [
    ("no_clearance", "Loaded training sold without clinician clearance",
     "A prospect disclosed an injury, condition or active treatment and was "
     "sold loaded or ballistic kettlebell work anyway, with no clearance "
     "sought and no stop rule anywhere in the process.",
     ("clearance", "clinician", "cleared", "sign-off", "physician approval",
      "medical approval", "without consulting")),
    ("no_screening", "Disclosed condition, no screening question",
     "A medical disclosure passed without a single follow-up question. There "
     "is no screening step in the script for it to have failed.",
     ("no screening", "screening question", "never asked about", "disclosed",
      "did not ask", "no follow-up question", "unexplored")),
    ("clinical_claim", "Unqualified clinical claims",
     "A rep asserting a medical or rehabilitative outcome they are not "
     "qualified to promise — that the programme will fix, heal or resolve a "
     "diagnosed condition.",
     ("unqualified", "clinical claim", "medical advice", "diagnos", "cure",
      "heal", "fix the", "rehabilitat", "therapeutic claim")),
    ("unsanctioned_tier", "Prices outside the sanctioned list",
     "Tiers and figures presented as standard that do not appear in the "
     "documented offer — improvised three-month, one-month and trial "
     "structures, priced live on the call.",
     ("tier", "outside the", "improvised", "price list", "sanctioned",
      "not in the", "invented", "unsanctioned", "off-menu")),
    ("plan_terms", "Payment plan terms differ call to call",
     "Instalment totals, deposits and differential-credit mechanics stated "
     "differently to different prospects, and often with the total never "
     "stated at all.",
     ("instalment", "installment", "payment plan", "differential", "deposit",
      "total was never", "never stated", "monthly figure", "per month")),
    ("guarantee", "The guarantee is not a fixed thing",
     "Refund and guarantee language varies by whoever is on the call, when it "
     "is mentioned at all.",
     ("guarantee", "refund", "money back", "money-back")),
    ("recording_stopped", "Recording stopped at the moment of payment",
     "The transaction and any terms stated during it are absent from the "
     "corpus. This biases the close rate in both directions and cannot be "
     "resolved without a CRM join.",
     ("stopped the recording", "recording stops", "recording was stopped",
      "recording ends", "cuts off", "stopped at", "truncated recording")),
    ("file_conflation", "One file, two calls — or the wrong name on it",
     "Drive files containing two unrelated sales calls back to back, and "
     "titles naming a different prospect than the transcript. Anything "
     "counting or joining on files is wrong by this amount.",
     ("single drive file", "two entirely separate", "two separate",
      "back to back", "title", "misnamed", "mislabel", "wrong prospect",
      "folder", "file contains")),
    ("attribution", "Speaker labels cannot be trusted",
     "Diarisation errors and mislabelled speakers, including one label that "
     "names the wrong rep entirely. Rep attribution has to come from folder "
     "and content, never the transcript label.",
     ("diarization", "diarisation", "speaker", "attribution", "inverts",
      "label", "misattribut")),
    ("payment_pressure", "Pressure and card-on-file tactics",
     "Taking a card from prospects who said they could not pay, deposits "
     "framed as commitment devices, and manager instruction to do so.",
     ("card on file", "card details", "credit card", "take a card",
      "cannot pay", "can't pay", "pressure", "manager instruct",
      "credit limit", "open a credit")),
    ("financial_advice", "Advice on the prospect's finances",
     "Steering purchases around divorce settlements, tax write-offs and "
     "invoice descriptions. Not a training issue.",
     ("write-off", "write off", "tax", "invoice", "divorce", "settlement",
      "business expense", "financial advice", "borrow")),
    ("pii", "Personal data captured on the recording",
     "Card numbers, addresses and contact details dictated onto a call and "
     "preserved in the stored transcript.",
     ("card number", "full card", "home address", "personal data", "pci",
      "postcode", "date of birth", "sensitive personal")),
    ("consent", "Recording and disclosure gaps",
     "Calls recorded without a stated disclosure, third parties captured "
     "incidentally, and claims made without the qualifying context.",
     ("consent", "disclosure", "recorded without", "not disclosed",
      "no disclosure", "notice", "third party", "third pa", "bystander",
      "unrelated conversation")),
    ("nutrition_advice", "Dietary advice given alongside medication",
     "Fasting windows, eating protocols and supplement guidance offered to "
     "prospects on active medication, by people not qualified to give it.",
     ("fasting", "eating window", "glp", "nutrition advice", "diet advice",
      "supplement", "calorie", "macro", "eating protocol")),
    ("coercion", "Coached pressure technique",
     "Refusing to accept a stated answer, holding the position until the "
     "prospect complies, enlarging their goal to enlarge the sale, and "
     "keeping buyers on the phone until they pay. Coached, not improvised.",
     ("until they comply", "keep buyers", "on the phone until", "enlarge",
      "bigger goal", "refusing to accept", "does not accept", "hold the",
      "holding the position", "pressure", "push back until", "coached to",
      "override", "detach")),
    ("profiling", "Prospects profiled by who they are",
     "Country of origin, accent and demographic used as a proxy for ability "
     "to pay, with harder qualification prescribed on that basis.",
     ("country of origin", "nationality", "profile prospects", "demographic",
      "ethnic", "accent", "where they are from")),
    ("unverified_proof", "Unverified numbers used as proof",
     "Client counts and result figures presented as the primary trust asset "
     "with nothing behind them, in place of specific evidence.",
     ("unverified", "unsubstantiated", "trust asset", "no evidence",
      "cannot be verified", "client figure", "success rate", "testimonial")),
    ("process_skipped", "Documented steps skipped after the sale",
     "Agreements never signed live, onboarding steps missed, written terms "
     "promised and never sent. The process exists; it is not being run.",
     ("agreement", "onboarding", "never returned", "no confirmation",
      "not confirmed", "never sent", "promised", "signed", "written terms",
      "follow-up email")),
    ("policy_reversal", "A policy stated, then reversed",
     "Rules given as fixed to a prospect and abandoned within hours when the "
     "deal was at risk, or contradicted in the same breath. The pattern says "
     "there was no policy.",
     ("reversed", "no longer offered", "then offered", "contradict",
      "same breath", "one day after", "inconsistent", "reversal", "abandoned")),
    ("corpus_gaps", "Calls missing from the corpus entirely",
     "Selling calls absent while their onboarding call is present, and "
     "role-played sequences that read as genuine to any content classifier. "
     "Both bias the denominator.",
     ("not present", "missing", "post-sale", "no discoverable", "role-play",
      "role played", "not in the batch", "absent from the", "incomplete")),
    ("pipeline_definition", "Definitions that flatter the pipeline",
     "Disposition rules confining 'lost' to explicit refusals, so everything "
     "unresolved lands in follow-up and the pipeline never shrinks.",
     ("disposition", "crm", "pipeline", "inflates", "lost' to", "follow-up "
      "forever", "never closed out")),
]

ICP_CRITERIA = {
    "successful": "Already successful",
    "income": "Makes good money",
    "neglected_health": "Health is neglected, not a crisis",
    "good_to_great": "Wants good → great, not rescue",
    "not_deconditioned": "Not 50 lb overweight and gym-averse",
}


def _theme_of(text, themes, default="other"):
    """First-hit theme lookup over an ordered map. Returns the theme key."""
    t = (text or "").lower()
    for key, _label, _blurb, needles in themes:
        if any(nd in t for nd in needles):
            return key
    return default


def _named_first(buckets, size=lambda b: b["n"]):
    """Rank buckets by size, but always park the catch-all last. A large
    'everything else' sorting to position one reads as the headline finding
    when it is really the residue."""
    rows = sorted(buckets, key=lambda b: -size(b))
    named = [b for b in rows if b["key"] != "other"]
    other = [b for b in rows if b["key"] == "other"]
    return named + other


def _theme_shell(themes, extra_label="Everything else",
                 extra_blurb="Did not match any theme. A large share here "
                             "means the map needs another bucket."):
    """Ordered accumulator, one slot per theme plus a reported 'other'."""
    out = {k: {"key": k, "label": lab, "blurb": bl, "n": 0, "closed": 0, "deals": 0}
           for k, lab, bl, _ in themes}
    out["other"] = {"key": "other", "label": extra_label, "blurb": extra_blurb,
                    "n": 0, "closed": 0, "deals": 0}
    return out


def build_buckets(records, deals, signals, icp, rollups):
    """Fold the free-text long tails into themed buckets.

    Every rate here is computed over the whole corpus, not over the sampled
    lists the payload ships — that distinction matters, because slim_payload
    caps anchors at 60 of 1,513 and a rate taken from the sample would be a
    different number wearing the same label.
    """
    by_call = {r["call_id"]: r for r in records}

    # ---- anchors ----
    anchors = _theme_shell(
        ANCHOR_THEMES,
        extra_blurb="Anchors that matched no theme. Reported rather than "
                    "dropped so the bucket map can be judged.")
    a_total = 0
    for e in signals["calls"]:
        r = by_call.get(e["call_id"])
        if not r:
            continue
        closed = r["outcome"]["disposition"] == "closed"
        for a in e.get("anchors", []):
            key = _theme_of(f"{a.get('type','')} {a.get('competitor','') or ''}",
                            ANCHOR_THEMES)
            b = anchors[key]
            b["n"] += 1
            a_total += 1
            if a.get("direction") == "undercuts_price":
                b["undercuts"] = b.get("undercuts", 0) + 1
            if closed:
                b["closed"] += 1
    for b in anchors.values():
        b["undercuts"] = b.get("undercuts", 0)
        b["undercut_pct"] = round(b["undercuts"] / b["n"] * 100) if b["n"] else 0
        b["share"] = round(b["n"] / a_total * 100) if a_total else 0
        b["close_rate"] = round(b["closed"] / b["n"] * 100) if b["n"] else 0
    anchor_themes = _named_first(anchors.values())

    # ---- unmet demand ----
    unmet = _theme_shell(
        UNMET_THEMES,
        extra_blurb="Requests that matched no theme — one-offs, and the "
                    "genuinely idiosyncratic.")
    u_total = 0
    for e in signals["calls"]:
        r = by_call.get(e["call_id"])
        if not r:
            continue
        closed = r["outcome"]["disposition"] == "closed"
        for u in e.get("unmet_demand", []):
            key = _theme_of(u.get("want", ""), UNMET_THEMES)
            b = unmet[key]
            b["n"] += 1
            u_total += 1
            v = u.get("verdict") or "unvalidated"
            b.setdefault("verdicts", {})[v] = b.setdefault("verdicts", {}).get(v, 0) + 1
            if closed:
                b["closed"] += 1
    for b in unmet.values():
        b.setdefault("verdicts", {})
        b["share"] = round(b["n"] / u_total * 100) if u_total else 0
        gap = b["verdicts"].get("product_gap", 0)
        b["product_gap_pct"] = round(gap / b["n"] * 100) if b["n"] else 0
    unmet_themes = _named_first(unmet.values())

    # ---- pains / goals, grouped ----
    # Deal counts cannot be summed across the categories in a group — one deal
    # routinely carries two categories from the same group — so membership is
    # recounted per deal rather than added up from the category rollup.
    def group_rollup(kind, groups):
        """Deal-level group membership, counted once per deal per group."""
        call_index = {r["call_id"]: r for r in records}
        cat_to_group = {c: k for k, _l, _b, cats in groups for c in cats}
        acc = {k: {"deals": 0, "closed": 0, "cash": 0.0, "mentions": 0}
               for k, _l, _b, _c in groups}
        acc["other"] = {"deals": 0, "closed": 0, "cash": 0.0, "mentions": 0}
        for d in deals:
            keys = set()
            for cid in d["call_ids"]:
                for item in call_index[cid].get(kind, []):
                    cat = item.get("category")
                    if not cat:
                        continue
                    k = cat_to_group.get(cat, "other")
                    keys.add(k)
                    acc[k]["mentions"] += 1
            for k in keys:
                acc[k]["deals"] += 1
                if d["disposition"] == "closed":
                    acc[k]["closed"] += 1
                    acc[k]["cash"] += d["cash_usd"] or 0
        n = len(deals) or 1
        out = []
        meta = {k: (lab, bl, cats) for k, lab, bl, cats in groups}
        meta["other"] = ("Everything else",
                         "Categories outside the named groups, including the "
                         "uncategorised bucket.", ())
        for k, a in acc.items():
            lab, bl, cats = meta[k]
            out.append({
                "key": k, "label": lab, "blurb": bl,
                "categories": list(cats),
                "mentions": a["mentions"], "deals": a["deals"],
                "closed": a["closed"], "cash": a["cash"],
                "share": round(a["deals"] / n * 100),
                "close_rate": round(a["closed"] / a["deals"] * 100) if a["deals"] else 0,
            })
        return _named_first(out, size=lambda b: b["deals"])

    # ---- objections, grouped ----
    obj_index = {o["type"]: o for o in rollups.get("objection_types", [])}
    cat_to_group = {c: k for k, _l, _b, cats in OBJECTION_GROUPS for c in cats}
    obj_acc = {k: {"key": k, "label": lab, "blurb": bl, "types": [],
                   "n": 0, "resolved": 0}
               for k, lab, bl, _c in OBJECTION_GROUPS}
    obj_acc["other"] = {"key": "other", "label": "Everything else",
                        "blurb": "Objections that did not fall into a named "
                                 "group, including the uncategorised bucket.",
                        "types": [], "n": 0, "resolved": 0}
    for o in rollups.get("objection_types", []):
        b = obj_acc[cat_to_group.get(o["type"], "other")]
        b["n"] += o["n"]
        b["resolved"] += o["resolved"]
        b["types"].append({"type": o["type"], "n": o["n"], "rate": o["rate"]})
    obj_total = sum(b["n"] for b in obj_acc.values())
    for b in obj_acc.values():
        b["rate"] = round(b["resolved"] / b["n"] * 100) if b["n"] else 0
        b["share"] = round(b["n"] / obj_total * 100) if obj_total else 0
        b["types"].sort(key=lambda x: -x["n"])
    objection_groups = _named_first(obj_acc.values())

    # ---- ICP criteria, aggregated out of the per-prospect assessments ----
    fits = ("core", "edge", "outside")
    crit = {k: {"key": k, "label": lab, "matched": 0, "missed": 0,
                "by_fit": {f: {"matched": 0, "missed": 0} for f in fits}}
            for k, lab in ICP_CRITERIA.items()}
    scored = 0
    for a in icp["assessments"]:
        fit = a.get("fit")
        if fit not in fits:
            continue
        scored += 1
        for m in a.get("matches", []):
            if m in crit:
                crit[m]["matched"] += 1
                crit[m]["by_fit"][fit]["matched"] += 1
        for m in a.get("misses", []):
            if m in crit:
                crit[m]["missed"] += 1
                crit[m]["by_fit"][fit]["missed"] += 1
    for c in crit.values():
        d = c["matched"] + c["missed"]
        c["assessed"] = d
        c["miss_pct"] = round(c["missed"] / d * 100) if d else 0
    icp_criteria = sorted(crit.values(), key=lambda x: -x["miss_pct"])

    # ---- corpus summary ----
    # Everything the page used to derive by iterating the per-call array. With
    # these precomputed the payload no longer has to ship 422 call records for
    # a dashboard that reports only aggregates — and a per-call array nobody
    # renders is still a per-call array sitting on a public URL.
    def _mean(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals)) if vals else 0

    closed = [r for r in records if r["outcome"]["disposition"] == "closed"]
    other = [r for r in records if r["outcome"]["disposition"] != "closed"]
    adh_all = [r.get("adherence", {}).get("adherence_pct")
               for r in records if r.get("adherence")]
    adh_all = [a for a in adh_all if a is not None]

    def profile(group):
        objs = [o for r in group for o in r.get("objections", [])]
        has = lambda fn: sum(1 for r in group if fn(r))
        share = lambda k: round(has(k) / len(group) * 100) if group else 0
        return {
            "n": len(group),
            "adherence": _mean([r.get("adherence", {}).get("adherence_pct")
                                for r in group if r.get("adherence")]),
            "objections_resolved_pct": (round(sum(1 for o in objs if o.get("resolved"))
                                              / len(objs) * 100) if objs else 0),
            "plan_live_pct": share(lambda r: (r.get("offer") or {}).get("payment_plan_structured_live")),
            "plan_offered_pct": share(lambda r: (r.get("offer") or {}).get("payment_plan_offered")),
            "guarantee_pct": share(lambda r: (r.get("offer") or {}).get("guarantee_mentioned")),
            "avg_duration_min": _mean([r["call"].get("duration_min_est") for r in group]),
        }

    summary = {
        "calls": len(records),
        "closed": len(closed),
        "close_rate": round(len(closed) / len(records) * 100) if records else 0,
        "cash_usd": sum(r["outcome"].get("cash_collected_usd") or 0 for r in records),
        "high_confidence_closes": sum(1 for r in closed
                                      if (r["outcome"].get("confidence") or 0) >= 0.9),
        "adherence_mean": _mean(adh_all),
        "adherence_min": round(min(adh_all)) if adh_all else 0,
        "adherence_max": round(max(adh_all)) if adh_all else 0,
        "objections": sum(len(r.get("objections", [])) for r in records),
        "objections_resolved": sum(1 for r in records
                                   for o in r.get("objections", []) if o.get("resolved")),
        "closed_profile": profile(closed),
        "other_profile": profile(other),
    }

    return {
        "summary": summary,
        "anchor_themes": anchor_themes,
        "anchor_theme_total": a_total,
        "unmet_themes": unmet_themes,
        "unmet_theme_total": u_total,
        "pain_groups": group_rollup("pains", PAIN_GROUPS),
        "goal_groups": group_rollup("goals", GOAL_GROUPS),
        "objection_groups": objection_groups,
        "icp_criteria": icp_criteria,
        "icp_assessments_scored": scored,
    }


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def build_flags(records):
    """Integrity flags — the audit half of the audit.

    Loaded independently of the sales-call filter, because internal calls
    (team meetings, training, manager 1-1s) are excluded from the sales
    corpus but are exactly where the conduct and policy findings live.
    """
    parts = ROOT / "data" / "scores" / "parts"
    by_call = {r["call_id"]: r for r in records}
    internal_dir = ROOT / "data" / "internal_calls"
    internal = {}
    if internal_dir.exists():
        for f in internal_dir.glob("*.json"):
            try:
                rec = json.loads(f.read_text())
            except json.JSONDecodeError:
                continue
            if rec.get("call_id"):
                internal[rec["call_id"]] = rec

    flags = []
    if parts.exists():
        for f in sorted(parts.glob("*.flags.json")):
            try:
                doc = json.loads(f.read_text())
            except json.JSONDecodeError:
                print(f"  WARN unreadable flags file: {f.name}")
                continue
            cid = doc.get("call_id")
            rec, inte = by_call.get(cid), internal.get(cid)
            for fl in doc.get("flags", []):
                flags.append({
                    **fl,
                    "call_id": cid,
                    "source_type": "internal" if inte else "sales",
                    "rep": (rec or {}).get("rep", {}).get("name")
                           or (inte or {}).get("participants", [None])[0],
                    "prospect": (rec or {}).get("prospect", {}).get("name"),
                    "date": (rec or {}).get("call", {}).get("date") or (inte or {}).get("date"),
                    "title": (rec or inte or {}).get("source", {}).get("original_title"),
                })

    flags.sort(key=lambda x: (SEVERITY_ORDER.get(x.get("severity"), 9), x.get("date") or ""))
    clusters = cluster_flags(flags)

    # ---- themes ----
    # What the flags are actually about, independent of how each agent worded
    # it. cluster_flags splits one issue into several whenever the phrasing
    # drifts, so it cannot carry the summary view on its own.
    meta = {k: (lab, bl) for k, lab, bl, _ in FLAG_THEMES}
    meta["other"] = ("Everything else",
                     "Flags that matched no theme — the genuine long tail, "
                     "reported rather than dropped so the map can be judged.")
    th = {}
    for fl in flags:
        key = _theme_of(fl.get("summary"), FLAG_THEMES)
        lab, bl = meta[key]
        b = th.setdefault(key, {"key": key, "label": lab, "blurb": bl, "n": 0,
                                "calls": set(), "reps": set(), "severities": {},
                                "dates": []})
        b["n"] += 1
        if fl.get("call_id"):
            b["calls"].add(fl["call_id"])
        if fl.get("rep"):
            b["reps"].add(fl["rep"])
        sev = fl.get("severity") or "unknown"
        b["severities"][sev] = b["severities"].get(sev, 0) + 1
        if fl.get("date"):
            b["dates"].append(fl["date"])
    total_flags = len(flags) or 1
    for b in th.values():
        worst = min(b["severities"], key=lambda s: SEVERITY_ORDER.get(s, 9))
        b["severity"] = worst
        b["critical"] = b["severities"].get("critical", 0)
        b["high"] = b["severities"].get("high", 0)
        b["calls"] = len(b["calls"])
        b["reps"] = len(b["reps"])
        b["share"] = round(b["n"] / total_flags * 100)
        b["date_range"] = [min(b["dates"]), max(b["dates"])] if b["dates"] else None
        b.pop("dates", None)
    themes = _named_first(th.values())

    by_cat, by_sev = {}, {}
    for fl in flags:
        cat = fl.get("category", "other")
        c = by_cat.setdefault(cat, {"category": cat, "n": 0, "critical": 0, "high": 0,
                                    "medium": 0, "low": 0, "calls": set()})
        c["n"] += 1
        if fl.get("severity") in c:
            c[fl["severity"]] += 1
        if fl.get("call_id"):
            c["calls"].add(fl["call_id"])
        by_sev[fl.get("severity", "unknown")] = by_sev.get(fl.get("severity", "unknown"), 0) + 1
    for c in by_cat.values():
        c["calls"] = len(c["calls"])

    return {
        "all": flags,
        "total": len(flags),
        "by_severity": by_sev,
        "by_category": sorted(by_cat.values(),
                              key=lambda x: (-x["critical"], -x["high"], -x["n"])),
        "clusters": clusters,
        "themes": themes,
        "systemic": [c for c in clusters if c["n"] >= 3],
        "urgent": [f for f in flags if f.get("severity") in ("critical", "high")],
        "calls_flagged": len({f["call_id"] for f in flags if f.get("call_id")}),
        "internal_calls_reviewed": len(internal),
    }


STOP = set("""a an and are as at be been but by for from had has have in into is it its
of on or que that the their there they this to was were what when which who will with
prospect rep call client the was were a""".split())


def _sig(text):
    """Content-word signature of a flag summary, numbers stripped. Two agents
    describing the same systemic issue phrase it differently but reuse the
    same nouns, so token overlap clusters them where exact matching cannot."""
    words = re.findall(r"[a-z]{3,}", (text or "").lower())
    return frozenset(w for w in words if w not in STOP)


def cluster_flags(flags, threshold=0.45):
    """Greedy Jaccard clustering within each category.

    Without this, one systemic problem quoted in forty calls renders as forty
    rows and reads as forty problems. Bucketing by category first keeps the
    pairwise comparison cheap enough at corpus scale.
    """
    buckets = {}
    for f in flags:
        buckets.setdefault(f.get("category", "other"), []).append(f)

    clusters = []
    for cat, items in buckets.items():
        reps = []                      # (signature, cluster dict)
        for f in items:
            sig = _sig(f.get("summary"))
            best, best_score = None, 0.0
            for rsig, cl in reps:
                union = len(sig | rsig)
                score = len(sig & rsig) / union if union else 0.0
                if score > best_score:
                    best, best_score = cl, score
            if best is not None and best_score >= threshold:
                best["members"].append(f)
            else:
                cl = {"category": cat, "exemplar": f.get("summary"),
                      "members": [f]}
                reps.append((sig, cl))
                clusters.append(cl)

    for cl in clusters:
        m = cl["members"]
        worst = min(m, key=lambda x: SEVERITY_ORDER.get(x.get("severity"), 9))
        cl["n"] = len(m)
        cl["severity"] = worst.get("severity")
        cl["calls"] = sorted({x["call_id"] for x in m if x.get("call_id")})
        cl["reps"] = sorted({x["rep"] for x in m if x.get("rep")})
        cl["evidence"] = [e for x in m[:4] for e in (x.get("evidence") or [])][:6]
        cl["date_range"] = [min((x.get("date") or "") for x in m),
                            max((x.get("date") or "") for x in m)]
        cl["members"] = [{"call_id": x.get("call_id"), "date": x.get("date"),
                          "rep": x.get("rep"), "prospect": x.get("prospect"),
                          "summary": x.get("summary"), "severity": x.get("severity")}
                         for x in m]
    clusters.sort(key=lambda c: (SEVERITY_ORDER.get(c["severity"], 9), -c["n"]))
    return clusters


def _num(v):
    """Coerce whatever an agent wrote into a number, or None.

    Across hundreds of extractions these arrive as 1500, "1500", "$1,500",
    "1500 USD", "~1500" and "650-700". Crashing the whole build on one of
    them is not an option, so parse leniently and drop what will not parse.
    """
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(v))
    return float(m.group(0).replace(",", "")) if m else None


def _band(v, edges, fmt="${:,.0f}"):
    """Bucket a number into a labelled range."""
    v = _num(v)
    if v is None:
        return None
    lo = None
    for e in edges:
        if v < e:
            return (f"under {fmt.format(e)}" if lo is None
                    else f"{fmt.format(lo)}–{fmt.format(e)}")
        lo = e
    return f"{fmt.format(lo)}+"


# Surnames in this corpus that are also ordinary words. Replacing these on a
# word boundary would still corrupt prose ("Cash confirmed" → "C. confirmed"),
# and a bare common noun identifies nobody on its own. The full-name form is
# still replaced; only the standalone-surname pass skips these.
GENERIC_SURNAMES = {"cash", "moore", "white", "young", "price", "long", "best",
                    "free", "close", "call", "plan", "king", "strong", "green",
                    "brown", "black", "short", "rich", "small", "great", "day",
                    "week", "month", "year", "back", "core", "edge", "fit"}


def redact_payload(payload, records):
    """Pseudonymise the PUBLISHED payload only.

    data/calls/*.json and primal.db keep full fidelity on this machine; this
    strips identity from the copy that goes on the web. Three passes:

      1. Names   → 'Robyn Stillwater' becomes 'Robyn S.' everywhere, including
                   inside call_ids, deal_ids, file titles and free-text notes.
                   Rep and setter names are staff and are deliberately left.
      2. Money   → exact figures a prospect disclosed (cash on hand, monthly
                   surplus, credit score) become ranges. A credit score of 650
                   attached to a named person is the single most sensitive
                   field in the corpus.
      3. Place   → city-level location drops to state/country. 'Robyn S.' plus
                   a city plus a health condition re-identifies; 'Robyn S.'
                   plus a state does not.

    Names are replaced by whole-string scrub rather than field-by-field
    because they leak into derived keys (2026-07-23_robyn-stillwater_...)
    and into quoted evidence, and missing one of those is the whole ballgame.
    """
    subs, bare_surnames = {}, {}
    for r in records:
        full = (r["prospect"].get("name") or "").strip()
        parts = full.split()
        if len(parts) < 2:
            continue
        first, last = parts[0], parts[-1]
        short = f"{first} {last[0]}."
        subs[full] = short
        for extra in [full, " ".join(parts[:2]), f"{first} {last}"]:
            subs[extra] = short
        subs[full.lower().replace(" ", "-")] = f"{first}-{last[0]}".lower()
        subs["-".join(p.lower() for p in parts)] = f"{first}-{last[0]}".lower()
        if r["prospect"].get("aka"):
            subs[r["prospect"]["aka"]] = first
        # A bare surname in prose ("...what Stillwater actually said") still
        # identifies, so it is replaced too — but NOT by naive substring
        # replace. Some prospects are recorded as "Jason S", which put
        # subs["S"] = "S." and rewrote every capital S in the whole payload:
        # "Sport" became "S.port", "Stephanie" became "S.tephanie". Surnames
        # shorter than three characters carry no identifying information on
        # their own and are skipped; the rest match on a word boundary.
        if len(last) >= 3 and last.lower() not in GENERIC_SURNAMES:
            bare_surnames[last] = last[0] + "."

    blob = json.dumps(payload)
    for src in sorted(subs, key=len, reverse=True):       # longest first
        if src:
            blob = blob.replace(src, subs[src])
    for src in sorted(bare_surnames, key=len, reverse=True):
        blob = re.sub(rf"\b{re.escape(src)}\b", bare_surnames[src], blob)
    out = json.loads(blob)

    CASH = [500, 1000, 2500, 5000, 10000]
    SCORE = [580, 670, 740, 800]

    # Bucketing the structured field is not enough — the same figures get
    # quoted back in scoring prose ("cash on hand $1,500 ... credit score
    # 650"). Collect every figure a prospect actually disclosed and band it
    # wherever it appears in free text. Deal figures (the $6,000 offer, a
    # $1,200 instalment) are business data and are deliberately untouched.
    disclosed = {}
    for r in records:
        fin = (r.get("offer") or {}).get("prospect_financials") or {}
        for key, edges, fmt in (("available_now_usd", CASH, "${:,.0f}"),
                                ("monthly_surplus_usd", CASH, "${:,.0f}"),
                                ("credit_score", SCORE, "{:.0f}")):
            v = _num(fin.get(key))
            if v is None:
                continue
            band = _band(v, edges, fmt)
            disclosed[f"${v:,.0f}"] = f"the {band} band"
            disclosed[f"${v:.0f}"] = f"the {band} band"
            disclosed[str(int(v))] = f"the {band} band"

    FIN_WORDS = ("credit", "cash on hand", "surplus", "left over", "leftover",
                 "financial picture", "monthly")

    # One alternation, one pass, longest literal first. Substituting key by key
    # in a loop re-scans text a previous substitution just inserted: replacing
    # 1000 with "the $1,000–$2,500 band" leaves a literal "$2,500" in the
    # string, which the next key then bands again. That cascade produced
    # "the the $2,500–$5,000 band–the $5,000–the under 580 band,000 band band"
    # in the published copy. A single pass cannot match its own output.
    money_rx = (re.compile(r"(?<![\d,])(" +
                           "|".join(re.escape(s) for s in
                                    sorted(disclosed, key=len, reverse=True)) +
                           r")(?![\d])")
                if disclosed else None)

    def scrub_prose(node):
        if isinstance(node, dict):
            return {k: scrub_prose(v) for k, v in node.items()}
        if isinstance(node, list):
            return [scrub_prose(v) for v in node]
        if isinstance(node, str) and any(w in node.lower() for w in FIN_WORDS):
            return money_rx.sub(lambda m: disclosed[m.group(1)], node)
        return node

    if disclosed:
        out = scrub_prose(out)

    for c in out.get("calls", []):
        loc = c.get("prospect", {}).get("location")
        if loc:
            bits = [b.strip() for b in loc.split(",")]
            c["prospect"]["location"] = ", ".join(bits[-2:] if len(bits) > 2 else bits[-1:])
        fin = c.get("offer", {}).get("prospect_financials")
        if fin:
            c["offer"]["prospect_financials"] = {
                "available_now": _band(fin.get("available_now_usd"), CASH),
                "monthly_surplus": _band(fin.get("monthly_surplus_usd"), CASH),
                "has_savings": fin.get("has_savings"),
                "credit_score": _band(fin.get("credit_score"), SCORE, "{:.0f}"),
            }
    out["privacy"] = {
        "pseudonymised": True,
        "scheme": "first name + last initial",
        "also_redacted": ["exact financial figures bucketed into ranges",
                          "location coarsened to state/country"],
        "not_redacted": ["rep names", "setter names", "call dates", "age"],
        "residual_risk": ("Someone who already knows a prospect could still "
                          "recognise them from date, rep and context. This "
                          "protects against casual browsing, not a determined "
                          "acquaintance."),
        "full_fidelity_source": "data/calls/*.json, local only",
    }
    return out


URGENT_CAP = 250
CLUSTER_MEMBER_CAP = 25


def slim_payload(p):
    """Strip the web payload to what the dashboard actually renders.

    The full corpus is ~24 MB — every goal, pain, quote and evidence string
    for 422 calls. All of it is already summarised in the rollups, and
    shipping it means every visitor downloads the whole extraction database
    to draw a few tables. Full fidelity stays in data/calls/ and primal.db.
    """
    # The per-call array goes entirely. This dashboard is an aggregate view —
    # there is no call-by-call table and no per-prospect anything on it — and
    # every figure it used to derive by iterating this list is precomputed in
    # rollups.summary. Shipping 422 call records to draw a dozen averages put
    # a per-call dataset on a public URL for no rendering benefit.
    p.pop("calls", None)

    f = p.get("rollups", {}).get("flags")
    if f:
        # Clusters carry the systemic story; individual medium/low flags are
        # long-tail detail that lives in data/scores/parts/ for anyone digging.
        f["urgent_total"] = len(f.get("urgent", []))
        f["urgent"] = f.get("urgent", [])[:URGENT_CAP]
        f["all"] = []
        for cl in f.get("clusters", []):
            cl["members"] = cl.get("members", [])[:CLUSTER_MEMBER_CAP]
        f["systemic"] = [c for c in f.get("clusters", []) if c["n"] >= 3]
        f["clusters"] = []
    # Rollups ship one entry per observation — 1,524 anchors, 3,314 pain items,
    # 1,288 unmet-demand records. Nobody scrolls those, and the counts that
    # drive every chart are already computed. Cap the illustrative lists and
    # record what was truncated so the UI can say so honestly.
    R = p.get("rollups", {})

    def cap(lst, n, key="items"):
        for b in lst or []:
            items = b.get(key) or []
            if len(items) > n:
                b[key] = items[:n]
                b[f"{key}_truncated_from"] = len(items)

    cap(R.get("objection_plays"), 12, "instances")

    # Per-observation and per-prospect lists. The dashboard is an aggregate
    # view — it reports rates and themes, never "here are the 231 people who
    # were an edge fit". Every one of these is now summarised by a bucket
    # rollup computed over the full corpus, so the lists themselves are dead
    # weight in the payload as well as on the page.
    if R.get("anchors"):
        R["anchors_total"] = len(R["anchors"])
    R.pop("anchors", None)
    if R.get("unmet_by_verdict"):
        R["unmet_totals"] = {k: len(v) for k, v in R["unmet_by_verdict"].items()}
    R.pop("unmet_by_verdict", None)
    R.pop("unmet_demand", None)
    for b in R.get("pains") or []:
        b.pop("items", None)
    for b in R.get("goals") or []:
        b.pop("items", None)
    for b in R.get("pillars") or []:
        b.pop("items", None)
    for b in R.get("avatars") or []:
        b.pop("names", None)
    for key in ("demand_goals", "demand_pains"):
        for b in R.get(key) or []:
            b.pop("names", None)
    for f in R.get("funnel") or []:
        f.pop("deals_died", None)
    if R.get("icp"):
        icp = R["icp"]
        icp["assessments_total"] = len(icp.get("assessments") or [])
        icp.pop("assessments", None)
        for f in icp.get("fit_counts") or []:
            f.pop("who", None)
    if R.get("offer_consistency"):
        # One row per call — 422 rep/guarantee pairs. The finding is the
        # variance itself, and that is already a count.
        R["offer_consistency"].pop("guarantees", None)
    # The per-call duration list drove a scatter that the bucketed table
    # replaced; duration_summary and duration_buckets carry everything the
    # page reads.
    R.pop("duration", None)
    for k in ("longest", "shortest"):
        v = (R.get("duration_summary") or {}).get(k)
        if isinstance(v, dict):
            v.pop("prospect", None)
            v.pop("rep", None)
    D = R.get("discriminators")
    if D:
        D["all"] = []                     # top_favours_* already carry the ranked view

    w = (p.get("rules") or {}).get("corpus_window") or {}
    if w.get("from"):
        p["rules_window"] = f"{w['from']} to {w['to']}"
    for k in ("deals", "rules"):
        p.pop(k, None)
    pb = p.get("playbook", {})
    p["playbook"] = {"name": pb.get("name"), "phases": pb.get("phases"),
                     "objection_plays": pb.get("objection_plays"),
                     "known_gaps_in_script": pb.get("known_gaps_in_script")}
    return p


def main():
    records = load_calls()
    playbook = load_json(ROOT / "data" / "playbook.json")
    rules = load_json(ROOT / "data" / "rules.json")
    adherence = merge_parts(load_json(ROOT / "data" / "scores" / "adherence.json"),
                            "adherence", "calls")
    signals = merge_parts(load_json(ROOT / "data" / "signals.json"), "signals", "calls")
    icp = merge_parts(load_json(ROOT / "data" / "icp.json"), "icp", "assessments")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_DATA.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    junk_min = rules["junk_filter"]["min_file_size_bytes"]
    kept, junk = [], []
    for r in records:
        (junk if (r["source"].get("file_size_bytes") or 0) < junk_min else kept).append(r)
    records = kept

    # Corpus window. Out-of-window extractions stay on disk untouched — only
    # excluded from the metrics — so the window can be widened later without
    # re-running a single call.
    win = rules.get("corpus_window") or {}
    w_from, w_to = win.get("from"), win.get("to")
    out_of_window = 0
    if w_from or w_to:
        inside = []
        for r in records:
            d = r.get("call", {}).get("date") or ""
            if (w_from and d < w_from) or (w_to and d > w_to):
                out_of_window += 1
            else:
                inside.append(r)
        records = inside
        if out_of_window:
            print(f"  {out_of_window} call(s) outside {w_from}..{w_to} excluded from metrics")

    # Drop score records with no surviving extraction. At fan-out scale a
    # worker can write a score file and fail before writing the extraction,
    # or the call can be filtered as junk afterwards — either way an orphan
    # would crash the rollups on a missing call lookup.
    known = {r["call_id"] for r in records}
    for doc, key, label in ((adherence, "calls", "adherence"),
                            (signals, "calls", "signals"),
                            (icp, "assessments", "icp")):
        before = len(doc.get(key, []))
        doc[key] = [e for e in doc.get(key, []) if e.get("call_id") in known]
        if before - len(doc[key]):
            print(f"  dropped {before - len(doc[key])} orphan {label} record(s)")

    for rec in records:
        insert(conn, rec)
    adherence_summary = score_adherence(conn, playbook, adherence)
    deals = build_deals(conn, records)
    conn.commit()

    for rec in records:
        rec["adherence"] = adherence_summary.get(rec["call_id"])

    rollups = build_rollups(records, deals, playbook, adherence)
    rollups["discriminators"] = build_discriminators(records, deals, playbook, adherence)
    rollups.update(build_offer_signals(records, deals, playbook, adherence, signals, icp))
    rollups.update(build_buckets(records, deals, signals, icp, rollups))
    rollups["flags"] = build_flags(records)

    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("calls", "deals", "goals", "pains", "objections", "offer_tiers",
                  "phase_scores", "check_scores", "objection_plays")
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus": {
            "calls_ingested": counts["calls"],
            "deals": counts["deals"],
            "junk_excluded": len(junk),
            "junk_min_bytes": junk_min,
            "multi_call_deals": sum(1 for d in deals if d["call_count"] > 1),
            "note": "Outcomes are inferred from transcript language, not CRM-verified.",
        },
        "counts": counts,
        "rules": rules,
        "playbook": playbook,
        "rollups": rollups,
        "deals": deals,
        "calls": records,
    }
    # SQLite keeps real names for local analysis; the web payload does not.
    web = slim_payload(redact_payload(payload, records))
    WEB_DATA.write_text(json.dumps(web, separators=(",", ":")))
    conn.close()

    print("Built", DB_PATH.relative_to(ROOT))
    for t, n in counts.items():
        print(f"  {t:12} {n:4}")
    print("Wrote", WEB_DATA.relative_to(ROOT))


if __name__ == "__main__":
    main()
