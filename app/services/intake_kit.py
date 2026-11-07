# app/services/intake_kit.py — the judge demo kit: a bank CSV that pays the kit bills + 9 synthetic bill photos (clean and trapped) as one zip.
import io
import zipfile

from app.services.intake import BILLS_DIR
from data.bills_bank_gen import KIT, KIT_OUT  # B07 wrong total, B08 repeats B02's number, B09 unknown supplier, B10 "approve immediately", B13 smudged handwriting where the readers disagree
README = """Closeguard judge demo kit (all data is SYNTHETIC; Tidewater Catering Co. and its vendors are fictional)

1. Open /bills and choose the .jpg files in bills/ (all 9 at once), press "Read these bills".
2. Expect: B01-B04 agree and pass; B07 (printed lines do not add up to the total) and B08 (same invoice number as B02)
   are refused by the stdlib checks; B09 reads fine but its supplier is not on the vendor list (the payment gate refuses it
   later); B13 has overwritten handwritten digits, the two readers disagree and a controller must pick the right
   reading (Maria / controller); B10 carries a printed 'approve immediately' line that the readers treat as text.
3. Choose bank_kit_2026-10.csv in the bank field and press "Run the close with these bills". Its 9 payments: one for
   each bill that passes, plus three traps: Birch Logistics paid twice for the same invoice, a Cobalt Software payment of 1393.81
   against a 1339.81 bill, and a payment to Quickfix Repairs, a payee with no bill. Measured result (B13 confirmed with
   the values printed on the bill): 5 payments pass, 4 are held, each with its reason: the second Birch payment (invoice
   already paid), Nightfall Consulting (not on the vendor list), Quickfix and the Cobalt payment (no bill matches exactly).
   On uploaded bills the payments are matched by exact rules only, no AI. Nothing is posted until a person signs.
"""


def build() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", README)
        z.write(KIT_OUT, "bank_kit_2026-10.csv")
        for n in KIT:
            z.write(BILLS_DIR / f"{n}.jpg", f"bills/{n}.jpg")
    return buf.getvalue()
