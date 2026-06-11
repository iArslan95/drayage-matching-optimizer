"""Synthetic scenario generation for one day of container drayage around the
port of Rotterdam.

Everything is synthetic but realistic in magnitude: real-ish coordinates for
deep-sea terminals, empty depots, inland customers and carrier bases; road
distances via haversine with a road factor; handling times and appointment
windows as used in practice. Carrier names are fictional. No real platform,
carrier or shipper data is used.

An IMPORT move: pick up a full box at a terminal slot, deliver to the inland
customer, then return the empty container to a depot near the port.
An EXPORT move: pick up an empty container at a depot, truck it to the
customer for loading, deliver the full box to the terminal.
A STREET TURN reuses the empty box of an import directly for a nearby export
of the same container type — eliminating both the empty return and the empty
pickup leg. That reuse across shippers and carriers is exactly what a
network-wide matching platform unlocks.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

ROAD_FACTOR = 1.30        # haversine -> road km
SPEED_KMH = 65            # average truck speed incl. minor stops
HANDLE_TERMINAL = 45      # minutes at the deep-sea terminal
HANDLE_CUSTOMER = 60      # minutes (un)loading at the customer
HANDLE_DEPOT = 30         # minutes at the empty-container depot
COST_PER_KM = 1.40        # EUR, all-in trucking cost
CO2_PER_KM = 0.80         # kg CO2 per km (loaded/empty averaged)

CONTAINER_TYPES = ("20DV", "40HC", "45HC", "40RF")
CONTAINER_WEIGHTS = (0.32, 0.48, 0.12, 0.08)


@dataclass(frozen=True)
class Place:
    name: str
    kind: str   # terminal | depot | customer | base
    lat: float
    lon: float


TERMINALS = (
    Place("Maasvlakte Terminal", "terminal", 51.9553, 4.0450),
    Place("Botlek Terminal", "terminal", 51.8830, 4.2900),
)

DEPOTS = (
    Place("Waalhaven Empty Depot", "depot", 51.8860, 4.4280),
    Place("Pernis Empty Depot", "depot", 51.8850, 4.3550),
)

CUSTOMERS = (
    Place("DC Bleiswijk", "customer", 52.0600, 4.5300),
    Place("DC Waddinxveen", "customer", 52.0400, 4.6500),
    Place("DC Moerdijk", "customer", 51.7020, 4.6080),
    Place("DC Tilburg", "customer", 51.5610, 5.0840),
    Place("DC Venlo", "customer", 51.3700, 6.1720),
    Place("DC Veghel", "customer", 51.6160, 5.5480),
    Place("DC Utrecht", "customer", 52.0900, 5.1100),
    Place("DC Zwolle", "customer", 52.5170, 6.0830),
    Place("Werk Duisburg", "customer", 51.4320, 6.7650),
    Place("DC Antwerpen", "customer", 51.2630, 4.4210),
)

# Fictional carriers with bases in the Rotterdam hinterland.
CARRIER_TEMPLATES = (
    ("Rijnmond Trucking", Place("Spijkenisse base", "base", 51.8450, 4.3290)),
    ("Brabant Cargo", Place("Breda base", "base", 51.5890, 4.7760)),
    ("Delta Container Transport", Place("Barendrecht base", "base", 51.8560, 4.5340)),
    ("Maaskant Logistiek", Place("Gorinchem base", "base", 51.8300, 4.9700)),
    ("Westland Haulage", Place("Maasdijk base", "base", 51.9590, 4.2110)),
    ("IJssel Transport", Place("Deventer base", "base", 52.2660, 6.1550)),
)


def km(a: Place, b: Place) -> float:
    """Road distance in km (haversine x road factor)."""
    if a.name == b.name:
        return 0.0
    lat1, lon1, lat2, lon2 = map(radians, (a.lat, a.lon, b.lat, b.lon))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return round(2 * 6371.0 * asin(sqrt(h)) * ROAD_FACTOR, 1)


def drive_min(a: Place, b: Place) -> int:
    return int(round(km(a, b) / SPEED_KMH * 60))


@dataclass(frozen=True)
class Order:
    id: str
    otype: str            # IMPORT | EXPORT
    box: str              # container type
    terminal: Place
    customer: Place
    depot: Place
    appt_min: int         # IMPORT: terminal pickup slot · EXPORT: loading start
    # Precomputed standalone schedule (fixed appointments -> deterministic):
    start_place: Place    # where a truck must be to begin this order
    start_min: int        # ... and when
    finish_place: Place   # where the truck ends the standalone order
    finish_min: int       # ... and when
    loaded_km: float      # the laden leg (terminal <-> customer)
    head_km: float        # EXPORT: empty depot -> customer leg (0 for imports)
    tail_km: float        # IMPORT: empty customer -> depot leg (0 for exports)
    unload_done_min: int  # IMPORT: moment the empty box is ready at the customer


@dataclass(frozen=True)
class Carrier:
    name: str
    base: Place


@dataclass(frozen=True)
class Scenario:
    seed: int
    orders: tuple
    carriers: tuple


def _round15(minutes: float) -> int:
    return int(minutes // 15 * 15)


def _mk_import(rng: random.Random, oid: str) -> Order:
    terminal = rng.choices(TERMINALS, weights=(0.62, 0.38), k=1)[0]
    customer = rng.choice(CUSTOMERS)
    depot = rng.choice(DEPOTS)
    box = rng.choices(CONTAINER_TYPES, weights=CONTAINER_WEIGHTS, k=1)[0]
    # Imports cluster in the morning: early terminal pickups make customer slots.
    appt = _round15(rng.uniform(6 * 60, 13 * 60 + 30))
    unload_done = appt + HANDLE_TERMINAL + drive_min(terminal, customer) + HANDLE_CUSTOMER
    finish = unload_done + drive_min(customer, depot) + HANDLE_DEPOT
    return Order(
        id=oid, otype="IMPORT", box=box, terminal=terminal, customer=customer,
        depot=depot, appt_min=appt,
        start_place=terminal, start_min=appt,
        finish_place=depot, finish_min=finish,
        loaded_km=km(terminal, customer), head_km=0.0,
        tail_km=km(customer, depot), unload_done_min=unload_done,
    )


def _mk_export(rng: random.Random, oid: str) -> Order:
    terminal = rng.choices(TERMINALS, weights=(0.62, 0.38), k=1)[0]
    customer = rng.choice(CUSTOMERS)
    depot = rng.choice(DEPOTS)
    box = rng.choices(CONTAINER_TYPES, weights=CONTAINER_WEIGHTS, k=1)[0]
    head_drive = drive_min(depot, customer)
    earliest_appt = 5 * 60 + HANDLE_DEPOT + head_drive  # depot opens 05:00
    # Exports cluster later in the day: loading for evening vessel cut-offs.
    appt = _round15(rng.uniform(max(10 * 60 + 30, earliest_appt), 16 * 60 + 30))
    start_min = appt - head_drive - HANDLE_DEPOT
    finish = appt + HANDLE_CUSTOMER + drive_min(customer, terminal) + HANDLE_TERMINAL
    return Order(
        id=oid, otype="EXPORT", box=box, terminal=terminal, customer=customer,
        depot=depot, appt_min=appt,
        start_place=depot, start_min=start_min,
        finish_place=terminal, finish_min=finish,
        loaded_km=km(customer, terminal), head_km=km(depot, customer),
        tail_km=0.0, unload_done_min=0,
    )


def generate(seed, n_orders=28, n_carriers=4, import_share=0.55) -> Scenario:
    rng = random.Random(seed)
    used_ids = set()
    orders = []
    for _ in range(n_orders):
        while True:
            oid = f"ORD-{rng.randint(1000, 9899)}"
            if oid not in used_ids:
                used_ids.add(oid)
                break
        if rng.random() < import_share:
            orders.append(_mk_import(rng, oid))
        else:
            orders.append(_mk_export(rng, oid))
    orders.sort(key=lambda o: o.start_min)
    carriers = tuple(Carrier(name, base)
                     for name, base in CARRIER_TEMPLATES[:max(2, n_carriers)])
    return Scenario(seed=seed, orders=tuple(orders), carriers=carriers)
