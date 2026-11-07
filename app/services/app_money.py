# app/services/app_money.py — what a bookkeeper asks first: how much money did Closeguard stop, and which bills are due or late.
import os
import re
from datetime import date
from decimal import Decimal

from app.services import plain


def _d(s) -> Decimal:
    return Decimal(str(s or "0").replace(",", ""))


def stopped(bills: list, bank: dict) -> dict:
    """Money that would have gone out (or been recorded) wrongly without a check. Every amount comes from a bill or a bank line on screen."""
    items = []
    for x in bank["lines"]:
        if x["kind"] != "hold":
            continue
        t, amt = x["text"], _d(x["amount"])
        if t.startswith("Paid twice"):
            items.append((x["who"], "paid twice: the second payment", amt))
        elif t.startswith("Amount differs"):
            nums = [_d(m) for m in re.findall(r"\$([\d,]+\.\d\d)", t)]  # "the bill says $X, the bank paid $Y": only the difference is at risk
            items.append((x["who"], "bill and payment differ", abs(nums[0] - nums[1]) if len(nums) == 2 else amt))
        elif "approved supplier" in t:
            items.append((x["who"], "supplier nobody approved", amt))
    for b in bills:  # held bills that were not paid: stopped before any money left
        if b["kind"] == "hold" and b["total"] and not any(x["ref"] == b["invoice_no"] for x in bank["lines"]):
            items.append((b["supplier"], "bill on hold: " + ("supplier nobody approved" if b["new_supplier"] else "it has a mistake"), _d(b["total"])))
    total = sum((a for _, _, a in items), Decimal(0))
    return {"total": plain.money(total), "count": len(items), "items": [{"who": w, "what": t, "amount": plain.money(a)} for w, t, a in items]}


def today() -> date:
    return date.fromisoformat(os.environ["CG_TODAY"]) if os.environ.get("CG_TODAY") else date.today()  # tests pin the day


def due(bills: list, bank: dict) -> dict:
    """Per bill: paid (its payment is on the bank statement), or days until due / days late. Plus the totals a bookkeeper plans with."""
    lines = {}
    for x in bank["lines"]:
        lines.setdefault(x["ref"], x)  # the first payment for a bill number (a second one is "paid twice")
    now, per, late, week = today(), {}, [], []
    for b in bills:
        x = lines.get(b["invoice_no"])
        if x and b["kind"] == "hold":  # e.g. a second copy of a bill that was already paid: not owed
            per[b["id"]] = {"state": "later", "text": f"on hold: a payment for this bill left the bank on {plain_date(x['date'])}"}
        elif x and x["kind"] == "pay":
            per[b["id"]] = {"state": "paid", "text": f"Paid {plain_date(x['date'])}"}
        elif x:
            per[b["id"]] = {"state": "problem", "text": f"Paid {plain_date(x['date'])}, but see the bank tab"}
        elif b["due"] and b["kind"] != "check":  # not paid yet: how long until it is due, or how late it is (a held bill still has a due date)
            n = (date.fromisoformat(b["due"]) - now).days
            st = "late" if n < 0 else "soon" if n <= 7 else "later"
            txt = f"{-n} day{'s' if n != -1 else ''} late" if n < 0 else "due today" if n == 0 else f"due in {n} day{'s' if n != 1 else ''}"
            per[b["id"]] = {"state": st, "text": ("on hold, " if b["kind"] == "hold" else "not paid, ") + txt}
            (late if st == "late" else week if st == "soon" else []).append(b)
    tot = lambda xs: plain.money(sum((_d(b["total"]) for b in xs), Decimal(0)))  # noqa: E731
    return {"today": str(now), "bills": per, "late": [len(late), tot(late)], "week": [len(week), tot(week)],
            "late_list": [{"who": b["supplier"], "total": b["total"], "hold": b["kind"] == "hold"} for b in late]}


def plain_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%b} {d.day}"


def to_pay(bills: list, due: dict) -> list:
    """[count, total, already paid count] for bills that passed the checks."""
    ok = [b for b in bills if b["kind"] == "pay"]
    left = [b for b in ok if due["bills"].get(b["id"], {}).get("state") not in ("paid", "problem")]
    return [len(left), plain.money(sum((_d(b["total"]) for b in left), Decimal(0))), len(ok) - len(left)]
