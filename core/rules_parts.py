# core/rules_parts.py — gate rule 11: each allocated part must equal the invoice amount. A short-pay never settles an invoice.
def part_mismatch(p, c):
    for i, v in p.parts.items():
        if v != c.ledger[i].amount:
            return f"part {v} for {i} != invoice amount {c.ledger[i].amount}"
