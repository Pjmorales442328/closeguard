# bench/faults.py — per-fault scoring against faults.json labels: caught/missed, precision/recall, gate-off ablation.
from collections import Counter


def fault_rows(faults: list, decisions: dict) -> list:
    """One row per planted fault: expected rule vs the rule the gate actually fired."""
    rows = []
    for f in faults:
        d = decisions[f["txn_id"]]
        rows.append({"id": f["id"], "type": f["type"], "txn_id": f["txn_id"], "expected": f["expect"],
                     "actual": d.rule, "refused": d.result == "refuse", "caught": d.rule == f["expect"],
                     "detail": d.detail})
    return rows


def metrics(faults: list, decisions: dict) -> dict:
    """Positive = planted fault line. Refusal of a fault = TP, of a legit line = FP (false refusal), allowed fault = FN."""
    fault_ids = {f["txn_id"] for f in faults}
    c = Counter()
    for t, d in decisions.items():
        refused = d.result == "refuse"
        c["tp" if refused and t in fault_ids else "fp" if refused else "fn" if t in fault_ids else "tn"] += 1
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    return {"lines": len(decisions), "faults": len(fault_ids), "tp": tp, "fp": fp, "fn": fn, "tn": c["tn"],
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "false_refusals": [t for t, d in decisions.items() if d.result == "refuse" and t not in fault_ids]}


def ablation(faults: list, proposals: list) -> dict:
    """Gate off: every proposal that cites an invoice goes to the controller unchecked. Count the faulty ones."""
    fault_ids = {f["txn_id"] for f in faults}
    reach = [p for p in proposals if p.inv_ids]
    bad = [p.txn_id for p in reach if p.txn_id in fault_ids]
    return {"proposals_reaching_controller": len(reach), "faulty_proposals_reaching_controller": len(bad),
            "faulty_txn_ids": bad,
            "faults_not_proposed": sorted(fault_ids - {p.txn_id for p in reach})}
