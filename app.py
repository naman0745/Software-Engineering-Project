"""
TrustGrid - Federated Fraud Detection Backend
=============================================
Run: python app.py
Requires: pip install flask flask-cors pandas
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import hashlib
import pandas as pd
import os
import csv
import json
from datetime import datetime
import ollama
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from flask import send_file
import io

app = Flask(__name__)
CORS(app)  # Allow frontend to call this backend from any origin

UPLOAD_FOLDER = "uploads"
DB_PATH = "trustgrid.db"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─────────────────────────────────────────────
#  DATABASE SETUP
# ─────────────────────────────────────────────

def get_db():
    """Open a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Rows behave like dicts
    return conn

def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    c = conn.cursor()

    # Users / Nodes table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id  TEXT    UNIQUE NOT NULL,
            key_hash TEXT    NOT NULL,
            company  TEXT    NOT NULL,
            ip       TEXT,
            created  TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Transactions table  (hashed amounts for privacy)
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            company    TEXT    NOT NULL,
            node_id    TEXT    NOT NULL,
            amount_hash TEXT   NOT NULL,
            is_fraud   INTEGER NOT NULL,   -- 1 = fraud, 0 = safe
            created    TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Fraud outcomes / case memory
    c.execute("""
        CREATE TABLE IF NOT EXISTS fraud_outcomes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            participating_nodes TEXT NOT NULL,   -- JSON list
            total_records       INTEGER,
            total_fraud         INTEGER,
            node_count          INTEGER,
            decision            TEXT,            -- "FRAUD DETECTED" | "SAFE"
            created             TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def sha256(value: str) -> str:
    """Return SHA-256 hex digest of any string."""
    return hashlib.sha256(str(value).encode()).hexdigest()

def check_fraud_rules(amount, time_str):
    """
    Local fraud rules (applied per transaction):
      1. Amount > 10,000  → fraud
      2. Transaction hour < 5 (before 5 AM) → fraud
    Returns True if fraudulent.
    """
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        amount = 0

    fraud = False
    if amount > 10000:
        fraud = True

    try:
        # Accept formats:  "02:30", "02:30:00", or full datetime
        hour = int(str(time_str).split(":")[0].split(" ")[-1])
        if hour < 5:
            fraud = True
    except Exception:
        pass

    return fraud

def generate_narrative(stats: dict) -> str:
    """Ask local Ollama to write a plain-English fraud summary."""
    prompt = f"""
You are a fraud analyst. Write a 3-4 sentence professional summary 
based on this data. Be concise and specific.

Data:
- Participating nodes: {stats['node_count']}
- Total transactions analyzed: {stats['total_records']}
- Fraudulent transactions: {stats['total_fraud']}
- Fraud rate: {stats['fraud_rate']}%
- Final decision: {stats['decision']}
- Per-node breakdown: {stats['per_node']}

Write only the summary paragraph, no headings.
"""
    response = ollama.chat(
        model='gemma4:e4b',
        messages=[{'role': 'user', 'content': prompt}],
        options={'num_predict': 150, 'temperature': 0.3},
        think=False
    )
    return response['message']['content']

# ─────────────────────────────────────────────
#  ENDPOINT 1 — LOGIN / REGISTER
#  POST /login
#  Body: { "node_id": "...", "key": "...", "company": "..." }
# ─────────────────────────────────────────────

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    node_id = data.get("node_id", "").strip()
    key     = data.get("key", "").strip()
    company = data.get("company", "").strip()

    # 1. Database logic (Keep hash for security)
    key_hash = sha256(key)
    conn = get_db()
    c = conn.cursor()
    existing = c.execute("SELECT * FROM users WHERE node_id = ?", (node_id,)).fetchone()
    
    if existing:
        conn.close()
        return jsonify({"success": False, "message": "Node ID already exists"}), 409

    # Block same IP from registering more than one node
    client_ip = request.remote_addr
    existing_ip = c.execute("SELECT node_id FROM users WHERE ip = ?", (client_ip,)).fetchone()
    if existing_ip:
        conn.close()
        return jsonify({
            "success": False,
            "message": f"A node already exists from this device (Node ID: {existing_ip['node_id']}). Only one node per device is allowed."
        }), 403

    c.execute("INSERT INTO users (node_id, key_hash, company, ip) VALUES (?, ?, ?, ?)",
              (node_id, key_hash, company, client_ip))
    conn.commit()
    conn.close()

    # 2. SAVE TO EXCEL (CSV) - Plain text for your reference
    file_exists = os.path.isfile('node_credentials.csv')
    with open('node_credentials.csv', 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Node ID', 'Company Name', 'Secure Key'])
        writer.writerow([node_id, company, key])

    return jsonify({"success": True, "message": "Registration complete. Please proceed for login."})

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    node_id = data.get("node_id", "").strip()
    key     = data.get("key", "").strip()

    if not node_id or not key:
        return jsonify({"success": False, "message": "Node ID and key are required"}), 400

    key_hash = sha256(key)
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE node_id = ?", (node_id,)).fetchone()
    conn.close()

    if user:
        if user["key_hash"] == key_hash:
            return jsonify({
                "success": True,
                "message": f"Welcome back, {user['company']}!",
                "node_id": node_id,
                "company": user["company"]
            })
        return jsonify({"success": False, "message": "Incorrect secure key"}), 401
    
    return jsonify({"success": False, "message": "Node ID not found"}), 404


# ─────────────────────────────────────────────
#  ENDPOINT 2 — UPLOAD CSV
#  POST /upload
#  Form-data: file=<CSV>, node_id=<str>
# ─────────────────────────────────────────────

@app.route("/upload", methods=["POST"])
def upload():
    node_id = request.form.get("node_id", "").strip()
    if not node_id:
        return jsonify({"success": False, "message": "node_id is required"}), 400

    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file uploaded"}), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({"success": False, "message": "Empty filename"}), 400

    # Verify node exists
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE node_id = ?", (node_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"success": False, "message": "Node not found. Login first."}), 404

    company = user["company"]

    # Save file temporarily
    filepath = os.path.join(UPLOAD_FOLDER, f"{node_id}_{f.filename}")
    f.save(filepath)
    conn.close()

    return jsonify({
        "success":  True,
        "message":  f"File uploaded for {company}. Now call /analyze to process it.",
        "filepath": filepath,
        "node_id":  node_id,
        "company":  company
    })

# ─────────────────────────────────────────────
#  ENDPOINT 3 — ANALYZE CSV
#  POST /analyze
#  Body: { "node_id": "..." }
#  Looks for the last uploaded file for this node
# ─────────────────────────────────────────────

@app.route("/analyze", methods=["POST"])
def analyze():
    data    = request.get_json()
    node_id = data.get("node_id", "").strip()

    if not node_id:
        return jsonify({"success": False, "message": "node_id is required"}), 400

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE node_id = ?", (node_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"success": False, "message": "Node not found"}), 404

    company = user["company"]

    # Find uploaded file for this node
    uploaded_files = [
        f for f in os.listdir(UPLOAD_FOLDER)
        if f.startswith(node_id + "_")
    ]
    if not uploaded_files:
        conn.close()
        return jsonify({"success": False, "message": "No uploaded file found. Upload first."}), 404

    filepath = os.path.join(UPLOAD_FOLDER, sorted(uploaded_files)[-1])   # most recent

    # ── Read CSV ──
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "message": f"CSV read error: {str(e)}"}), 500

    # Normalise column names (lowercase, strip spaces)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Detect amount column (first numeric column is used as fallback)
    amount_col = None
    for candidate in ["amount", "transaction_amount", "value", "amt"]:
        if candidate in df.columns:
            amount_col = candidate
            break
    if amount_col is None:
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        amount_col = numeric_cols[0] if numeric_cols else None

    # Detect time column
    time_col = None
    for candidate in ["time", "transaction_time", "timestamp", "datetime", "hour"]:
        if candidate in df.columns:
            time_col = candidate
            break

    # ── Apply fraud rules & insert into DB ──
    # Validate required columns exist
    if amount_col is None:
        conn.close()
        return jsonify({
            "success": False,
            "message": f"CSV is missing an amount column. Found columns: {list(df.columns)}. Rename your column to 'amount'."
        }), 400

    if time_col is None:
        conn.close()
        return jsonify({
            "success": False,
            "message": f"CSV is missing a time column. Found columns: {list(df.columns)}. Rename your column to 'time'."
        }), 400

    # Clear previous transactions for this node
    conn.execute("DELETE FROM transactions WHERE node_id = ?", (node_id,))

    total   = len(df)
    n_fraud = 0

    for _, row in df.iterrows():
        amount = row[amount_col] if amount_col else 0
        time   = row[time_col]   if time_col   else "12:00"
        is_fraud = 1 if check_fraud_rules(amount, time) else 0
        n_fraud += is_fraud

        conn.execute(
            "INSERT INTO transactions (company, node_id, amount_hash, is_fraud) VALUES (?, ?, ?, ?)",
            (company, node_id, sha256(amount), is_fraud)
        )

    conn.commit()
    conn.close()

    return jsonify({
        "success":     True,
        "company":     company,
        "node_id":     node_id,
        "total":       total,
        "fraud_count": n_fraud,
        "safe_count":  total - n_fraud,
        "fraud_rate":  round(n_fraud / total * 100, 2) if total else 0,
        "message":     f"Analysis complete for {company}"
    })

# ─────────────────────────────────────────────
#  ENDPOINT 4 — PER-NODE RESULTS
#  GET /results
# ─────────────────────────────────────────────

@app.route("/results", methods=["GET"])
def results():
    node_id = request.args.get("node_id")
    conn = get_db()
    # If node_id is provided, show only that node. Otherwise show all (for global view).
    query = "SELECT company, node_id, COUNT(*) AS total, SUM(is_fraud) AS fraud_count FROM transactions"
    params = []
    
    if node_id:
        query += " WHERE node_id = ?"
        params.append(node_id)
    
    query += " GROUP BY node_id"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    data = [{
        "company": r["company"],
        "node_id": r["node_id"],
        "total": r["total"],
        "fraud_count": r["fraud_count"],
        "safe_count": r["total"] - r["fraud_count"],
        "fraud_rate": round(r["fraud_count"] / r["total"] * 100, 2) if r["total"] else 0
    } for r in rows]

    return jsonify({"success": True, "results": data})


# ─────────────────────────────────────────────
#  ENDPOINT 5 — GLOBAL / COLLABORATIVE ANALYSIS
#  GET /global_analysis
# ─────────────────────────────────────────────

@app.route("/global_analysis", methods=["GET"])
def global_analysis():
    conn = get_db()

    # How many distinct nodes have uploaded data in the last 24 hours?
    nodes_with_data = conn.execute("""
        SELECT DISTINCT node_id FROM transactions
        WHERE created >= datetime('now', '-24 hours')
    """).fetchall()
    node_count = len(nodes_with_data)

    if node_count < 2:
        conn.close()
        return jsonify({
            "success":    False,
            "message":    f"Only {node_count} node(s) have submitted data in the last 24 hours. Minimum 2 required for collaborative fraud detection.",
            "node_count": node_count
        }), 400

    # Aggregate (last 24 hours only)
    row = conn.execute("""
        SELECT COUNT(*)      AS total_records,
               SUM(is_fraud) AS total_fraud
        FROM   transactions
        WHERE  created >= datetime('now', '-24 hours')
    """).fetchone()

    total   = row["total_records"]
    fraud   = row["total_fraud"] or 0
    safe    = total - fraud
    rate    = round(fraud / total * 100, 2) if total else 0

    # Decision rule: if >5% of transactions are fraud → FRAUD DETECTED
    decision = "FRAUD DETECTED" if rate > 5 else "SAFE"

    # Save this outcome in memory
    node_ids = [n["node_id"] for n in nodes_with_data]
    conn.execute("""
        INSERT INTO fraud_outcomes
               (participating_nodes, total_records, total_fraud, node_count, decision)
        VALUES (?, ?, ?, ?, ?)
    """, (json.dumps(node_ids), total, fraud, node_count, decision))
    conn.commit()
    conn.close()

    return jsonify({
        "success":      True,
        "node_count":   node_count,
        "total_records": total,
        "total_fraud":   fraud,
        "total_safe":    safe,
        "fraud_rate":    rate,
        "decision":      decision,
        "message":       f"Global analysis complete across {node_count} nodes"
    })

# ─────────────────────────────────────────────
#  ENDPOINT 6 — ACTIVITY LOGS
#  GET /logs
# ─────────────────────────────────────────────

@app.route("/logs", methods=["GET"])
def logs():
    # Get node_id from the request parameters
    node_id = request.args.get("node_id")
    if not node_id:
        return jsonify({"success": False, "message": "node_id required"}), 400

    conn = get_db()
    # Updated SQL: Added WHERE node_id = ?
    rows = conn.execute("""
        SELECT company, amount_hash, is_fraud, created
        FROM   transactions
        WHERE  node_id = ?
        ORDER  BY id DESC
        LIMIT  20
    """, (node_id,)).fetchall()
    conn.close()

    logs_list = [{
        "company": r["company"],
        "hash_preview": r["amount_hash"][:12] + "...",
        "status": "FRAUD" if r["is_fraud"] else "SAFE",
        "timestamp": r["created"]
    } for r in rows]

    return jsonify({"success": True, "logs": logs_list})


# ─────────────────────────────────────────────
#  ENDPOINT 7 — ACTIVE NODES LIST
#  GET /nodes
# ─────────────────────────────────────────────

@app.route("/nodes", methods=["GET"])
def nodes():
    conn = get_db()
    rows = conn.execute("""
        SELECT u.node_id,
               u.company,
               u.created,
               CASE WHEN t.node_id IS NOT NULL THEN 1 ELSE 0 END AS has_data
        FROM   users u
        LEFT JOIN (
            SELECT DISTINCT node_id FROM transactions
        ) t ON u.node_id = t.node_id
    """).fetchall()
    conn.close()

    nodes_list = [
        {
            "node_id":  r["node_id"],
            "company":  r["company"],
            "joined":   r["created"],
            "has_data": bool(r["has_data"])
        }
        for r in rows
    ]

    return jsonify({"success": True, "nodes": nodes_list, "count": len(nodes_list)})

# ─────────────────────────────────────────────
#  ENDPOINT 8 — PAST OUTCOMES (Case Memory)
#  GET /outcomes
# ─────────────────────────────────────────────

@app.route("/outcomes", methods=["GET"])
def outcomes():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM fraud_outcomes ORDER BY id DESC LIMIT 10
    """).fetchall()
    conn.close()

    data = [
        {
            "id":           r["id"],
            "nodes":        json.loads(r["participating_nodes"]),
            "total_records": r["total_records"],
            "total_fraud":   r["total_fraud"],
            "node_count":   r["node_count"],
            "decision":     r["decision"],
            "timestamp":    r["created"]
        }
        for r in rows
    ]
    return jsonify({"success": True, "outcomes": data})

