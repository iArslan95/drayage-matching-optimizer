"""CP-SAT successor-matching model: pool all orders network-wide, chain them
onto trucks and exploit street turns, minimizing empty kilometres.

Decision variables
    x[i, j]   order j directly follows order i on the same truck (Boolean);
              the arc is a STREET TURN when i is an import and j an export of
              the same container type and the empty box is reused directly
    start[i]  order i opens a truck route (Boolean)
    end[i]    order i closes a truck route (Boolean)

Because appointments are fixed, every arc points forward in time — chains are
acyclic by construction and no subtour constraints are needed.

Objective
    minimize empty km = approach legs from a base + connecting legs between
    orders + return legs to a base + depot legs (heads/tails), where street
    turns replace an import's empty-return and an export's empty-pickup leg
    by one (usually short) customer-to-customer hop.
"""
from __future__ import annotations

from ortools.sat.python import cp_model

from .data import Scenario, drive_min, km
from .routes import build_route


def _arcs(orders):
    """Feasible succession arcs with their empty-km cost delta.

    Regular arc cost: empty drive from i's standalone finish to j's standalone
    start. Street-turn arc cost: the customer-to-customer hop MINUS the depot
    legs it eliminates (i.tail + j.head) — often a net negative.
    """
    arcs = {}
    for i, oi in enumerate(orders):
        for j, oj in enumerate(orders):
            if i == j:
                continue
            best = None
            if oi.finish_min + drive_min(oi.finish_place, oj.start_place) <= oj.start_min:
                best = (km(oi.finish_place, oj.start_place), False)
            if (oi.otype == "IMPORT" and oj.otype == "EXPORT"
                    and oi.box == oj.box
                    and oi.unload_done_min + drive_min(oi.customer, oj.customer)
                    <= oj.appt_min):
                cost = km(oi.customer, oj.customer) - oi.tail_km - oj.head_km
                if best is None or cost < best[0]:
                    best = (cost, True)
            if best is not None:
                arcs[i, j] = best
    return arcs


def solve(scenario: Scenario, time_limit_s: float = 10.0) -> dict:
    orders = list(scenario.orders)
    bases = [c.base for c in scenario.carriers]
    arcs = _arcs(orders)

    first_km = [min(km(b, o.start_place) for b in bases) for o in orders]
    last_km = [min(km(o.finish_place, b) for b in bases) for o in orders]

    m = cp_model.CpModel()
    x = {(i, j): m.NewBoolVar(f"x_{i}_{j}") for (i, j) in arcs}
    start = [m.NewBoolVar(f"start_{i}") for i in range(len(orders))]
    end = [m.NewBoolVar(f"end_{i}") for i in range(len(orders))]

    for i in range(len(orders)):
        m.Add(start[i] + sum(x[j, i] for j in range(len(orders)) if (j, i) in x) == 1)
        m.Add(end[i] + sum(x[i, j] for j in range(len(orders)) if (i, j) in x) == 1)

    scale = 10  # km -> decihectometres, keeps the objective integral
    obj = []
    for i in range(len(orders)):
        obj.append(start[i] * int(round(first_km[i] * scale)))
        obj.append(end[i] * int(round(last_km[i] * scale)))
    for (i, j), (cost, _street) in arcs.items():
        obj.append(x[i, j] * int(round(cost * scale)))
    m.Minimize(sum(obj))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    status = solver.Solve(m)
    status_name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "routes": []}

    succ = {}
    streets = {}
    for (i, j), (_cost, street) in arcs.items():
        if solver.Value(x[i, j]):
            succ[i] = j
            streets[i] = street

    routes = []
    for i in range(len(orders)):
        if not solver.Value(start[i]):
            continue
        chain_idx = [i]
        while chain_idx[-1] in succ:
            chain_idx.append(succ[chain_idx[-1]])
        chain = [orders[k] for k in chain_idx]
        flags = [streets[k] for k in chain_idx[:-1]]
        carrier = min(
            scenario.carriers,
            key=lambda c: km(c.base, chain[0].start_place)
            + km(chain[-1].finish_place, c.base),
        )
        routes.append(build_route(chain, flags, carrier))

    return {
        "status": status_name,
        "routes": routes,
        "wall_time_s": solver.WallTime(),
        "branches": solver.NumBranches(),
        "conflicts": solver.NumConflicts(),
    }
