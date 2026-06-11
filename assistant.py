"""DrayOpt Plan Assistant — a grounded LLM chat over the live day plan.

Architecture: context injection. Every question is answered by an LLM (Groq,
Llama 3.3 70B) that receives a freshly serialized snapshot of the current
scenario, the network-optimized plan and the fragmented baseline in its
system prompt. Nothing is stored server-side; the API key lives in Streamlit
secrets, never in the repo.
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_HISTORY_TURNS = 8
MAX_USER_MESSAGES = 25

SYSTEM_PROMPT = """\
You are the DrayOpt Plan Assistant, embedded in DrayOpt — an interactive
Operations Research demo about container drayage (road transport of sea
containers) around the port of Rotterdam. Built by Ismail Arslan as a
portfolio demo; all data is synthetic, carrier names are fictional.

THE DOMAIN
- An IMPORT move: pick up a full container at a deep-sea terminal slot,
  deliver it to an inland customer, then return the EMPTY box to a depot
  near the port. An EXPORT move: collect an empty box at a depot, truck it
  to the customer for loading, deliver the full box to the terminal.
- A STREET TURN reuses an import's empty box directly for a nearby export of
  the same container type — eliminating the empty return leg AND the empty
  pickup leg. Reuse across shippers/carriers requires network-wide
  visibility: exactly what a matching platform adds.
- Roughly one in three drayage trucks runs empty today; empty km cost money
  and CO2 (here: EUR 1.40/km and 0.80 kg CO2/km, avg 65 km/h, handling 45
  min terminal / 60 min customer / 30 min depot).

WHAT THE APP SHOWS
- Sidebar: orders, carriers, import share; Advanced: random seed, solver
  time limit.
- KPI cards: empty running share, total kilometres, trucks needed — each
  versus the fragmented baseline. A banner shows km/EUR saved and street
  turns found.
- Tabs: "The day" (map of all truck legs — grey = empty, petrol = laden
  import, amber = laden export — plus a per-truck table) · "vs. fragmented
  dispatch" (side-by-side KPIs) · "Scenario" (orders, carriers) · "How it
  works" (the math).
- The map can toggle between the network-optimized plan and the fragmented
  baseline.

HOW THE OPTIMIZATION WORKS
- Baseline ("fragmented dispatch"): every shipper has its own contracted
  carrier, so the order book is split; dispatchers chain greedily within
  their own company and street turns are impossible. This is a fair model
  of pre-platform practice.
- Optimizer: Google OR-Tools CP-SAT successor matching over the POOLED
  order book. Variables: x[i,j] = order j follows i on the same truck
  (street-turn arcs replace depot legs by one customer-to-customer hop);
  start/end variables open and close truck routes. Appointments are fixed,
  so arcs always point forward in time (no subtours). Objective: minimize
  empty kilometres. Status OPTIMAL = mathematically proven best.
- IMPORTANT NUANCE (be honest about this when asked): all orders here are
  KNOWN in advance — matching itself needs no forecasting. Prediction adds
  value around the matching: anticipatory matching (commit now vs wait for
  a likely better order tonight), empty repositioning toward expected
  demand, vessel/container-release ETAs, and carrier acceptance/pricing.
  Those are roadmap items, deliberately not faked in this demo.

RULES
- Ground every number in the CURRENT STATE block. If something is not in
  the data, say so — never invent orders, trucks or kilometres.
- Be concise: under 150 words unless asked for depth. Money like
  "EUR 4,600"; distances like "1,234 km".
- Small arithmetic on the provided numbers is encouraged; show it briefly.
- Mirror the language of the user's latest message: English in, English
  out; Dutch in, Dutch out.
- Stay on topic: this demo, drayage and Operations Research. Politely steer
  anything else back to the plan.
