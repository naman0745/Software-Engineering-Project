"""
utils/pdf.py
------------
PDF report generation using ReportLab.
AI narrative is generated locally via Ollama (gemma4:e4b).
"""

import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from config import OLLAMA_MODEL, OLLAMA_MAX_TOKENS, OLLAMA_TEMPERATURE


def generate_narrative(stats: dict) -> str:
    """
    Ask the local Ollama model to write a professional fraud summary.

    Args:
        stats: Dict containing node_count, total_records, total_fraud,
               fraud_rate, decision, and per_node breakdown string.

    Returns:
        Plain-English narrative paragraph from the LLM.
        Falls back to a template string if Ollama is unavailable.
    """
    try:
        import ollama
        prompt = (
            f"Fraud report summary in 2 sentences:\n"
            f"Nodes: {stats['node_count']}, "
            f"Records: {stats['total_records']}, "
            f"Fraud: {stats['total_fraud']} ({stats['fraud_rate']}%), "
            f"Decision: {stats['decision']}, "
            f"Breakdown: {stats['per_node']}"
        )
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"num_predict": OLLAMA_MAX_TOKENS, "temperature": OLLAMA_TEMPERATURE},
            think=False,
        )
        return response["message"]["content"]
    except Exception as e:
        print(f"[PDF] Ollama unavailable: {e}")
        return (
            f"This report covers {stats['node_count']} participating nodes analyzing "
            f"{stats['total_records']:,} transactions in total. "
            f"The system detected {stats['total_fraud']} fraudulent transactions, "
            f"representing a fraud rate of {stats['fraud_rate']}%. "
            f"Final collaborative decision: {stats['decision']}."
        )


def build_pdf(stats: dict, node_rows: list, narrative: str) -> io.BytesIO:
    """
    Build and return a PDF report as a BytesIO buffer.

    Args:
        stats:     Global summary statistics dict.
        node_rows: List of per-node result dicts.
        narrative: AI-generated or fallback narrative string.

    Returns:
        BytesIO buffer containing the rendered PDF.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    _, h = A4

    # ── Title ───────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, h - 60, "TrustGrid — Fraud Detection Report")

    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(50, h - 80, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ── Global Summary ──────────────────────────────────────
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, h - 120, "Global Summary")

    c.setFont("Helvetica", 11)
    y = h - 145
    for line in [
        f"Participating Nodes : {stats['node_count']}",
        f"Total Records       : {stats['total_records']:,}",
        f"Fraud Detected      : {stats['total_fraud']}",
        f"Fraud Rate          : {stats['fraud_rate']}%",
        f"Final Decision      : {stats['decision']}",
    ]:
        c.drawString(50, y, line)
        y -= 20

    # ── Per-Node Breakdown ──────────────────────────────────
    y -= 20
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Per-Node Breakdown")
    y -= 25
    c.setFont("Helvetica", 11)
    for r in node_rows:
        fraud_r = r["fraud"]
        tot     = r["total"]
        rate    = round(fraud_r / tot * 100, 1) if tot else 0
        c.drawString(50, y, f"{r['company']}:  {fraud_r} fraud / {tot} total  ({rate}%)")
        y -= 20

    # ── AI Narrative ────────────────────────────────────────
    y -= 20
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "AI Analysis Summary")
    y -= 25
    c.setFont("Helvetica", 10)

    # Word-wrap narrative to fit page width
    words, line_buf = narrative.split(), []
    for word in words:
        line_buf.append(word)
        if len(" ".join(line_buf)) > 90:
            c.drawString(50, y, " ".join(line_buf[:-1]))
            y -= 16
            line_buf = [word]
    if line_buf:
        c.drawString(50, y, " ".join(line_buf))

    c.save()
    buffer.seek(0)
    return buffer