@app.route("/report", methods=["GET"])
def generate_report():
    conn = get_db()

    # Fetch per-node data
    node_rows = conn.execute("""
        SELECT company, COUNT(*) AS total, SUM(is_fraud) AS fraud
        FROM transactions GROUP BY node_id
    """).fetchall()

    # Fetch global data
    global_row = conn.execute("""
        SELECT COUNT(*) AS total, SUM(is_fraud) AS fraud
        FROM transactions
    """).fetchone()

    conn.close()

    total   = global_row['total'] or 0
    fraud   = global_row['fraud'] or 0
    rate    = round(fraud / total * 100, 2) if total else 0
    decision = "FRAUD DETECTED" if rate > 5 else "SAFE"

    per_node = [
        f"{r['company']}: {r['fraud']}/{r['total']} fraud"
        for r in node_rows
    ]

    stats = {
        'node_count':    len(node_rows),
        'total_records': total,
        'total_fraud':   fraud,
        'fraud_rate':    rate,
        'decision':      decision,
        'per_node':      ', '.join(per_node)
    }

    # Generate AI narrative
    try:
        narrative = generate_narrative(stats)
    except Exception as e:
        print(f"Ollama error: {e}")
        narrative = "Ollama not running. Start it with: ollama serve"

    # Build PDF
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4

    # Title
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, h - 60, "TrustGrid Fraud Detection Report")

    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(50, h - 80, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Global stats
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

    # Per-node breakdown
    y -= 20
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Per-Node Breakdown")
    y -= 25
    c.setFont("Helvetica", 11)
    for r in node_rows:
        fraud_r = r['fraud']
        tot     = r['total']
        fr_rate = round(fraud_r / tot * 100, 1) if tot else 0
        c.drawString(50, y, f"{r['company']}:  {fraud_r} fraud / {tot} total  ({fr_rate}%)")
        y -= 20

    # AI Narrative
    y -= 20
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "AI Analysis Summary")
    y -= 25
    c.setFont("Helvetica", 10)
    # Word-wrap the narrative
    words = narrative.split()
    line_buf, max_w = [], 90
    for word in words:
        line_buf.append(word)
        if len(' '.join(line_buf)) > max_w:
            c.drawString(50, y, ' '.join(line_buf[:-1]))
            y -= 16
            line_buf = [word]
    if line_buf:
        c.drawString(50, y, ' '.join(line_buf))

    c.save()
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='trustgrid_report.pdf'
    )
