#!/usr/bin/env python3
"""
Split the manifest into worker batches.

Batches are grouped by rep and kept chronological within a rep, so a worker
sees a contextually coherent run of calls — same closer, same period, same
script era. That materially improves consistency of judgement calls like
avatar assignment versus handing an agent twelve unrelated calls.

Writes data/batches/batch_NNN.json and a batches/index.json summary.
"""
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "manifest.json"
OUT = ROOT / "data" / "batches"
BATCH_SIZE = 12


def window():
    """Corpus window from rules.json — single source of truth, so the batcher
    and the build can never disagree about what is in scope."""
    r = json.loads((ROOT / "data" / "rules.json").read_text())
    w = r.get("corpus_window") or {}
    return w.get("from"), w.get("to")


def main(batch_size=BATCH_SIZE, only_rep=None, limit=None):
    m = json.loads(MANIFEST.read_text())
    files = [f for f in m["files"] if not f["junk"]]
    total_eligible = len(files)

    w_from, w_to = window()
    if w_from or w_to:
        files = [f for f in files
                 if not ((w_from and f["call_date"] < w_from)
                         or (w_to and f["call_date"] > w_to))]
        print(f"window {w_from}..{w_to}: {len(files)} of {total_eligible} eligible calls in scope")

    if only_rep:
        files = [f for f in files if f["rep_folder"] == only_rep]

    # already-extracted calls are skipped so the run is resumable
    done_ids = set()
    for p in (ROOT / "data" / "calls").glob("*.json"):
        try:
            done_ids.add(json.loads(p.read_text())["source"]["drive_file_id"])
        except Exception:
            pass
    pending = [f for f in files if f["id"] not in done_ids]
    skipped = len(files) - len(pending)

    by_rep = {}
    for f in pending:
        by_rep.setdefault(f["rep_folder"], []).append(f)
    for v in by_rep.values():
        v.sort(key=lambda x: x["call_date"])

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("batch_*.json"):
        old.unlink()

    batches, n = [], 0
    for rep, items in sorted(by_rep.items()):
        for i in range(0, len(items), batch_size):
            chunk = items[i:i + batch_size]
            n += 1
            path = OUT / f"batch_{n:03d}.json"
            path.write_text(json.dumps({
                "batch_id": f"batch_{n:03d}",
                "rep_folder": rep,
                "count": len(chunk),
                "date_range": [chunk[0]["call_date"], chunk[-1]["call_date"]],
                "files": chunk,
            }, indent=2))
            batches.append({"batch_id": f"batch_{n:03d}", "rep": rep,
                            "count": len(chunk), "path": str(path.relative_to(ROOT)),
                            "bytes": sum(c["size_bytes"] for c in chunk)})
            if limit and n >= limit:
                break
        if limit and n >= limit:
            break

    (OUT / "index.json").write_text(json.dumps({
        "batch_size": batch_size, "batches": batches,
        "total_calls": sum(b["count"] for b in batches),
        "already_done": skipped,
    }, indent=2))

    print(f"{len(batches)} batches covering {sum(b['count'] for b in batches)} calls")
    if skipped:
        print(f"  ({skipped} already extracted, skipped)")
    per_rep = {}
    for b in batches:
        per_rep[b["rep"]] = per_rep.get(b["rep"], 0) + b["count"]
    for rep, c in sorted(per_rep.items(), key=lambda x: -x[1]):
        print(f"  {rep:18} {c:>4} calls")
    mb = sum(b["bytes"] for b in batches) / 1e6
    print(f"\n{mb:.1f} MB total · ~{mb/4*1e6/1e6:.1f}M tokens of transcript")


if __name__ == "__main__":
    args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
    main(batch_size=int(args.get("size", BATCH_SIZE)),
         only_rep=args.get("rep"),
         limit=int(args["limit"]) if "limit" in args else None)
