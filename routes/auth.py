"""
routes/auth.py
--------------
Authentication routes: register, login, reset_key.

Endpoints
---------
POST /register   — create a new node account
POST /login      — authenticate an existing node
POST /reset_key  — reset key using company name as proof of identity
"""

import csv
import os

from flask import Blueprint, request, jsonify

from database.schema import get_db
from utils.crypto import sha256

auth_bp = Blueprint("auth", __name__)

CREDENTIALS_FILE = "node_credentials.csv"


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Register a new node.

    Body (JSON):
        node_id  (str): Unique identifier for the node.
        key      (str): Plaintext key — stored as SHA-256 hash only.
        company  (str): Display name for this node/bank.

    Returns 409 if node_id already exists.
    Returns 403 if the same IP has already registered a node.
    """
    data    = request.get_json()
    node_id = data.get("node_id", "").strip()
    key     = data.get("key", "").strip()
    company = data.get("company", "").strip()

    if not node_id or not key or not company:
        return jsonify({"success": False, "message": "node_id, key, and company are all required"}), 400

    key_hash  = sha256(key)
    client_ip = request.remote_addr

    conn = get_db()
    c    = conn.cursor()

    # Block duplicate node_id
    if c.execute("SELECT 1 FROM users WHERE node_id = ?", (node_id,)).fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Node ID already exists. Please choose a different one."}), 409

    # Block same IP registering multiple nodes (enforces genuine collaboration)
    existing_ip = c.execute("SELECT node_id FROM users WHERE ip = ?", (client_ip,)).fetchone()
    if existing_ip:
        conn.close()
        return jsonify({
            "success": False,
            "message": f"A node ({existing_ip['node_id']}) already exists from this device. Only one node per device is allowed."
        }), 403

    c.execute(
        "INSERT INTO users (node_id, key_hash, company, ip) VALUES (?, ?, ?, ?)",
        (node_id, key_hash, company, client_ip),
    )
    conn.commit()
    conn.close()

    # Persist plain-text credentials to CSV for admin reference
    _append_credentials_csv(node_id, company, key)

    return jsonify({"success": True, "message": "Registration complete. You can now log in."})


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate an existing node.

    Body (JSON):
        node_id (str): Node identifier.
        key     (str): Plaintext key to verify.

    Returns 404 if node not found, 401 if key is wrong.
    """
    data    = request.get_json()
    node_id = data.get("node_id", "").strip()
    key     = data.get("key", "").strip()

    if not node_id or not key:
        return jsonify({"success": False, "message": "node_id and key are required"}), 400

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE node_id = ?", (node_id,)).fetchone()
    conn.close()

    if not user:
        return jsonify({"success": False, "message": "Node ID not found. Please register first."}), 404

    if user["key_hash"] != sha256(key):
        return jsonify({"success": False, "message": "Incorrect secure key."}), 401

    return jsonify({
        "success": True,
        "message": f"Welcome back, {user['company']}!",
        "node_id": node_id,
        "company": user["company"],
    })


@auth_bp.route("/reset_key", methods=["POST"])
def reset_key():
    """
    Reset a node's key using company name as proof of identity.
    The original key is never recoverable (stored as SHA-256 hash only).

    Body (JSON):
        node_id (str): Node to reset.
        company (str): Must match the registered company name exactly.
        new_key (str): Replacement key.
    """
    data    = request.get_json()
    node_id = data.get("node_id", "").strip()
    company = data.get("company", "").strip()
    new_key = data.get("new_key", "").strip()

    if not node_id or not company or not new_key:
        return jsonify({"success": False, "message": "node_id, company, and new_key are all required"}), 400

    if len(new_key) < 4:
        return jsonify({"success": False, "message": "New key must be at least 4 characters"}), 400

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE node_id = ?", (node_id,)).fetchone()

    if not user:
        conn.close()
        return jsonify({"success": False, "message": "Node ID not found"}), 404

    if user["company"].strip().lower() != company.strip().lower():
        conn.close()
        return jsonify({"success": False, "message": "Company name does not match our records"}), 401

    conn.execute("UPDATE users SET key_hash = ? WHERE node_id = ?", (sha256(new_key), node_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Key reset successfully. You can now log in with your new key."})


# ── Private helpers ─────────────────────────────────────────

def _append_credentials_csv(node_id: str, company: str, key: str) -> None:
    """Append plaintext credentials to CSV for admin reference."""
    file_exists = os.path.isfile(CREDENTIALS_FILE)
    with open(CREDENTIALS_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Node ID", "Company Name", "Secure Key"])
        writer.writerow([node_id, company, key])
