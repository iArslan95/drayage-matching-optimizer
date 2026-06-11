"""Turn chains of orders into concrete truck routes: a list of legs with
from/to, kind (empty vs laden) and departure/arrival times. Used by both the
optimizer and the baseline so the comparison is exact."""
from __future__ import annotations

from .data import (HANDLE_CUSTOMER, HANDLE_DEPOT, HANDLE_TERMINAL, drive_min,
                   km)


def _leg(frm, to, kind, dep, order_id=None):
    return {
        "frm": frm, "to": to, "kind": kind, "km": km(frm, to),
        "dep": dep, "arr": dep + drive_min(frm, to), "order": order_id,
    }


def chain_legs(chain, flags, base):
    """Build the leg list for one truck.

    chain: orders in service sequence; flags[k] is True when the connection
    between chain[k] and chain[k+1] is a street turn (the import's empty box
    is trucked straight to the export customer); base is the carrier base.
    """
    legs = []
    cur = base
    for k, order in enumerate(chain):
        street_in = k > 0 and flags[k - 1]
        street_out = k < len(chain) - 1 and flags[k]

        if not street_in:
            if km(cur, order.start_place) > 0:
                legs.append(_leg(cur, order.start_place, "empty",
                                 order.start_min - drive_min(cur, order.start_place),
                                 order.id))
            cur = order.start_place

        if order.otype == "IMPORT":
            legs.append(_leg(order.terminal, order.customer, "import",
                             order.appt_min + HANDLE_TERMINAL, order.id))
            cur = order.customer
            if street_out:
                nxt = chain[k + 1]
                if km(cur, nxt.customer) > 0:
                    legs.append(_leg(cur, nxt.customer, "empty",
                                     order.unload_done_min, nxt.id))
                cur = nxt.customer
            else:
                legs.append(_leg(cur, order.depot, "empty",
                                 order.unload_done_min, order.id))
                cur = order.depot
        else:  # EXPORT
            if not street_in:
                legs.append(_leg(order.depot, order.customer, "empty",
                                 order.start_min + HANDLE_DEPOT, order.id))
                cur = order.customer
            legs.append(_leg(order.customer, order.terminal, "export",
                             order.appt_min + HANDLE_CUSTOMER, order.id))
            cur = order.terminal

    if km(cur, base) > 0:
        legs.append(_leg(cur, base, "empty", chain[-1].finish_min, None))
    return legs


def build_route(chain, flags, carrier):
    legs = chain_legs(chain, flags, carrier.base)
    return {
        "carrier": carrier.name,
        "base": carrier.base,
        "orders": [o.id for o in chain],
        "flags": list(flags),
        "legs": legs,
        "loaded_km": round(sum(l["km"] for l in legs if l["kind"] != "empty"), 1),
        "empty_km": round(sum(l["km"] for l in legs if l["kind"] == "empty"), 1),
    }
