"""
Standa Hill Kalungu — Fee Tracker & Receipt Generator
======================================================
Backend module for:
  - Recording student fee payments
  - Tracking balances per student
  - Generating PDF receipts
  - Listing outstanding balances
  - Generating defaulter reports
"""

import json
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

# ── CONFIG ──────────────────────────────────────────────────────────────────
SCHOOL_NAME   = "Standa Hill Kalungu"
SCHOOL_MOTTO  = "Excellence Through Discipline"
SCHOOL_ADDR   = "Kalungu District, Central Uganda"
SCHOOL_TEL    = "+256 700 000000"
CURRENCY      = "UGX"
DB_FILE       = "fee_records.json"          # Flat-file "database"
RECEIPTS_DIR  = "receipts"

TERM_FEES = {                                # Expected fees per term (UGX)
    "S1": 450_000,
    "S2": 450_000,
    "S3": 480_000,
    "S4": 500_000,
    "S5": 520_000,
    "S6": 520_000,
    "P1": 250_000,
    "P2": 250_000,
    "P3": 260_000,
    "P4": 270_000,
    "P5": 280_000,
    "P6": 290_000,
    "P7": 300_000,
}

# ── STORAGE HELPERS ──────────────────────────────────────────────────────────
def _load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f:
            return json.load(f)
    return {"students": {}, "payments": [], "receipt_counter": 1000}

def _save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)

def _next_receipt_no(db):
    no = db["receipt_counter"]
    db["receipt_counter"] += 1
    return f"SHK-{no:05d}"

os.makedirs(RECEIPTS_DIR, exist_ok=True)

# ── STUDENT MANAGEMENT ───────────────────────────────────────────────────────
def add_student(student_id: str, name: str, class_level: str, parent_name: str = "", parent_tel: str = ""):
    """Register a student in the fee system."""
    db = _load_db()
    db["students"][student_id] = {
        "name": name,
        "class": class_level.upper(),
        "parent_name": parent_name,
        "parent_tel": parent_tel,
        "created": datetime.now().isoformat()
    }
    _save_db(db)
    print(f"✅ Student registered: {name} ({student_id}) — {class_level.upper()}")

def get_student(student_id: str):
    db = _load_db()
    return db["students"].get(student_id)

# ── FEE RECORDING ────────────────────────────────────────────────────────────
def record_payment(student_id: str, amount: int, term: str, academic_year: str,
                   payment_method: str = "Cash", notes: str = "") -> str:
    """
    Record a fee payment and return the receipt number.
    term format: 'Term 1', 'Term 2', 'Term 3'
    academic_year format: '2026'
    """
    db = _load_db()
    student = db["students"].get(student_id)
    if not student:
        raise ValueError(f"Student '{student_id}' not found. Register them first.")

    receipt_no = _next_receipt_no(db)
    payment = {
        "receipt_no": receipt_no,
        "student_id": student_id,
        "student_name": student["name"],
        "class": student["class"],
        "amount": amount,
        "term": term,
        "academic_year": academic_year,
        "payment_method": payment_method,
        "notes": notes,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cashier": "Admin"
    }
    db["payments"].append(payment)
    _save_db(db)

    # Generate PDF receipt
    pdf_path = _generate_receipt_pdf(payment, student)
    print(f"✅ Payment recorded — Receipt: {receipt_no} | Amount: {CURRENCY} {amount:,}")
    print(f"   PDF saved → {pdf_path}")
    return receipt_no

# ── BALANCE CALCULATION ───────────────────────────────────────────────────────
def get_balance(student_id: str, term: str, academic_year: str) -> dict:
    """Return paid, expected, and outstanding balance for a student/term."""
    db = _load_db()
    student = db["students"].get(student_id)
    if not student:
        raise ValueError(f"Student '{student_id}' not found.")

    paid = sum(
        p["amount"] for p in db["payments"]
        if p["student_id"] == student_id
        and p["term"] == term
        and p["academic_year"] == academic_year
    )
    expected = TERM_FEES.get(student["class"], 0)
    outstanding = max(0, expected - paid)
    return {
        "student_id": student_id,
        "student_name": student["name"],
        "class": student["class"],
        "term": term,
        "academic_year": academic_year,
        "expected": expected,
        "paid": paid,
        "outstanding": outstanding,
        "status": "Cleared" if outstanding == 0 else "Partial" if paid > 0 else "Unpaid"
    }

# ── REPORTS ───────────────────────────────────────────────────────────────────
def list_defaulters(term: str, academic_year: str):
    """Print all students with outstanding balances."""
    db = _load_db()
    print(f"\n{'─'*60}")
    print(f"  DEFAULTERS REPORT — {term} {academic_year}")
    print(f"{'─'*60}")
    print(f"  {'ID':<10} {'Name':<25} {'Class':<6} {'Paid':>10} {'Owed':>10} {'Status'}")
    print(f"{'─'*60}")
    total_owed = 0
    count = 0
    for sid in db["students"]:
        b = get_balance(sid, term, academic_year)
        if b["outstanding"] > 0:
            count += 1
            total_owed += b["outstanding"]
            print(f"  {sid:<10} {b['student_name']:<25} {b['class']:<6} "
                  f"{CURRENCY} {b['paid']:>8,}  {CURRENCY} {b['outstanding']:>8,}  {b['status']}")
    print(f"{'─'*60}")
    print(f"  Total defaulters: {count}  |  Total owed: {CURRENCY} {total_owed:,}")
    print(f"{'─'*60}\n")

