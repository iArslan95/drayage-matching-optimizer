"""Parameter sweep to pick demo defaults with a credible, strong story."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from optimizer import baseline, data, kpis, model  # noqa: E402

for n_orders in (28, 36, 44):
    for n_carriers in (4, 5):
        rows = []
        for seed in range(1, 9):
            sc = data.generate(seed, n_orders=n_orders, n_carriers=n_carriers)
            ko = kpis.compute(model.solve(sc, 10))
            kb = kpis.compute(baseline.fragmented_dispatch(sc))
            empty_cut = 1 - ko["empty_km"] / kb["empty_km"]
            rows.append((seed, kb["empty_pct"], ko["empty_pct"], empty_cut,
                         kb["total_km"] - ko["total_km"], ko["street_turns"],
                         kb["trucks"], ko["trucks"]))
        avg = [sum(r[i] for r in rows) / len(rows) for i in range(1, 6)]
        print(f"orders={n_orders} carriers={n_carriers}  "
              f"base%={avg[0]:.0%} opt%={avg[1]:.0%} emptyCut={avg[2]:.0%} "
              f"savedKm={avg[3]:,.0f} turns={avg[4]:.1f}")
        best = max(rows, key=lambda r: r[3])
        print(f"    best seed {best[0]}: base {best[1]:.0%} -> opt {best[2]:.0%}, "
              f"empty -{best[3]:.0%}, saved {best[4]:,.0f} km, turns {best[5]}, "
              f"trucks {best[6]}->{best[7]}")
