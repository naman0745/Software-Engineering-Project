"""
config.py
---------
Central configuration for TrustGrid.
All environment-specific settings live here.
Never hardcode these values in route files.
"""

import os

# ── Paths ──────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_PATH       = os.path.join(BASE_DIR, "trustgrid.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

# ── Fraud Detection Rules ───────────────────────────────────
FRAUD_AMOUNT_THRESHOLD = 10_000   # transactions above this are flagged
FRAUD_HOUR_THRESHOLD   = 5        # transactions before 5 AM are flagged
FRAUD_RATE_THRESHOLD   = 5.0      # global fraud rate (%) above which → FRAUD DETECTED

# ── Collaboration Rules ─────────────────────────────────────
MIN_NODES_FOR_ANALYSIS = 2        # minimum nodes needed for global analysis
DATA_WINDOW_HOURS      = 24       # only consider data from the last N hours

# ── Ollama / LLM ────────────────────────────────────────────
OLLAMA_MODEL      = "gemma4:e4b"
OLLAMA_MAX_TOKENS = 150
OLLAMA_TEMPERATURE = 0.3

# ── Flask ────────────────────────────────────────────────────
DEBUG = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
PORT  = int(os.environ.get("PORT", 5000))