def payment_history(student_id: str):
    """Print all payments for a student."""
    db = _load_db()
    student = db["students"].get(student_id)
    if not student:
        print(f"Student '{student_id}' not found.")
        return
    payments = [p for p in db["payments"] if p["student_id"] == student_id]
    print(f"\n  Payment history for {student['name']} ({student_id})")
    print(f"  {'Receipt':<14} {'Term':<10} {'Year':<6} {'Amount':>12} {'Method':<10} {'Date'}")
    print(f"  {'─'*70}")
    for p in payments:
        print(f"  {p['receipt_no']:<14} {p['term']:<10} {p['academic_year']:<6} "
              f"{CURRENCY} {p['amount']:>8,}  {p['payment_method']:<10} {p['date'][:10]}")
    total = sum(p['amount'] for p in payments)
    print(f"  {'─'*70}")
    print(f"  Total paid (all terms): {CURRENCY} {total:,}\n")

# ── PDF RECEIPT GENERATOR ─────────────────────────────────────────────────────
def _generate_receipt_pdf(payment: dict, student: dict) -> str:
    filename = os.path.join(RECEIPTS_DIR, f"{payment['receipt_no']}.pdf")
    doc = SimpleDocTemplate(filename, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    blue    = colors.HexColor("#1e50a2")
    dkblue  = colors.HexColor("#0a1628")
    green   = colors.HexColor("#16a34a")
    ltgray  = colors.HexColor("#f1f5f9")
    midgray = colors.HexColor("#64748b")

    h1 = ParagraphStyle("h1", fontSize=20, fontName="Helvetica-Bold",
                         textColor=dkblue, alignment=TA_CENTER, spaceAfter=4)
    h2 = ParagraphStyle("h2", fontSize=11, fontName="Helvetica",
                         textColor=midgray, alignment=TA_CENTER, spaceAfter=2)
    h3 = ParagraphStyle("h3", fontSize=9, fontName="Helvetica",
                         textColor=midgray, alignment=TA_CENTER, spaceAfter=12)
    receipt_style = ParagraphStyle("rcpt", fontSize=13, fontName="Helvetica-Bold",
                                    textColor=blue, alignment=TA_RIGHT)
    label_style  = ParagraphStyle("lbl", fontSize=9, fontName="Helvetica-Bold",
                                   textColor=midgray)
    value_style  = ParagraphStyle("val", fontSize=10, fontName="Helvetica",
                                   textColor=dkblue)
    amount_style = ParagraphStyle("amt", fontSize=22, fontName="Helvetica-Bold",
                                   textColor=green, alignment=TA_CENTER, spaceBefore=6, spaceAfter=6)
    footer_style = ParagraphStyle("ftr", fontSize=8, fontName="Helvetica",
                                   textColor=midgray, alignment=TA_CENTER)

    story = []

    # ── Header ──
    story.append(Paragraph(SCHOOL_NAME, h1))
    story.append(Paragraph(SCHOOL_MOTTO, h2))
    story.append(Paragraph(f"{SCHOOL_ADDR}  |  Tel: {SCHOOL_TEL}", h3))
    story.append(HRFlowable(width="100%", thickness=2, color=blue, spaceAfter=8))

    # ── Receipt title + number ──
    story.append(Paragraph(f"OFFICIAL FEE RECEIPT — {payment['receipt_no']}", receipt_style))
    story.append(Spacer(1, 0.3*cm))

    # ── Student details table ──
    details = [
        ["Student Name", student["name"],   "Receipt No.",  payment["receipt_no"]],
        ["Student ID",   payment["student_id"], "Date",     payment["date"][:10]],
        ["Class",        student["class"],   "Academic Year", payment["academic_year"]],
        ["Term",         payment["term"],    "Method",       payment["payment_method"]],
    ]
    if student.get("parent_name"):
        details.append(["Parent/Guardian", student["parent_name"], "Contact", student.get("parent_tel","—")])

    tbl = Table(details, colWidths=[3.8*cm, 6.2*cm, 3.8*cm, 4.2*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), ltgray),
        ("BACKGROUND", (2,0), (2,-1), ltgray),
        ("FONTNAME",   (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",   (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("TEXTCOLOR",  (0,0), (0,-1), midgray),
        ("TEXTCOLOR",  (2,0), (2,-1), midgray),
        ("TEXTCOLOR",  (1,0), (1,-1), dkblue),
        ("TEXTCOLOR",  (3,0), (3,-1), dkblue),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, ltgray]),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("PADDING",    (0,0), (-1,-1), 7),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.4*cm))

    # ── Amount box ──
    amount_table = Table(
        [[Paragraph(f"{CURRENCY} {payment['amount']:,}", amount_style)]],
        colWidths=[18*cm]
    )
    amount_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#dcfce7")),
        ("ROUNDEDCORNERS", [8]),
        ("BOX", (0,0), (-1,-1), 1.5, green),
        ("PADDING", (0,0), (-1,-1), 10),
    ]))
    story.append(amount_table)
    story.append(Spacer(1, 0.3*cm))

    # ── Balance info ──
    expected = TERM_FEES.get(student["class"], 0)
    db = _load_db()
    paid_so_far = sum(
        p["amount"] for p in db["payments"]
        if p["student_id"] == payment["student_id"]
        and p["term"] == payment["term"]
        and p["academic_year"] == payment["academic_year"]
    )
    outstanding = max(0, expected - paid_so_far)
    status_color = green if outstanding == 0 else colors.HexColor("#d97706")
    status_text  = "FULLY CLEARED" if outstanding == 0 else f"BALANCE REMAINING: {CURRENCY} {outstanding:,}"

    bal_data = [
        ["Term Fees Expected", f"{CURRENCY} {expected:,}"],
        ["Total Paid (this term)", f"{CURRENCY} {paid_so_far:,}"],
        ["Outstanding Balance", f"{CURRENCY} {outstanding:,}"],
        ["Account Status", "FULLY CLEARED" if outstanding == 0 else "PARTIAL PAYMENT"],
    ]
    bal_tbl = Table(bal_data, colWidths=[9*cm, 9*cm])
    bal_tbl.setStyle(TableStyle([
        ("FONTNAME",   (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("TEXTCOLOR",  (0,0), (0,-1), midgray),
        ("TEXTCOLOR",  (1,0), (1,-2), dkblue),
        ("TEXTCOLOR",  (1,3), (1,3), green if outstanding == 0 else colors.HexColor("#d97706")),
        ("FONTNAME",   (1,3), (1,3), "Helvetica-Bold"),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0,0), (0,-1), ltgray),
        ("PADDING",    (0,0), (-1,-1), 7),
    ]))
    story.append(bal_tbl)
    story.append(Spacer(1, 0.4*cm))

    # ── Notes ──
    if payment.get("notes"):
        story.append(Paragraph(f"Notes: {payment['notes']}", value_style))
        story.append(Spacer(1, 0.2*cm))

    # ── Footer ──
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceBefore=8, spaceAfter=8))
    story.append(Paragraph(
        f"This is an official receipt issued by {SCHOOL_NAME}. Please retain for your records.<br/>"
        f"Generated on {datetime.now().strftime('%d %b %Y at %H:%M')}  |  {SCHOOL_ADDR}",
        footer_style
    ))
    story.append(Spacer(1, 1.5*cm))

    # ── Signature line ──
    sig_tbl = Table(
        [["_________________________", "", "_________________________"],
         ["Received By (Cashier)", "", "Parent / Guardian Signature"]],
        colWidths=[7*cm, 4*cm, 7*cm]
    )
    sig_tbl.setStyle(TableStyle([
        ("FONTSIZE",  (0,0), (-1,-1), 8),
        ("TEXTCOLOR", (0,0), (-1,-1), midgray),
        ("ALIGN",     (0,0), (0,-1), "LEFT"),
        ("ALIGN",     (2,0), (2,-1), "RIGHT"),
    ]))
    story.append(sig_tbl)

    doc.build(story)
    return filename


