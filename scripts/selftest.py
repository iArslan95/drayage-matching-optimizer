"""Smoke test: generate scenarios across seeds, solve the network matching
and the fragmented baseline, and report the empty-km gap. Run from the
project root:

    python scripts/selftest.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from optimizer import baseline, data, kpis, model  # noqa: E402

HEADER = (
    f"{'seed':>4} {'status':<8} {'baseKm':>8} {'optKm':>8} {'savedKm':>8} "
    f"{'base%':>6} {'opt%':>6} {'trB':>4} {'trO':>4} {'turns':>5} {'sec':>5}"
)


def main():
    print(HEADER)
    for seed in range(1, 13):
        scenario = data.generate(seed, n_orders=28, n_carriers=4, import_share=0.55)
        opt = model.solve(scenario, time_limit_s=10)
        base = baseline.fragmented_dispatch(scenario)
        assert opt["status"] in ("OPTIMAL", "FEASIBLE"), opt["status"]
        ko = kpis.compute(opt)
        kb = kpis.compute(base)
        assert ko["orders"] == kb["orders"] == len(scenario.orders)
        assert abs(ko["loaded_km"] - kb["loaded_km"]) < 1e-6, "laden km must match"
        print(
            f"{seed:>4} {opt['status']:<8} {kb['total_km']:>8,.0f} {ko['total_km']:>8,.0f} "
            f"{kb['total_km'] - ko['total_km']:>8,.0f} {kb['empty_pct']:>5.0%} "
            f"{ko['empty_pct']:>5.0%} {kb['trucks']:>4} {ko['trucks']:>4} "
            f"{ko['street_turns']:>5} {opt['wall_time_s']:>5.2f}"
        )
        assert ko["empty_km"] <= kb["empty_km"] + 1e-6, \
            "network matching should never produce more empty km"
    print("ALL OK")


if __name__ == "__main__":
    main()
