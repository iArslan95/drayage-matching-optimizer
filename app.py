"""DrayOpt — interactive Operations Research demo.

One synthetic day of container drayage around the port of Rotterdam: a
CP-SAT matching model pools the order book network-wide, chains moves onto
trucks and finds street turns — benchmarked against today's fragmented,
per-carrier dispatch.

Run:  streamlit run app.py
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import assistant
from optimizer import baseline, data, kpis, model

st.set_page_config(
    page_title="DrayOpt — Drayage Matching",
    page_icon="🚛",
    layout="wide",
)

DEFAULT_SEED = 5
LEG_STYLE = {
    "empty": dict(color="#b8b2ac", width=1.3, name="Empty running"),
    "import": dict(color="#0f766e", width=2.6, name="Laden — import"),
    "export": dict(color="#e09f3e", width=2.6, name="Laden — export"),
}

CSS = """
<style>
.block-container {padding-top: 1.4rem;}
.hero {
  background: #ffffff;
  border: 1px solid #e7e5e4; border-left: 4px solid #0f766e;
  border-radius: 14px; padding: 26px 30px; margin-bottom: 18px;
}
.hero h1 {margin: 0; font-size: 1.8rem; color: #1c1917; letter-spacing: -0.01em;}
.hero p {margin: 8px 0 0; color: #78716c; font-size: 0.98rem; max-width: 90ch;}
[data-testid="stMetric"] {
  background: #ffffff; border: 1px solid #e7e5e4;
  border-radius: 12px; padding: 14px 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.savings {
  background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534;
  padding: 13px 18px; border-radius: 12px;
  font-size: 1.0rem; margin: 6px 0 14px;
}
.orcard {
  background: #ffffff; border: 1px solid #e7e5e4; border-radius: 12px;
  padding: 16px 18px; height: 100%;
}
.orcard h4 {margin: 0 0 8px; color: #0f766e;}
.orcard p {margin: 0; color: #57534e; font-size: 0.92rem;}
.footer {color: #a8a29e; font-size: 0.85rem; margin-top: 28px;}
.stTabs [data-baseweb="tab-list"] {gap: 8px; padding: 2px 0 10px;}
.stTabs [data-baseweb="tab"] {
  background: #ffffff; border: 1px solid #e7e5e4; border-radius: 10px;
  padding: 9px 18px; font-weight: 600; font-size: 0.97rem; color: #57534e;
}
.stTabs [data-baseweb="tab"]:hover {border-color: #0f766e; color: #0f766e;}
.stTabs [aria-selected="true"] {
  background: #0f766e; border-color: #0f766e; color: #ffffff;
}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {display: none;}
.chat-head {font-weight: 700; font-size: 1.02rem; color: #0f766e; margin-top: 4px;}
.stButton button {
  font-size: 0.85rem; text-align: left; width: 100%;
  background: #ffffff; border: 1px solid #e7e5e4; border-radius: 10px;
  color: #44403c; padding: 6px 12px;
}
.stButton button:hover {border-color: #0f766e; color: #0f766e;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def t(minutes: float) -> str:
    minutes = int(minutes)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def eur(x: float) -> str:
    return f"€ {x:,.0f}"


@st.cache_data(show_spinner="Matching the network with CP-SAT…")
def solve_all(seed, n_orders, n_carriers, import_share, time_limit):
    scenario = data.generate(seed, n_orders=n_orders, n_carriers=n_carriers,
                             import_share=import_share)
    return (scenario, model.solve(scenario, time_limit),
            baseline.fragmented_dispatch(scenario))


def _arc(frm, to, bend):
    """Quadratic-bezier arc between two places; laden and empty legs bend to
    opposite sides so shared corridors separate instead of overlapping."""
    lat1, lon1, lat2, lon2 = frm.lat, frm.lon, to.lat, to.lon
    dx, dy = lon2 - lon1, lat2 - lat1
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return [lat1, lat2], [lon1, lon2]
    cx = (lon1 + lon2) / 2 + (-dy / length) * bend * length
    cy = (lat1 + lat2) / 2 + (dx / length) * bend * length
    lats, lons = [], []
    for k in range(15):
        s = k / 14
        lons.append((1 - s) ** 2 * lon1 + 2 * (1 - s) * s * cx + s * s * lon2)
        lats.append((1 - s) ** 2 * lat1 + 2 * (1 - s) * s * cy + s * s * lat2)
    return lats, lons


def _lanes(routes):
    """Aggregate individual legs into lanes: one line per corridor & kind,
    with trip count and summed km — the flow-map view."""
    agg = {}
    for r in routes:
        for leg in r["legs"]:
            key = (leg["frm"].name, leg["to"].name, leg["kind"])
            if key not in agg:
                agg[key] = {"frm": leg["frm"], "to": leg["to"],
                            "kind": leg["kind"], "trips": 0, "km": 0.0}
            agg[key]["trips"] += 1
            agg[key]["km"] += leg["km"]
    return sorted(agg.values(), key=lambda l: 0 if l["kind"] == "empty" else 1)


def day_map(routes, focus=None):
    """Flow map of the day. Aggregated lanes by default (width = trips);
    with `focus` set, one truck's route is drawn stop by stop and the rest
    fades to a backdrop."""
    trace_cls = getattr(go, "Scattermap", None) or go.Scattermapbox
    fig = go.Figure()

    if focus is None:
        seen = set()
        for lane in _lanes(routes):
            kind, style = lane["kind"], LEG_STYLE[lane["kind"]]
            empty = kind == "empty"
            lats, lons = _arc(lane["frm"], lane["to"], -0.16 if empty else 0.16)
            width = min(5.5, (1.1 if empty else 1.7) + 0.9 * (lane["trips"] - 1))
            label = (f"{lane['frm'].name} → {lane['to'].name} · "
                     f"{lane['trips']}× {style['name'].lower()} · "
                     f"{lane['km']:,.0f} km")
            fig.add_trace(trace_cls(
                lat=lats, lon=lons, mode="lines", name=style["name"],
                line=dict(color=style["color"], width=width),
                opacity=0.45 if empty else 0.85,
                legendgroup=kind, showlegend=kind not in seen,
                hoverinfo="text", text=[label] * len(lats),
            ))
            seen.add(kind)
    else:
        # Faint backdrop of every other lane, then the focused truck on top.
        lats, lons = [], []
        for lane in _lanes([r for r in routes if r is not focus]):
            lats += [lane["frm"].lat, lane["to"].lat, None]
            lons += [lane["frm"].lon, lane["to"].lon, None]
        fig.add_trace(trace_cls(
            lat=lats, lon=lons, mode="lines", name="Other trucks",
            line=dict(color="#d6d3d1", width=1), opacity=0.5,
            hoverinfo="skip",
        ))
        seen = set()
        for n, leg in enumerate(focus["legs"], start=1):
            kind, style = leg["kind"], LEG_STYLE[leg["kind"]]
            empty = kind == "empty"
            lats, lons = _arc(leg["frm"], leg["to"], -0.16 if empty else 0.16)
            label = (f"Leg {n}: {leg['frm'].name} → {leg['to'].name} · "
                     f"{style['name'].lower()} · {leg['km']:,.0f} km · "
                     f"{t(leg['dep'])}–{t(leg['arr'])}")
            fig.add_trace(trace_cls(
                lat=lats, lon=lons, mode="lines", name=style["name"],
                line=dict(color=style["color"], width=2.0 if empty else 3.4),
                opacity=0.7 if empty else 0.95,
                legendgroup=kind, showlegend=kind not in seen,
                hoverinfo="text", text=[label] * len(lats),
            ))
            seen.add(kind)
        stops = [focus["legs"][0]["frm"]] + [leg["to"] for leg in focus["legs"]]
        fig.add_trace(trace_cls(
            lat=[p.lat for p in stops], lon=[p.lon for p in stops],
            mode="markers+text",
            text=[str(k) for k in range(1, len(stops) + 1)],
            textposition="middle center",
            textfont=dict(size=9, color="#ffffff"),
            marker=dict(size=16, color="#1c1917"),
            hovertext=[f"Stop {k}: {p.name}" for k, p in enumerate(stops, 1)],
            hoverinfo="text", showlegend=False,
        ))

    marker_sets = (
        (data.TERMINALS, "#1c1917", 13, True),
        (data.DEPOTS, "#78716c", 10, False),
        (data.CUSTOMERS, "#0f766e", 9, False),
        (tuple(c.base for c in st.session_state.get("_carriers", ())), "#e09f3e", 9, False),
    )
    for places, color, size, labeled in marker_sets:
        if not places:
            continue
        fig.add_trace(trace_cls(
            lat=[p.lat for p in places], lon=[p.lon for p in places],
            mode="markers+text" if labeled else "markers",
            text=[p.name for p in places],
            textposition="top right",
            textfont=dict(size=11, color="#44403c"),
            marker=dict(size=size, color=color),
            hovertext=[f"{p.name} ({p.kind})" for p in places],
            hoverinfo="text", showlegend=False,
        ))

    layout_key = "map" if hasattr(go, "Scattermap") else "mapbox"
    fig.update_layout(**{layout_key: dict(
        style="carto-positron",
        center=dict(lat=51.82, lon=5.05), zoom=7.2,
    )})
    fig.update_layout(
        height=540, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0,
                    bgcolor="rgba(255,255,255,0.8)"),
        font_color="#57534e",
    )
    return fig


def trucks_table(routes):
    rows = []
    for n, r in enumerate(sorted(routes, key=lambda r: r["legs"][0]["dep"]), start=1):
        moves = r["orders"][0]
        for k, oid in enumerate(r["orders"][1:]):
            moves += (" ⟳ " if r["flags"][k] else " → ") + oid
        total = r["loaded_km"] + r["empty_km"]
        rows.append({
            "Truck": f"T{n:02d}",
            "Carrier": r["carrier"],
            "Moves (⟳ = street turn)": moves,
            "Start": t(r["legs"][0]["dep"]),
            "End": t(r["legs"][-1]["arr"]),
            "Laden km": round(r["loaded_km"]),
            "Empty km": round(r["empty_km"]),
            "Empty %": f"{r['empty_km'] / total:.0%}" if total else "0%",
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def km_bar(k_base, k_opt):
    df = pd.DataFrame([
        {"Plan": "Fragmented dispatch", "Component": "Laden", "km": k_base["loaded_km"]},
        {"Plan": "Fragmented dispatch", "Component": "Empty", "km": k_base["empty_km"]},
        {"Plan": "Network-optimized", "Component": "Laden", "km": k_opt["loaded_km"]},
        {"Plan": "Network-optimized", "Component": "Empty", "km": k_opt["empty_km"]},
    ])
    fig = px.bar(df, x="Plan", y="km", color="Component", barmode="stack",
                 text_auto=".3s",
                 color_discrete_map={"Laden": "#0f766e", "Empty": "#b8b2ac"})
    fig.update_layout(
        height=360, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#57534e", margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=""),
    )
    fig.update_xaxes(title="")
    fig.update_yaxes(gridcolor="#e7e5e4", title="km")
    return fig


def render_chat(scenario, opt, base, k_opt, k_base, settings):
    st.markdown('<div class="chat-head">💬 Plan Assistant</div>', unsafe_allow_html=True)
    st.caption("Grounded in the live day plan — ask why, what, and what-if.")
    history = st.session_state.setdefault("chat_history", [])

    box = st.container(height=460, border=True)
    with box:
        if not history:
            st.markdown(
                "<small style='color:#a8a29e'>I can explain every number and "
                "every route on this page. Try a suggestion below or ask your "
                "own question.</small>",
                unsafe_allow_html=True,
            )
        for m in history:
            with st.chat_message(m["role"], avatar="🚛" if m["role"] == "assistant" else None):
                st.markdown(m["content"])

    api_key = assistant.get_api_key()
    if not api_key:
        st.info("Add `GROQ_API_KEY` to `.streamlit/secrets.toml` (locally) or to "
                "the app's Secrets on Streamlit Cloud to enable the assistant.")
        return

    n_user = sum(1 for m in history if m["role"] == "user")
    if n_user >= assistant.MAX_USER_MESSAGES:
        st.warning("Chat limit reached for this session — tweak the scenario or refresh.")
        return

    if not history:
        for i, q in enumerate(assistant.suggested_questions(k_opt, k_base)):
            if st.button(q, key=f"suggestion_{i}"):
                st.session_state["pending_question"] = q

    user_msg = st.chat_input("Ask about this plan…")
    user_msg = user_msg or st.session_state.pop("pending_question", None)
    if not user_msg:
        return

    history.append({"role": "user", "content": user_msg})
    with box:
        with st.chat_message("user"):
            st.markdown(user_msg)
        with st.chat_message("assistant", avatar="🚛"):
            context = assistant.build_context(scenario, opt, base, k_opt, k_base, settings)
            try:
                reply = st.write_stream(assistant.stream_reply(api_key, context, history))
            except Exception as exc:
                reply = f"⚠️ The assistant hit an error: {exc}"
                st.markdown(reply)
    history.append({"role": "assistant", "content": str(reply)})


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### 🚛 DrayOpt")
    st.caption("Operations Research demo — synthetic data, real mathematics.")

    st.markdown("#### Scenario")
    n_orders = st.slider("Container moves today", 12, 60, 36,
                         help="How many import/export moves are booked for this day. "
                              "More moves = a denser network = more matching potential.")
    n_carriers = st.slider("Carriers", 2, 6, 4,
                           help="Trucking companies in the market. In the fragmented "
                                "baseline each shipper is tied to one carrier; the "
                                "network plan pools them all.")
    import_share = st.slider("Import share", 0.35, 0.75, 0.55, 0.05,
                             help="Share of moves that are imports (terminal → customer). "
                                  "The rest are exports. Street turns need both.")

    with st.expander("⚙️ Advanced"):
        seed = st.number_input("Random seed", 1, 999, DEFAULT_SEED,
                               help="Same seed = same day. Change it for a fresh order book.")
        time_limit = st.slider("CP-SAT time limit (s)", 2, 30, 10,
                               help="Maximum solver search time. Instances this size "
                                    "solve to proven optimality in well under a second.")

scenario, opt, base = solve_all(seed, n_orders, n_carriers, import_share, time_limit)
st.session_state["_carriers"] = scenario.carriers

# ----------------------------------------------------------------------------- header
st.markdown(
    """
    <div class="hero">
      <h1>🚛 DrayOpt — Drayage Matching Optimizer</h1>
      <p>One day of container trucking around the port of Rotterdam. A CP-SAT model
      pools every carrier's order book, chains moves onto trucks and finds
      <b>street turns</b> — reusing import empties for nearby exports — versus
      today's fragmented, per-carrier dispatch.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if opt["status"] not in ("OPTIMAL", "FEASIBLE"):
    st.error(f"Solver returned **{opt['status']}** — try another seed.")
    st.stop()

k_opt = kpis.compute(opt)
k_base = kpis.compute(base)
saved_km = k_base["total_km"] - k_opt["total_km"]
saved_eur = k_base["cost"] - k_opt["cost"]
saved_co2 = k_base["co2"] - k_opt["co2"]
empty_cut = 1 - k_opt["empty_km"] / k_base["empty_km"] if k_base["empty_km"] else 0.0

c1, c2, c3 = st.columns(3)
c1.metric("Empty running", f"{k_opt['empty_pct']:.0%}",
          delta=f"{(k_opt['empty_pct'] - k_base['empty_pct']) * 100:+.0f} pp vs fragmented",
          delta_color="inverse",
          help="Share of all kilometres driven without a container on the chassis. "
               "The delta compares against the fragmented per-carrier baseline.")
c2.metric("Total kilometres", f"{k_opt['total_km']:,.0f} km",
          delta=f"{k_opt['total_km'] - k_base['total_km']:+,.0f} km vs fragmented",
          delta_color="inverse",
          help="Laden + empty kilometres across all trucks today. Laden km are "
               "identical in both plans — the entire difference is empty running.")
c3.metric("Trucks on the road", f"{k_opt['trucks']}",
          delta=f"{k_opt['trucks'] - k_base['trucks']:+d} vs fragmented",
          delta_color="inverse",
          help="Number of truck shifts needed to serve all moves. Chaining moves "
               "tightly means fewer trucks for the same work.")

if saved_km > 0.5:
    st.markdown(
        f"""<div class="savings">♻️ Network-wide matching eliminates
        <b>{saved_km:,.0f} km</b> and <b>{eur(saved_eur)}</b> today —
        {empty_cut:.0%} fewer empty kilometres through pooling and
        <b>{k_opt['street_turns']} street turns</b>, avoiding
        {saved_co2:,.0f} kg CO₂.</div>""",
        unsafe_allow_html=True,
    )
else:
    st.info("The fragmented dispatch happens to be efficient for this day — "
            "add moves or carriers to see pooling earn its keep.")

main_col, chat_col = st.columns([2.3, 1], gap="medium")

with main_col:
    tab_day, tab_vs, tab_data, tab_how = st.tabs(
        ["🗺️ The day", "⚖️ vs. fragmented dispatch", "📦 Scenario", "🧠 How it works"]
    )

# ----------------------------------------------------------------------------- day tab
with tab_day:
    st.caption(
        f"Solver: CP-SAT · status **{opt['status']}** · {opt['wall_time_s']:.2f}s wall time · "
        f"{len(scenario.orders)} moves · {k_opt['street_turns']} street turns found"
    )
    view_col, focus_col = st.columns([1.25, 1])
    with view_col:
        view = st.radio("Map view",
                        ["Network-optimized plan", "Fragmented dispatch (today's practice)"],
                        horizontal=True, label_visibility="collapsed")
    routes_view = opt["routes"] if view.startswith("Network") else base["routes"]
    routes_sorted = sorted(routes_view, key=lambda r: r["legs"][0]["dep"])
    with focus_col:
        options = ["All trucks — network overview"]
        for n, r in enumerate(routes_sorted, start=1):
            turns = sum(r["flags"])
            options.append(f"T{n:02d} · {r['carrier']} · {len(r['orders'])} moves"
                           + (f" · {turns} ⟳" if turns else ""))
        pick = st.selectbox("Focus on one truck", options,
                            label_visibility="collapsed",
                            help="Follow a single truck's day stop by stop; "
                                 "all other traffic fades to a backdrop.")
    focus = None if pick == options[0] else routes_sorted[options.index(pick) - 1]
    st.plotly_chart(day_map(routes_view, focus))
    if focus is None:
        st.caption("Lanes are bundled: one arc per corridor, **line width = number "
                   "of trips**; laden arcs bend one way, empty running the other. "
                   "⬛ terminals · ⚫ depots · 🟢 customers · 🟠 carrier bases. "
                   "Pick a truck above to follow its day stop by stop.")
    else:
        st.caption("Numbered stops follow the truck through its day; hover a leg "
                   "for times and kilometres. Grey backdrop = the rest of the "
                   "network. ⟳ in the picker marks trucks with a street turn.")
    st.subheader("Truck assignments",
                 help="One row per truck shift in the selected view. ⟳ marks a street "
                      "turn: the import's empty box goes straight to the export "
                      "customer instead of via the depot.")
    trucks_table(routes_sorted)

# ----------------------------------------------------------------------------- compare tab
with tab_vs:
    st.markdown(
        "The baseline models **today's practice**: every shipper works with its own "
        "contracted carrier, dispatchers chain jobs well — but only within their own "
        "company, and container reuse across shippers is off-limits. The optimizer "
        "pools the same order book network-wide and unlocks street turns."
    )
    left, right = st.columns(2)
    with left:
        st.subheader("Kilometres by plan",
                     help="Laden kilometres are identical by construction — the gap "
                          "is pure empty running.")
        st.plotly_chart(km_bar(k_base, k_opt))
    with right:
        st.subheader("Side by side",
                     help="Same order book, same cost model, same yardstick.")
        st.dataframe(pd.DataFrame([
            {"Metric": "Total km", "Fragmented": f"{k_base['total_km']:,.0f}",
             "Network-optimized": f"{k_opt['total_km']:,.0f}"},
            {"Metric": "Empty km", "Fragmented": f"{k_base['empty_km']:,.0f}",
             "Network-optimized": f"{k_opt['empty_km']:,.0f}"},
            {"Metric": "Empty share", "Fragmented": f"{k_base['empty_pct']:.0%}",
             "Network-optimized": f"{k_opt['empty_pct']:.0%}"},
            {"Metric": "Trucks", "Fragmented": str(k_base["trucks"]),
             "Network-optimized": str(k_opt["trucks"])},
            {"Metric": "Street turns", "Fragmented": "0 (not possible)",
             "Network-optimized": str(k_opt["street_turns"])},
            {"Metric": "Cost", "Fragmented": eur(k_base["cost"]),
             "Network-optimized": eur(k_opt["cost"])},
            {"Metric": "CO₂", "Fragmented": f"{k_base['co2']:,.0f} kg",
             "Network-optimized": f"{k_opt['co2']:,.0f} kg"},
        ]), width="stretch", hide_index=True, height=330)

# ----------------------------------------------------------------------------- data tab
with tab_data:
    st.caption(f"All synthetic, generated from seed {seed}. Carrier names are "
               "fictional; locations are real-ish points around Rotterdam.")
    st.subheader(f"Container moves ({len(scenario.orders)})",
                 help="The day's order book. An import runs terminal → customer → "
                      "empty depot; an export runs depot → customer → terminal. "
                      "Appointments are fixed slots.")
    st.dataframe(pd.DataFrame([
        {
            "Order": o.id,
            "Move": "⬇️ Import" if o.otype == "IMPORT" else "⬆️ Export",
            "Box": o.box,
            "Terminal": o.terminal.name,
            "Customer": o.customer.name,
            "Depot": o.depot.name,
            "Appointment": t(o.appt_min),
            "Laden km": round(o.loaded_km),
        }
        for o in scenario.orders
    ]), width="stretch", hide_index=True)

    st.subheader(f"Carriers ({len(scenario.carriers)})",
                 help="Fictional trucking companies. In the fragmented baseline each "
                      "order is tied to one of them; the network plan dispatches from "
                      "the best-placed base.")
    st.dataframe(pd.DataFrame([
        {"Carrier": c.name, "Base": c.base.name} for c in scenario.carriers
    ]), width="stretch", hide_index=True)

# ----------------------------------------------------------------------------- how tab
with tab_how:
    st.markdown("#### Operations Research in three building blocks")
    cc1, cc2, cc3 = st.columns(3)
    cc1.markdown(
        """<div class="orcard"><h4>1 · Decision variables</h4>
        <p>For every pair of moves: does j <b>follow</b> i on the same truck
        (x<sub>i,j</sub>)? Special arcs mark <b>street turns</b>. Start/end
        variables open and close truck routes. Every possible day plan is some
        setting of these switches.</p></div>""",
        unsafe_allow_html=True)
    cc2.markdown(
        """<div class="orcard"><h4>2 · Hard constraints</h4>
        <p>Each move has exactly one predecessor and successor (or opens/closes
        a route) · fixed appointment slots make every arc point forward in time
        — no subtours possible · street turns require the same container type
        and a feasible drive between customers.</p></div>""",
        unsafe_allow_html=True)
    cc3.markdown(
        """<div class="orcard"><h4>3 · Objective</h4>
        <p>Minimise <b>empty kilometres</b>: base approach + connections between
        moves + return legs + depot legs. A street turn replaces two depot legs
        by one short customer-to-customer hop. The solver proves optimality.</p>
        </div>""",
        unsafe_allow_html=True)

    st.markdown("&nbsp;")
    st.latex(r"""
        \min \;\; \sum_{i} s_i\, d(b, \mathrm{start}_i)
        \;+\; \sum_{(i,j)} x_{ij}\, d^{\varnothing}_{ij}
        \;+\; \sum_{i} e_i\, d(\mathrm{finish}_i, b)
    """)
    st.latex(r"""
        \text{s.t.}\quad
        s_i + \sum_{j} x_{ji} = 1, \qquad
        e_i + \sum_{j} x_{ij} = 1, \qquad
        x_{ij} = 0 \;\text{unless time-feasible}
    """)

    with st.expander("Where does forecasting come in? (the honest version)"):
        st.markdown(
            """
Every order in this demo is **known in advance** — matching itself needs no
forecasting, and this demo deliberately doesn't fake any. In a live
marketplace, prediction adds value *around* the matching:

- **Anticipatory matching** — commit truck X to order A now, or wait for the
  statistically likely better order B tonight? Needs a demand forecast per lane.
- **Empty repositioning** — sometimes the best move is driving empty *toward*
  where tomorrow's demand will be. Only possible with a regional demand forecast.
- **Container release & vessel ETAs** — a booked import is only truckable once
  the vessel is in and the box is released; predicting *when* keeps plans real.
- **Acceptance & pricing** — will a carrier take this load at this price?

That is the natural bridge between predictive modelling and the optimization
shown here: forecasts feed the matcher.
            """
        )

    with st.expander("The model in code (OR-Tools CP-SAT)"):
        st.code(
            '''
# one boolean per feasible succession; street-turn arcs carry the saving
x[i, j] = model.NewBoolVar(f"x_{i}_{j}")          # j follows i on a truck
model.Add(start[i] + sum(x[j, i]) == 1)            # one way in
model.Add(end[i] + sum(x[i, j]) == 1)              # one way out
# arcs exist only when finish_i + drive <= start_j  (fixed appointments)
# street turn (import i -> export j, same box type):
#   cost = hop(customer_i, customer_j) - empty_return_i - empty_pickup_j
model.Minimize(sum(arc_cost * x) + base_approach + base_return)
''',
            language="python",
        )

    st.markdown("#### From demo to production")
    st.markdown(
        """
- **Rolling re-matching** — re-solve as orders drop in during the day, freezing moves already underway.
- **Driver & shift rules** — driving-time regulations, breaks, chassis and reefer constraints.
- **Demand forecasting per lane** — anticipatory matching and proactive empty repositioning.
- **Vessel ETA / container-release prediction** — plan on predicted, not nominated, availability.
- **Carrier pricing & acceptance models** — which match clears the market, not just the shortest one.
- **Per-shipper CO₂ reporting** — the avoided kilometres, attributed.
        """
    )

with chat_col:
    chat_settings = {
        "seed": int(seed), "moves": n_orders, "carriers": n_carriers,
        "import_share": import_share,
    }
    render_chat(scenario, opt, base, k_opt, k_base, chat_settings)

st.markdown(
    """<div class="footer">DrayOpt · OR-Tools CP-SAT + Streamlit · all data synthetic ·
    inspired by the Rotterdam container-drayage market and the matching challenge
    platforms like UTURN address · built by Ismail Arslan as an Operations Research
    portfolio demo — not affiliated with any platform, carrier or terminal.</div>""",
    unsafe_allow_html=True,
)
