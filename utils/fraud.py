"""
utils/fraud.py
--------------
Local fraud detection rules applied per transaction.

Rules
-----
1. Amount > FRAUD_AMOUNT_THRESHOLD  → fraud
2. Transaction hour < FRAUD_HOUR_THRESHOLD (before 5 AM) → fraud

Both rules are independent — either one triggers a fraud flag.
"""

from config import FRAUD_AMOUNT_THRESHOLD, FRAUD_HOUR_THRESHOLD


def is_fraudulent(amount, time_str) -> bool:
    """
    Apply local fraud rules to a single transaction.

    Args:
        amount:   Transaction amount (numeric or string).
        time_str: Transaction time string. Accepted formats:
                  "HH:MM", "HH:MM:SS", or full datetime string.

    Returns:
        True if the transaction is fraudulent, False otherwise.

    Examples:
        >>> is_fraudulent(15000, "14:30")   # high amount
        True
        >>> is_fraudulent(500, "02:00")     # night transaction
        True
        >>> is_fraudulent(200, "10:00")     # normal
        False
    """
    fraud = False

    # Rule 1 — High amount
    try:
        if float(amount) > FRAUD_AMOUNT_THRESHOLD:
            fraud = True
    except (ValueError, TypeError):
        pass

    # Rule 2 — Night-time transaction (before FRAUD_HOUR_THRESHOLD AM)
    try:
        hour = int(str(time_str).split(":")[0].split(" ")[-1])
        if hour < FRAUD_HOUR_THRESHOLD:
            fraud = True
    except Exception:
        pass

    return fraud


def detect_amount_column(columns: list) -> str | None:
    """
    Find the amount column from a list of CSV column names.
    Checks known aliases in order of preference.

    Returns:
        Column name if found, None otherwise.
    """
    candidates = ["amount", "transaction_amount", "value", "amt"]
    for name in candidates:
        if name in columns:
            return name
    return None


def detect_time_column(columns: list) -> str | None:
    """
    Find the time column from a list of CSV column names.
    Checks known aliases in order of preference.

    Returns:
        Column name if found, None otherwise.
    """
    candidates = ["time", "transaction_time", "timestamp", "datetime", "hour"]
    for name in columns:
        if name in candidates:
            return name
    return None
