"""
tests/test_fraud.py
-------------------
Unit tests for fraud detection rules.
Run with: pytest tests/
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from utils.fraud import is_fraudulent, detect_amount_column, detect_time_column


class TestIsFraudulent:

    def test_normal_transaction_is_safe(self):
        assert is_fraudulent(500, "14:30") is False

    def test_high_amount_is_fraud(self):
        assert is_fraudulent(15000, "14:30") is True

    def test_boundary_amount_is_safe(self):
        # Exactly at threshold is NOT fraud (rule is strictly >)
        assert is_fraudulent(10000, "14:30") is False

    def test_above_boundary_is_fraud(self):
        assert is_fraudulent(10001, "14:30") is True

    def test_night_transaction_is_fraud(self):
        assert is_fraudulent(200, "02:00") is True

    def test_boundary_hour_is_fraud(self):
        # Hour 4 (04:00) is before 5 AM — fraud
        assert is_fraudulent(200, "04:59") is True

    def test_exactly_5am_is_safe(self):
        assert is_fraudulent(200, "05:00") is False

    def test_both_rules_triggered(self):
        assert is_fraudulent(50000, "01:30") is True

    def test_invalid_amount_defaults_to_zero(self):
        # Invalid amount treated as 0 — not fraud by amount rule
        assert is_fraudulent("abc", "14:00") is False

    def test_invalid_time_ignores_time_rule(self):
        # Invalid time means time rule is skipped
        assert is_fraudulent(500, "not-a-time") is False

    def test_invalid_time_high_amount_still_fraud(self):
        assert is_fraudulent(20000, "not-a-time") is True

    def test_string_amount_parsed_correctly(self):
        assert is_fraudulent("15000", "14:00") is True

    def test_full_datetime_string_for_time(self):
        # "2024-01-01 03:00:00" → hour 3 → fraud
        assert is_fraudulent(500, "2024-01-01 03:00:00") is True


class TestDetectAmountColumn:

    def test_finds_amount(self):
        assert detect_amount_column(["amount", "time"]) == "amount"

    def test_finds_transaction_amount(self):
        assert detect_amount_column(["transaction_amount", "time"]) == "transaction_amount"

    def test_finds_value(self):
        assert detect_amount_column(["value", "hour"]) == "value"

    def test_finds_amt(self):
        assert detect_amount_column(["id", "amt", "ts"]) == "amt"

    def test_returns_none_when_not_found(self):
        assert detect_amount_column(["customer_id", "category"]) is None

    def test_prefers_amount_over_value(self):
        assert detect_amount_column(["value", "amount"]) == "amount"


class TestDetectTimeColumn:

    def test_finds_time(self):
        assert detect_time_column(["amount", "time"]) == "time"

    def test_finds_timestamp(self):
        assert detect_time_column(["amount", "timestamp"]) == "timestamp"

    def test_finds_hour(self):
        assert detect_time_column(["amount", "hour"]) == "hour"

    def test_returns_none_when_not_found(self):
        assert detect_time_column(["amount", "category"]) is None
