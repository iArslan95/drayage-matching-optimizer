"""Baseline: today's fragmented dispatch, without a matching platform.

Every shipper works with its own contracted carrier, so the order book is
split across carriers rather than pooled. Within a carrier, a competent
dispatcher chains jobs greedily (nearest feasible next job for each truck).
Street turns are NOT available: reusing another shipper's empty container
requires the network-wide visibility and shipping-line approvals that a
platform brings — so every import returns its empty box to the depot and
every export collects one there.
"""
from __future__ import annotations

import random

from .data import Scenario, drive_min, km
from .routes import build_route


def fragmented_dispatch(scenario: Scenario) -> dict:
    rng = random.Random(scenario.seed * 77 + 5)
    shuffled = list(scenario.orders)
    rng.shuffle(shuffled)
    carriers = scenario.carriers
    book = {c.name: [] for c in carriers}
    for k, order in enumerate(shuffled):  # each shipper has its own carrier
        book[carriers[k % len(carriers)].name].append(order)

    routes = []
    for carrier in carriers:
        trucks = []  # each truck: list of orders, in service sequence
        for order in sorted(book[carrier.name], key=lambda o: o.start_min):
            best = None
            for truck in trucks:
                last = truck[-1]
                reach = last.finish_min + drive_min(last.finish_place, order.start_place)
                if reach <= order.start_min:
                    dead = km(last.finish_place, order.start_place)
                    if best is None or dead < best[1]:
                        best = (truck, dead)
            if best is None:
                trucks.append([order])
            else:
                best[0].append(order)
        for chain in trucks:
            routes.append(build_route(chain, [False] * (len(chain) - 1), carrier))

    return {"status": "FRAGMENTED", "routes": routes}