# ─────────────────────────────────────────────
#  ENDPOINT — RESET KEY (Authenticated Password Reset)
# ─────────────────────────────────────────────
@app.route("/reset_key", methods=["POST"])
def reset_key():
    data    = request.get_json()
    node_id = data.get("node_id", "").strip()
    company = data.get("company", "").strip()
    new_key = data.get("new_key", "").strip()

    if not node_id or not company or not new_key:
        return jsonify({"success": False, "message": "node_id, company, and new_key are all required"}), 400

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE node_id = ?", (node_id,)).fetchone()

    if not user:
        conn.close()
        return jsonify({"success": False, "message": "Node ID not found"}), 404

    # Company name must match exactly — this is the authentication check
    if user["company"].strip().lower() != company.strip().lower():
        conn.close()
        return jsonify({"success": False, "message": "Company name does not match our records"}), 401

    conn.execute("UPDATE users SET key_hash = ? WHERE node_id = ?", (sha256(new_key), node_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Key reset successfully. You can now login with your new key."})


# ─────────────────────────────────────────────
#  ENDPOINT — CLEAR DATA (Remove stale transactions)
# ─────────────────────────────────────────────
@app.route("/clear_data", methods=["POST"])
def clear_data():
    data    = request.get_json()
    node_id = data.get("node_id", "").strip()
    if not node_id:
        return jsonify({"success": False, "message": "node_id required"}), 400

    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE node_id = ?", (node_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Data cleared successfully"})


@app.route("/discontinue", methods=["POST"])
def discontinue():
    data = request.get_json()
    node_id = data.get("node_id")
    
    conn = get_db()
    # This deletes the transaction data for this node, effectively "disconnecting" its signals
    conn.execute("DELETE FROM transactions WHERE node_id = ?", (node_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Connection discontinued and data cleared."})


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("\n" + "="*50)
    print("  TrustGrid Backend  —  http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=True, port=5000)
