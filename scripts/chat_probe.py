"""End-to-end probe of the Plan Assistant: solve a day, build the grounded
context, ask Groq one question, print the answer.

    python scripts/chat_probe.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import assistant  # noqa: E402
from optimizer import baseline, data, kpis, model  # noqa: E402


def main():
    key = assistant.get_api_key()
    if not key:
        sys.exit("No GROQ_API_KEY found in secrets or environment.")

    scenario = data.generate(5, n_orders=36, n_carriers=4, import_share=0.55)
    opt = model.solve(scenario, time_limit_s=10)
    base = baseline.fragmented_dispatch(scenario)
    k_opt, k_base = kpis.compute(opt), kpis.compute(base)

    context = assistant.build_context(
        scenario, opt, base, k_opt, k_base,
        settings={"seed": 5, "moves": 36, "carriers": 4, "import_share": 0.55},
    )
    question = ("Every order was known in advance - so why does pooling still "
                "cut empty kilometres versus the fragmented baseline? "
                "Max 3 sentences, mention one concrete street turn from today.")
    reply = "".join(assistant.stream_reply(
        key, context, [{"role": "user", "content": question}]))

    print("Q:", question)
    print("A:", reply)
    assert len(reply) > 40, "suspiciously short reply"
    print("CHAT PROBE OK")


if __name__ == "__main__":
    main()
