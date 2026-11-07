# data/bills_html.py — four paper layouts (typed A4, thermal till slip, handwritten delivery bill, carbon copy) as HTML.
from html import escape as e

CUSTOMER = "Tidewater Catering Co."
MARK = "SYNTHETIC DATA - not a real bill"
LAYOUTS = ("a4", "thermal", "hand", "carbon")
DATE_FMT = {"a4": "%d %b %Y", "thermal": "%Y-%m-%d", "hand": "%b %d, %Y", "carbon": "%d-%b-%y"}


def _rows(b, fmt):
    return "".join(fmt.format(d=e(d), a=f"{a:,.2f}".replace(",", "")) for d, a in b["lines"])


def _a4(b, f):
    note = f'<p class="note">{e(b["note"])}</p>' if b.get("note") else ""
    return f"""<div class="paper" style="width:620px;min-height:480px;background:#fff;color:#1c1c1c;font:15px Arial,sans-serif;padding:0 0 28px">
<div style="background:{b['color']};color:#fff;padding:26px 34px"><div style="font-size:26px;font-weight:700">{e(b['vendor'])}</div>
<div style="font-size:12px;opacity:.85">Trade supplier · terms net 30</div></div>
<div style="padding:22px 34px"><div style="display:flex;justify-content:space-between"><div><b style="font-size:22px;letter-spacing:2px">INVOICE</b>
<p style="margin:10px 0 0;font-size:13px">Bill to:<br><b>{CUSTOMER}</b></p></div>
<table style="font-size:13px;text-align:right"><tr><td>Invoice no.</td><td><b>{e(b['inv_no'])}</b></td></tr>
<tr><td>Invoice date&nbsp;</td><td><b>{f(b['inv_date'])}</b></td></tr><tr><td>Due date</td><td><b>{f(b['due'])}</b></td></tr>
<tr><td>Currency</td><td><b>USD</b></td></tr></table></div>
<table style="width:100%;margin-top:26px;border-collapse:collapse;font-size:14px"><tr style="background:#eef0f3;text-align:left"><th style="padding:8px">Description</th><th style="text-align:right">Amount (USD)</th></tr>
{_rows(b, '<tr><td style="padding:8px;border-bottom:1px solid #ddd">{d}</td><td style="text-align:right;border-bottom:1px solid #ddd">{a}</td></tr>')}
<tr><td style="padding:12px 8px;text-align:right"><b>TOTAL DUE</b></td><td style="text-align:right;font-size:19px"><b>{b['total']}</b></td></tr></table>{note}
<p style="margin-top:34px;font-size:10px;color:#777">{MARK}</p></div></div>"""


def _thermal(b, f):
    note = f'<p>{e(b["note"])}</p>' if b.get("note") else ""
    return f"""<div class="paper" style="width:300px;background:#f6f4ee;color:#2b2b2b;font:13px 'Courier New',monospace;padding:22px 18px 30px">
<div style="text-align:center;font-size:17px;font-weight:700">{e(b['vendor']).upper()}</div><div style="text-align:center">TRADE COUNTER</div>
<p>------------------------------</p><div>INV# {e(b['inv_no'])}<br>DATE {f(b['inv_date'])}<br>DUE  {f(b['due'])}<br>CUST {CUSTOMER}</div><p>------------------------------</p>
{_rows(b, '<div style="display:flex;justify-content:space-between"><span>{d}</span><span>{a}</span></div>')}
<p>------------------------------</p><div style="display:flex;justify-content:space-between;font-size:16px"><b>TOTAL USD</b><b>{b['total']}</b></div>{note}
<p style="text-align:center;font-size:10px;margin-top:22px">{MARK}</p></div>"""


def _inv(b):
    n, v = b["inv_no"], b.get("amb", 0)
    if not v:
        return e(n)
    return smudge(n, len(n) - 1, v) if v != 3 else smudge(n, len(n) - 3, v)


def _due(b, f):
    s, v = f(b["due"]), b.get("amb", 0)
    return smudge(s, s.index(",") - 1, v) if v else e(s)


ALT = {"0": "6", "1": "7", "2": "7", "3": "8", "4": "9", "5": "6", "6": "5", "7": "1", "8": "3", "9": "4"}


def smudge(text: str, idx: int, v: int = 1) -> str:
    """Escape text with the digit at idx written over by a second digit (an ambiguous handwritten character)."""
    d = text[idx]
    rot = {1: "-4deg", 2: "6deg", 3: "-9deg"}[v]
    over = (f'<span style="position:relative;display:inline-block">{d}<span style="position:absolute;left:1px;top:1px;opacity:.75;'
            f'transform:rotate({rot})">{ALT[d]}</span></span>')
    return e(text[:idx]) + over + e(text[idx + 1:])


def _hand(b, f):
    note = f'<p style="margin:8px 0">{e(b["note"])}</p>' if b.get("note") else ""
    ink = "font-family:'Ink Free','Segoe Script','Bradley Hand',cursive;color:#1b3a8f;font-size:21px"
    return f"""<div class="paper" style="width:540px;min-height:400px;background:#fbf7e6 repeating-linear-gradient(transparent 0 33px,#bcd3e6 33px 34px);padding:26px 34px;color:#222;font:14px Arial,sans-serif">
<div style="display:flex;justify-content:space-between;align-items:baseline"><b style="font-size:20px;letter-spacing:1px">DELIVERY BILL</b><span>{e(b['vendor'])}</span></div>
<div style="{ink};margin-top:22px;line-height:34px">To: {CUSTOMER}<br>Bill no: {_inv(b)}<br>Date: {f(b['inv_date'])} &nbsp; Pay by: {_due(b, f)}<br>
{_rows(b, '{d} ........ {a}<br>')}<b>Total USD {b['total']}</b></div>{note}
<p style="font-size:10px;color:#777;margin-top:26px">{MARK}</p></div>"""


def _carbon(b, f):
    note = f'<p>{e(b["note"])}</p>' if b.get("note") else ""
    ink = "color:#37408f;text-shadow:1px 1px 0 rgba(55,64,143,.35),0 0 2px rgba(55,64,143,.5)"
    return f"""<div class="paper" style="width:600px;min-height:360px;background:#e3e8f4;{ink};font:15px 'Courier New',monospace;padding:26px 30px">
<div style="display:flex;justify-content:space-between;border-bottom:2px solid #6b74b8;padding-bottom:8px"><b style="font-size:20px">{e(b['vendor'])}</b><b>SALES INVOICE</b></div>
<table style="width:100%;margin-top:14px;font-size:14px"><tr><td>No: {e(b['inv_no'])}</td><td>Date: {f(b['inv_date'])}</td></tr><tr><td>Sold to: {CUSTOMER}</td><td>Due: {f(b['due'])}</td></tr></table>
<div style="margin-top:16px;border:1px solid #6b74b8;padding:8px">{_rows(b, '<div style="display:flex;justify-content:space-between"><span>{d}</span><span>{a}</span></div>')}</div>
<div style="text-align:right;margin-top:12px;font-size:18px"><b>TOTAL USD {b['total']}</b></div>{note}
<p style="font-size:10px;margin-top:24px">{MARK} · customer copy</p></div>"""


def html(layout: str, b: dict) -> str:
    f = lambda d: d.strftime(DATE_FMT[layout])  # noqa: E731
    body = {"a4": _a4, "thermal": _thermal, "hand": _hand, "carbon": _carbon}[layout](b, f)
    return f'<html><body style="margin:0;background:#888;padding:10px;display:inline-block">{body}</body></html>'