"""


def get_api_key():
    try:
        import streamlit as st
        key = st.secrets.get("GROQ_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY")


def _t(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def build_context(scenario, opt, base, k_opt, k_base, settings) -> str:
    lines = ["CURRENT STATE", "", "Settings: " + json.dumps(settings)]

    lines.append(
        f"KPIs optimized network plan: {k_opt['total_km']:,.0f} km total "
        f"({k_opt['empty_km']:,.0f} empty = {k_opt['empty_pct']:.0%}), "
        f"{k_opt['trucks']} trucks, {k_opt['street_turns']} street turns, "
        f"cost EUR {k_opt['cost']:,.0f}, CO2 {k_opt['co2']:,.0f} kg."
    )
    lines.append(
        f"KPIs fragmented baseline: {k_base['total_km']:,.0f} km total "
        f"({k_base['empty_km']:,.0f} empty = {k_base['empty_pct']:.0%}), "
        f"{k_base['trucks']} trucks, 0 street turns, cost EUR "
        f"{k_base['cost']:,.0f}. Network matching saves "
        f"{k_base['total_km'] - k_opt['total_km']:,.0f} km and EUR "
        f"{k_base['cost'] - k_opt['cost']:,.0f} today "
        f"({1 - k_opt['empty_km'] / k_base['empty_km']:.0%} fewer empty km)."
    )

    lines.append("")
    lines.append("ORDERS (id | type | box | terminal | customer | depot | "
                 "appointment | laden km):")
    for o in scenario.orders:
        lines.append(
            f"- {o.id} | {o.otype} | {o.box} | {o.terminal.name} | "
            f"{o.customer.name} | {o.depot.name} | {_t(o.appt_min)} | "
            f"{o.loaded_km:,.0f}"
        )

    lines.append("")
    lines.append("OPTIMIZED TRUCK ROUTES (carrier | moves, '>>' = street turn "
                 "| laden km | empty km):")
    for r in opt["routes"]:
        seq = ""
        for k, oid in enumerate(r["orders"]):
            if k == 0:
                seq = oid
            else:
                seq += (" >> " if r["flags"][k - 1] else " -> ") + oid
        lines.append(f"- {r['carrier']} | {seq} | {r['loaded_km']:,.0f} | "
                     f"{r['empty_km']:,.0f}")

    lines.append("")
    lines.append("FRAGMENTED BASELINE ROUTES (carrier | moves | laden km | empty km):")
    for r in base["routes"]:
        lines.append(f"- {r['carrier']} | {' -> '.join(r['orders'])} | "
                     f"{r['loaded_km']:,.0f} | {r['empty_km']:,.0f}")

    return "\n".join(lines)


def suggested_questions(k_opt, k_base):
    cut = 1 - k_opt["empty_km"] / k_base["empty_km"] if k_base["empty_km"] else 0
    return [
        f"Where do today's {k_opt['street_turns']} street turns save the "
        "most kilometres?",
        f"Every order was known in advance — so why does pooling still cut "
        f"empty kilometres by {cut:.0%}?",
        "Which lane or customer drives the most empty kilometres, and what "
        "would fix it structurally?",
    ]


def _post_with_retry(api_key, payload):
    """POST to Groq, retrying on free-tier 429s (the response says how long
    to wait) and transient 5xx errors before giving up with a clear message."""
    for attempt in range(3):
        resp = requests.post(GROQ_URL, json=payload, stream=True, timeout=60,
                             headers={"Authorization": f"Bearer {api_key}"})
        if resp.status_code == 200:
            return resp
        status, detail = resp.status_code, resp.text[:200]
        if attempt < 2 and status == 429:
            m = re.search(r"try again in ([0-9.]+)s", resp.text)
            try:
                wait = float(resp.headers.get("retry-after") or
                             (m.group(1) if m else 3.0))
            except ValueError:
                wait = 3.0
            resp.close()
            time.sleep(min(wait + 0.4, 9.0))
            continue
        if attempt < 2 and status >= 500:
            resp.close()
            time.sleep(1.5)
            continue
        resp.close()
        if status == 429:
            raise RuntimeError("the free Groq tier hit its tokens-per-minute "
                               "limit and stayed busy after retries — wait "
                               "~30 seconds and ask again.")
        raise RuntimeError(f"Groq API {status}: {detail}")
    raise RuntimeError("Groq API unavailable after retries.")


def stream_reply(api_key, context, history):
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context}]
        + history[-MAX_HISTORY_TURNS:]
    )
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 700,
        "stream": True,
    }
    with _post_with_retry(api_key, payload) as resp:
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8")
            if not line.startswith("data: "):
                continue
            data = line[len("data: "):]
            if data == "[DONE]":
                break
            delta = json.loads(data)["choices"][0].get("delta", {})
            chunk = delta.get("content")
            if chunk:
                yield chunk
