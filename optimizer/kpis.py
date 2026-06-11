"""Shared KPI computation so the optimized plan and the fragmented baseline
are scored with exactly the same yardstick."""
from __future__ import annotations

from .data import CO2_PER_KM, COST_PER_KM


def compute(plan) -> dict:
    routes = plan["routes"]
    loaded = sum(r["loaded_km"] for r in routes)
    empty = sum(r["empty_km"] for r in routes)
    total = loaded + empty
    return {
        "loaded_km": round(loaded, 1),
        "empty_km": round(empty, 1),
        "total_km": round(total, 1),
        "empty_pct": empty / total if total else 0.0,
        "cost": total * COST_PER_KM,
        "co2": total * CO2_PER_KM,
        "trucks": len(routes),
        "street_turns": sum(sum(r["flags"]) for r in routes),
        "orders": sum(len(r["orders"]) for r in routes),
    }
