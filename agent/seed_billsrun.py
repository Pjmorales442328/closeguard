# agent/seed_billsrun.py — fills agent/cache for the demo bills run on the bills bank (B13 open, then confirmed as Maria).
# Run: CG_ENV_FILE=<path to .env> python -m agent.seed_billsrun   (key loaded by code, never printed; <= 5 calls first time)
import os
import sys

from agent import extract

TRUTH_B13 = {"invoice_no": "FAL-24371", "invoice_date": "2026-10-03", "due_date": "2026-11-02", "total": "367.02"}


def main() -> int:
    if os.environ.get("CG_ENV_FILE"):
        extract.load_key_from(os.environ["CG_ENV_FILE"])
    os.environ["CG_MODEL_LIVE"] = "1"
    from app.services import intake, intake_human
    from app.services import intake_read as ir
    b = intake.demo()
    calls = []
    for step in ("B13 open", "B13 confirmed"):
        if step == "B13 confirmed":
            c = b.cards[12]
            picks = {f: "0" if str(x) == TRUTH_B13[f] else "1" if str(y) == TRUTH_B13[f] else f"other:{TRUTH_B13[f]}"
                     for f, x, y in ir.pick_fields(c)}
            print(step, intake_human.confirm(b, c, "Maria", "controller", picks).detail)
        r = intake.make_run(b)
        calls += r.model["calls"]
        print(step, r.counters(), [(x["txn"], x["how"]) for x in r.model["calls"]])
    bad = [x for x in calls if x["how"] not in ("live", "cached")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
