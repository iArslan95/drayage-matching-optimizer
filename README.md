# 🚛 DrayOpt — Drayage Matching Optimizer

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![OR-Tools](https://img.shields.io/badge/OR--Tools-CP--SAT-green)
![Streamlit](https://img.shields.io/badge/Streamlit-app-red)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

An interactive **Operations Research** demo about container drayage — the road
leg of sea containers — around the port of Rotterdam. A CP-SAT matching model
pools the order books of all carriers, chains moves onto trucks and finds
**street turns**, benchmarked against today's fragmented per-carrier dispatch.
Inspired by the Rotterdam drayage market and the matching challenge platforms
like UTURN address; all data is synthetic and the project is not affiliated
with any platform, carrier or terminal.

## Why

In European container trucking roughly **one in three trucks runs empty**. A
truck delivers an import box in Venlo and drives back empty, while three
kilometres away another truck departs empty to collect an export load headed
the same way. The waste is structural: every shipper works with its own
contracted carrier, so no single dispatcher sees the whole board — and reusing
another shipper's empty container (a *street turn*) is impossible without
network-wide visibility.

That is a matching problem. This repo turns one synthetic day of it into
mathematics: pool every move, chain them optimally onto trucks, reuse empties
across shippers — and show exactly how many kilometres, euros and kg CO₂ the
network view is worth versus fragmented dispatch.

## What the app does

- **Optimizes** the whole day with [OR-Tools CP-SAT](https://developers.google.com/optimization/cp/cp_solver):
  successor-matching with street-turn arcs, minimizing empty kilometres.
- **Benchmarks** against a fair baseline: competent greedy dispatching, but
  fragmented per carrier and without street turns — today's practice.
- **Maps the day**: every truck leg on a minimal map (grey = empty running,
  petrol = laden import, amber = laden export), toggleable between the
  optimized network plan and the fragmented baseline.
- **Explains itself**: per-truck assignments (street turns marked ⟳), a
  side-by-side comparison, the model formulation, and an honest section on
  where forecasting would enter a live marketplace.
- **Plan Assistant**: a built-in LLM chat (Groq, Llama 3.3 70B) grounded in
  the live day plan — it answers "why" questions with the actual numbers.

All data is **synthetic** but realistic in magnitude: real-ish coordinates for
terminals, empty depots, inland customers and carrier bases; haversine × road
factor distances; practical handling times and appointment windows. Imports
cluster in the morning, exports later in the day — which is what makes street
turns possible in reality too.

## The optimization model

| Block | Content |
|---|---|
| **Variables** | `x[i,j]` move j follows move i on the same truck (street-turn arcs replace both depot legs by one customer-to-customer hop) · `start[i]` / `end[i]` open and close truck routes |
| **Constraints** | exactly one predecessor and successor per move (or route open/close) · fixed appointment slots make every arc point forward in time, so chains are acyclic by construction · street turns require the same container type and a time-feasible hop |
| **Objective** | minimise empty km: base approach + connections + depot legs + return legs |

The baseline splits the same order book across carriers (every shipper its own
contracted carrier), chains greedily within each company, and cannot street-turn
— a fair model of pre-platform practice. Typical result on the default day:
**~50% fewer empty kilometres**, a handful of street turns, fewer trucks.

## Where forecasting comes in (honestly)

Every order in the demo is known in advance — matching needs no forecast, and
none is faked. In a live marketplace, prediction adds value *around* the
matching: anticipatory matching (commit now vs. wait for tonight's likely
better order), empty repositioning toward expected demand, vessel ETA and
container-release prediction, and carrier acceptance/pricing models. That is
the natural bridge between predictive modelling and optimization.

## Plan Assistant setup (optional)

The chat panel needs a free [Groq](https://console.groq.com/keys) API key:

- **Locally**: copy `.streamlit/secrets.toml.example` to
  `.streamlit/secrets.toml` and fill in the key (the file is gitignored).
- **Streamlit Cloud**: App settings → Secrets → `GROQ_API_KEY = "gsk_..."`.

Without a key the app runs fine; the panel simply explains how to enable it.

## Quickstart

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Sanity checks:

```bash
python scripts/selftest.py    # 12 seeds: matching never loses to the baseline
python scripts/ui_test.py     # headless UI test (streamlit.testing)
python scripts/chat_probe.py  # one real grounded LLM answer (needs a key)
```

## Deploy (free, shareable link)

1. Push this repo to GitHub (public).
2. [share.streamlit.io](https://share.streamlit.io) → **New app** → pick the
   repo, main file `app.py` → **Deploy**.
3. Add the Groq key under **Settings → Secrets**, share the `*.streamlit.app` URL.

## Project structure

```
app.py                  Streamlit UI (map, KPIs, comparison, chat panel)
assistant.py            grounded LLM chat (Groq) over the live day plan
optimizer/
  data.py               synthetic day generator (moves, carriers, geography)
  model.py              CP-SAT successor matching with street-turn arcs
  baseline.py           fragmented per-carrier greedy dispatch
  routes.py             chains -> concrete truck routes (shared yardstick)
  kpis.py               km / cost / CO2 / trucks / street turns
scripts/selftest.py     multi-seed smoke test
scripts/ui_test.py      headless UI test
scripts/chat_probe.py   end-to-end assistant probe
```

## From demo to production

- Rolling re-matching as orders drop in during the day
- Driver shift & driving-time regulations, chassis and reefer constraints
- Lane-level demand forecasts for anticipatory matching and repositioning
- Vessel ETA / container-release prediction as optimizer input
- Carrier pricing & acceptance models
- Per-shipper CO₂ reporting of avoided kilometres

## Disclaimer

Educational portfolio project. All scenario data is synthetic; carrier names
are fictional; locations are approximate public coordinates. Inspired by the
Rotterdam container-drayage market and platforms such as UTURN — not
affiliated with or endorsed by any platform, carrier or terminal operator.
