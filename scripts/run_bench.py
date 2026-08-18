"""Eval harness — runs the 15-complaint bench set through the LIVE pipeline.

Scores: clustering quality (purity + coverage + merge accuracy) against ground
truth, plus per-complaint intake correctness (category match).

Usage:
  python scripts/run_bench.py            # hits a running backend on :8799
  python scripts/run_bench.py --host http://IP:9999
"""
import argparse
import json
import sys
import time
from collections import defaultdict

import httpx

sys.path.insert(0, __import__("os").path.dirname(__file__))
from bench_set import COMPLAINTS, GROUND_TRUTH


def run_set(host: str) -> dict:
    results = []
    for c in COMPLAINTS:
        t0 = time.time()
        payload = {}
        if c.get("text"):
            payload["text"] = c["text"]
        if c.get("transcript"):
            payload["text"] = c["transcript"]  # voice via text for harness; audio tested separately
        if c.get("language"):
            payload["language"] = c["language"]
        if c.get("lat"):
            payload["lat"] = c["lat"]
            payload["lng"] = c["lng"]
        r = httpx.post(f"{host}/api/complaints", data=payload, timeout=180)
        dt = time.time() - t0
        try:
            body = r.json()
        except Exception:
            results.append({"id": c["id"], "truth": c["truth"], "error": f"HTTP {r.status_code}", "dt": round(dt, 1)})
            continue
        dd = body.get("dedup", {})
        comp = body.get("complaint", {})
        results.append({
            "id": c["id"], "truth": c["truth"], "issue_id": dd.get("issue_id"),
            "merged": dd.get("merged"), "category": comp.get("category"),
            "scores": dd.get("scores"), "dt": round(dt, 1),
        })
    return {"results": results}


def score(results: list) -> dict:
    # cluster accuracy: which complaints ended in the same issue
    truth_groups = defaultdict(list)
    for r in results:
        if "error" not in r:
            truth_groups[r["truth"]].append(r["id"])
    issue_groups = defaultdict(list)
    for r in results:
        if "error" not in r:
            issue_groups[r["issue_id"]].append(r["id"])

    # purity: for each issue, fraction of its members from the dominant truth cluster
    purity_numer = 0
    total_members = 0
    for issue, members in issue_groups.items():
        dom = max((truth_groups[t] and sum(1 for m in members if m in truth_groups[t]) for t in truth_groups),
                  default=0)
        total_members += len(members)
        purity_numer += dom
    purity = purity_numer / total_members if total_members else 0.0

    # coverage: fraction of ground-truth pairs that share an issue
    correct_pairs = total_pairs = 0
    for t, members in truth_groups.items():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                total_pairs += 1
                if _same_issue(results, members[i], members[j]):
                    correct_pairs += 1
    coverage = correct_pairs / total_pairs if total_pairs else 0.0

    # merge accuracy: how many complaints landed in the CORRECT cluster (their truth group's majority issue)
    correct_assign = 0
    for r in results:
        if "error" in r:
            continue
        truth = r["truth"]
        # issue that the majority of this truth group landed in
        votes = defaultdict(int)
        for rr in results:
            if "error" not in rr and rr["truth"] == truth:
                votes[rr["issue_id"]] += 1
        majority_issue = max(votes, key=votes.get) if votes else None
        if r["issue_id"] == majority_issue:
            correct_assign += 1
    assign_acc = correct_assign / len([r for r in results if "error" not in r]) if results else 0.0

    # category accuracy (normalize streetlight vs broken_streetlight)
    def _norm_cat(x):
        return "streetlight" if x in ("streetlight", "broken_streetlight") else x
    cat_ok = sum(1 for r in results if "error" not in r
                 and _norm_cat(r["category"]) == _norm_cat(GROUND_TRUTH[r["truth"]][0]))
    cat_acc = cat_ok / len([r for r in results if "error" not in r]) if results else 0.0

    return {
        "purity": round(purity, 3),
        "coverage": round(coverage, 3),
        "merge_accuracy": round(assign_acc, 3),
        "category_accuracy": round(cat_acc, 3),
        "num_issues": len(issue_groups),
        "expected_issues": len(truth_groups),
    }


def _same_issue(results, id1, id2):
    i1 = next((r["issue_id"] for r in results if r["id"] == id1), None)
    i2 = next((r["issue_id"] for r in results if r["id"] == id2), None)
    return i1 is not None and i1 == i2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:8799")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    print(f"=== NagarAI bench: {len(COMPLAINTS)} complaints → {args.host} ===\n")
    data = run_set(args.host)
    metrics = score(data["results"])

    if args.json:
        print(json.dumps({"results": data["results"], "metrics": metrics}, indent=2))
        return

    for r in data["results"]:
        err = f" ERROR: {r.get('error')}" if "error" in r else ""
        print(f"  #{r['id']:>2} truth={r['truth']} → issue={r.get('issue_id')} "
              f"merged={r.get('merged')} cat={r.get('category')} ({r.get('dt')}s){err}")
    print("\n=== METRICS ===")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    if metrics["num_issues"] == metrics["expected_issues"]:
        print(f"\n  ✓ {metrics['expected_issues']} distinct issues found — cluster count matches ground truth")


if __name__ == "__main__":
    main()
