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
        [(cid, t.get("months"), t.get("price_usd")) for t in offer.get("tiers", [])],
    )


SCORE_NUM = {"hit": 1.0, "partial": 0.5, "miss": 0.0}


def load_json(path):
    with path.open() as fh:
        return json.load(fh)


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
    phase_rollup.sort(key=lambda x: (x["adherence_pct"] is None, x["adherence_pct"]))

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

    return {
        "phases": phase_rollup,
        "objection_plays": play_rollup,
        "avatars": avatar_rollup,
        "pains": bucket("pains"),
        "goals": bucket("goals"),
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

    universe = sorted({f for s in feats.values() for f in s})
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
        "min_p": min([r["p_enriched"] for r in rows], default=1.0),
        "top_favours_close": [r for r in rows if r["diff"] > 0][:40],
        "top_favours_loss": [r for r in rows if r["diff"] < 0][:40],
        "all": rows,
    }


def main():
    records = load_calls()
    playbook = load_json(ROOT / "data" / "playbook.json")
    adherence = load_json(ROOT / "data" / "scores" / "adherence.json")
    rules = load_json(ROOT / "data" / "rules.json")
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

    for rec in records:
        insert(conn, rec)
    adherence_summary = score_adherence(conn, playbook, adherence)
    deals = build_deals(conn, records)
    conn.commit()

    for rec in records:
        rec["adherence"] = adherence_summary.get(rec["call_id"])

    rollups = build_rollups(records, deals, playbook, adherence)
    rollups["discriminators"] = build_discriminators(records, deals, playbook, adherence)

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
    WEB_DATA.write_text(json.dumps(payload, indent=2))
    conn.close()

    print("Built", DB_PATH.relative_to(ROOT))
    for t, n in counts.items():
        print(f"  {t:12} {n:4}")
    print("Wrote", WEB_DATA.relative_to(ROOT))


if __name__ == "__main__":
    main()
