"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    import math

    # 1. Any metric in pr["metrics"] is NaN or Inf
    for k, v in pr.get("metrics", {}).items():
        if isinstance(v, (int, float)):
            if math.isnan(v) or math.isinf(v):
                problems.append(f"metric {k} is NaN or inf ({v})")

    # 2. Manifest check & row count
    pr_manifest = pr.get("manifest", {})
    expected_items = pr_manifest.get("items")
    expected_seeds = pr_manifest.get("seeds", [])
    expected_count = (expected_items * len(expected_seeds)) if (expected_items is not None and expected_seeds) else len(base.get("rows", []))

    pr_rows = pr.get("rows", [])
    if len(pr_rows) != expected_count:
        problems.append(f"row count {len(pr_rows)} != expected {expected_count}")

    # Check duplicated rows
    pr_keys = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    if len(pr_keys) != len(set(pr_keys)):
        problems.append("duplicate (item_id, seed) rows detected")

    # 3. (item_id, seed) set differs from baseline
    base_rows = base.get("rows", [])
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(pr_keys) != base_keys:
        problems.append("PR (item_id, seed) set differs from baseline")

    # 4. Evaluator failures or None in graded spec metrics
    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures is non-empty: {pr['evaluator_failures']}")

    graded_metrics = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    for r in pr_rows:
        for gm in graded_metrics:
            if gm in r and r[gm] is None:
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} has None for metric {gm}")
                break

    # 5. Slice tags consistency
    base_slices = {(r.get("item_id"), r.get("seed")): sorted(r.get("slices") or []) for r in base_rows}
    for r in pr_rows:
        key = (r.get("item_id"), r.get("seed"))
        if key in base_slices and sorted(r.get("slices") or []) != base_slices[key]:
            problems.append(f"row {key[0]}@{key[1]} slice tags differ from baseline")
            break

    # 6. Ratchet against base_spec
    if base_spec and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        spec_m = {m["id"]: m for m in spec.get("metrics", [])}
        base_m = {m["id"]: m for m in base_spec.get("metrics", [])}

        for mid, bm in base_m.items():
            if mid not in spec_m:
                problems.append(f"metric {mid} was removed from spec (ratchet)")
                continue
            sm = spec_m[mid]
            if bm.get("blocking") and not sm.get("blocking"):
                problems.append(f"metric {mid} blocking was removed (ratchet)")

            b_th = bm.get("threshold", {})
            s_th = sm.get("threshold", {})
            if "min" in b_th:
                if "min" not in s_th or s_th["min"] < b_th["min"]:
                    problems.append(f"metric {mid} min threshold loosened ({s_th.get('min')} < {b_th['min']})")
            if "max" in b_th:
                if "max" not in s_th or s_th["max"] > b_th["max"]:
                    problems.append(f"metric {mid} max threshold loosened ({s_th.get('max')} > {b_th['max']})")
            if b_th.get("no_significant_drop") and not s_th.get("no_significant_drop"):
                problems.append(f"metric {mid} no_significant_drop removed (ratchet)")

        spec_sl = {s["name"]: s for s in spec.get("slices", [])}
        base_sl = {s["name"]: s for s in base_spec.get("slices", [])}
        for sname, b_slice in base_sl.items():
            if sname not in spec_sl:
                problems.append(f"slice {sname} was removed from spec (ratchet)")
                continue
            s_slice = spec_sl[sname]
            if b_slice.get("blocking") and not s_slice.get("blocking"):
                problems.append(f"slice {sname} blocking removed (ratchet)")
            if "min" in b_slice:
                if "min" not in s_slice or s_slice["min"] < b_slice["min"]:
                    problems.append(f"slice {sname} min loosened ({s_slice.get('min')} < {b_slice['min']})")
            if b_slice.get("no_significant_drop") and not s_slice.get("no_significant_drop"):
                problems.append(f"slice {sname} no_significant_drop removed (ratchet)")

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})

    for s in spec.get("slices", []):
        name = s["name"]
        mid = s["metric"]
        min_val = s.get("min")
        no_drop = s.get("no_significant_drop", False)
        is_blocking = s.get("blocking", False)

        pr_items = per_item(pr, mid, slice_name=name)
        base_items = per_item(base, mid, slice_name=name)

        if not pr_items:
            continue

        val = sum(pr_items.values()) / len(pr_items)
        verdict = "ok"
        note = ""

        if min_val is not None and val < min_val:
            verdict = "fail"

        if no_drop and base_items:
            keys = sorted(set(pr_items) & set(base_items))
            if keys:
                d, lo, hi = stats.paired_bootstrap(
                    [pr_items[k] for k in keys],
                    [base_items[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"

        slice_id = f"slice:{name}/{mid}"
        if verdict != "ok" and is_blocking:
            blocked.append(slice_id)

        label = "ok" if verdict == "ok" else ("BLOCK" if is_blocking else "warn")
        lines.append(f"  {slice_id:<22} {val:<8.4f} min={min_val!s:<6} {note:<28} {label}")

    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
