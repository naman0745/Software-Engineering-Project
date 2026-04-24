"""
routes/report.py
----------------
PDF report generation endpoint.

Endpoint
--------
GET /report — generate and return a PDF fraud detection report
"""

from flask import Blueprint, send_file

from config import FRAUD_RATE_THRESHOLD
from database.schema import get_db
from utils.pdf import generate_narrative, build_pdf

report_bp = Blueprint("report", __name__)


@report_bp.route("/report", methods=["GET"])
def generate_report():
    """
    Generate a downloadable PDF fraud detection report.

    The report includes:
        - Global summary (node count, totals, decision)
        - Per-node breakdown
        - AI-generated narrative (via Ollama/gemma4:e4b)

    Returns the PDF as a file attachment.
    """
    conn = get_db()

    node_rows = conn.execute("""
        SELECT company, COUNT(*) AS total, SUM(is_fraud) AS fraud
        FROM   transactions
        GROUP  BY node_id
    """).fetchall()

    global_row = conn.execute("""
        SELECT COUNT(*) AS total, SUM(is_fraud) AS fraud
        FROM   transactions
    """).fetchone()

    conn.close()

    total    = global_row["total"] or 0
    fraud    = global_row["fraud"] or 0
    rate     = round(fraud / total * 100, 2) if total else 0
    decision = "FRAUD DETECTED" if rate > FRAUD_RATE_THRESHOLD else "SAFE"

    per_node_str = ", ".join(
        f"{r['company']}: {r['fraud']}/{r['total']} fraud"
        for r in node_rows
    )

    stats = {
        "node_count":    len(node_rows),
        "total_records": total,
        "total_fraud":   fraud,
        "fraud_rate":    rate,
        "decision":      decision,
        "per_node":      per_node_str,
    }

    narrative = generate_narrative(stats)
    buffer    = build_pdf(stats, [dict(r) for r in node_rows], narrative)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="trustgrid_report.pdf",
    )