# ── DEMO ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  Standa Hill Kalungu — Fee Tracker Demo")
    print("="*60)

    # Register students
    add_student("STU001", "Nakato Aisha",     "S3", "Mr. Ssemakula David",  "+256 772 111111")
    add_student("STU002", "Ochieng Brian",    "S1", "Mrs. Ochieng Grace",   "+256 701 222222")
    add_student("STU003", "Tendo Patience",   "P6", "Mr. Tendo Robert",     "+256 756 333333")
    add_student("STU004", "Mugisha Emmanuel", "S4", "Mrs. Mugisha Harriet",  "+256 782 444444")

    # Record payments
    record_payment("STU001", 300_000, "Term 2", "2026", "Mobile Money", "First instalment")
    record_payment("STU001", 180_000, "Term 2", "2026", "Cash",          "Second instalment")
    record_payment("STU002", 450_000, "Term 2", "2026", "Bank Transfer", "Full payment")
    record_payment("STU003", 150_000, "Term 2", "2026", "Cash",          "Partial")
    record_payment("STU004", 200_000, "Term 2", "2026", "Mobile Money")

    # Show defaulters
    list_defaulters("Term 2", "2026")

    # Show payment history
    payment_history("STU001")

    # Show individual balance
    b = get_balance("STU003", "Term 2", "2026")
    print(f"  Balance check → {b['student_name']}: Paid {CURRENCY} {b['paid']:,} | Outstanding {CURRENCY} {b['outstanding']:,} | {b['status']}\n")
