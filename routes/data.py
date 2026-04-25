"""
routes/data.py
--------------
Data ingestion routes: upload CSV, analyze, clear.

Endpoints
---------
POST /upload      — upload a CSV dataset for a node
POST /analyze     — run fraud detection on uploaded CSV
POST /clear_data  — delete a node's transaction data
"""

import os

import pandas as pd
from flask import Blueprint, request, jsonify

from config import UPLOAD_FOLDER
from database.schema import get_db
from utils.crypto import sha256
from utils.fraud import is_fraudulent, detect_amount_column, detect_time_column

data_bp = Blueprint("data", __name__)


@data_bp.route("/upload", methods=["POST"])
def upload():
    """
    Upload a CSV file for a registered node.
    Deletes any previously uploaded file for this node before saving the new one,
    so stale files can never be accidentally re-analyzed.

    Form data:
        file    (file):  CSV file to upload.
        node_id (str):   Registered node ID.
    """
    node_id = request.form.get("node_id", "").strip()
    if not node_id:
        return jsonify({"success": False, "message": "node_id is required"}), 400

    if "file" not in request.files or request.files["file"].filename == "":
        return jsonify({"success": False, "message": "No file uploaded"}), 400

    f = request.files["file"]

    # Validate it's actually a CSV before saving
    if not f.filename.lower().endswith(".csv"):
        return jsonify({"success": False, "message": "Only CSV files are accepted"}), 400

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE node_id = ?", (node_id,)).fetchone()
    conn.close()

    if not user:
        return jsonify({"success": False, "message": "Node not found. Please log in first."}), 404

    # Delete any previously uploaded files for this node so stale data
    # can never be re-analyzed after a fresh upload
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    for old_file in os.listdir(UPLOAD_FOLDER):
        if old_file.startswith(node_id + "_"):
            os.remove(os.path.join(UPLOAD_FOLDER, old_file))

    filepath = os.path.join(UPLOAD_FOLDER, f"{node_id}_{f.filename}")
    f.save(filepath)

    # Immediately validate the CSV columns so the user gets feedback
    # right at upload time — not later when they call /analyze
    try:
        df = pd.read_csv(filepath)
        df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]
        cols = list(df.columns)

        amount_col = detect_amount_column(cols)
        time_col   = detect_time_column(cols)

        if amount_col is None or time_col is None:
            os.remove(filepath)
            missing = []
            if amount_col is None:
                missing.append("'amount'")
            if time_col is None:
                missing.append("'time'")

            return jsonify({
                "success": False,
                "message": f"CSV is missing required columns: {', '.join(missing)}. Your CSV needs columns named 'amount' and 'time'."
            }), 400

    except Exception as e:
        os.remove(filepath)
        return jsonify({"success": False, "message": f"Could not read CSV: {str(e)}"}), 400

    return jsonify({
        "success": True,
        "message": f"File uploaded and validated for {user['company']}. Call /analyze to process it.",
        "node_id": node_id,
        "company": user["company"],
        "rows":    len(df),
        "columns": cols,
    })


@data_bp.route("/analyze", methods=["POST"])
def analyze():
    """
    Analyze the most recently uploaded CSV for a node.
    Applies fraud detection rules and stores hashed results.
    Will not run if no valid uploaded file exists for the node.

    Body (JSON):
        node_id (str): Node to analyze.

    Returns per-node fraud summary.
    """
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

    # Find uploaded file for this node — must exist and be recent
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    uploaded = sorted([
        f for f in os.listdir(UPLOAD_FOLDER)
        if f.startswith(node_id + "_")
    ])

    if not uploaded:
        conn.close()
        return jsonify({
            "success": False,
            "message": "No uploaded file found for this node. Please upload a CSV first."
        }), 404

    filepath = os.path.join(UPLOAD_FOLDER, uploaded[-1])

    # ── Read CSV ────────────────────────────────────────────
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "message": f"Could not read CSV: {str(e)}"}), 500

    # Normalise column names
    df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]
    cols = list(df.columns)

    amount_col = detect_amount_column(cols)
    time_col   = detect_time_column(cols)

    # Double-check columns (upload already validated, but be safe)
    if amount_col is None:
        conn.close()
        return jsonify({
            "success": False,
            "message": f"CSV is missing an amount column. Found: {cols}. Rename your column to 'amount'."
        }), 400

    if time_col is None:
        conn.close()
        return jsonify({
            "success": False,
            "message": f"CSV is missing a time column. Found: {cols}. Rename your column to 'time'."
        }), 400

    # ── Apply fraud rules & store hashed transactions ───────
    # Always clear previous transactions before inserting new ones
    conn.execute("DELETE FROM transactions WHERE node_id = ?", (node_id,))

    total, n_fraud = len(df), 0
    for _, row in df.iterrows():
        amount   = row[amount_col]
        time     = row[time_col]
        fraud    = is_fraudulent(amount, time)
        n_fraud += int(fraud)

        conn.execute(
            "INSERT INTO transactions (company, node_id, amount_hash, is_fraud) VALUES (?, ?, ?, ?)",
            (company, node_id, sha256(amount), int(fraud)),
        )

    conn.commit()
    conn.close()

    fraud_rate = round(n_fraud / total * 100, 2) if total else 0
    return jsonify({
        "success":     True,
        "company":     company,
        "node_id":     node_id,
        "total":       total,
        "fraud_count": n_fraud,
        "safe_count":  total - n_fraud,
        "fraud_rate":  fraud_rate,
        "message":     f"Analysis complete for {company}",
    })


@data_bp.route("/clear_data", methods=["POST"])
def clear_data():
    """
    Delete all transaction data and uploaded files for a node.
    Used to clear stale data before a fresh analysis.

    Body (JSON):
        node_id (str): Node whose data should be cleared.
    """
    data    = request.get_json()
    node_id = data.get("node_id", "").strip()

    if not node_id:
        return jsonify({"success": False, "message": "node_id is required"}), 400

    # Delete uploaded files
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    for old_file in os.listdir(UPLOAD_FOLDER):
        if old_file.startswith(node_id + "_"):
            os.remove(os.path.join(UPLOAD_FOLDER, old_file))

    # Delete transactions from DB
    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE node_id = ?", (node_id,))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Data and uploaded files cleared successfully"})
