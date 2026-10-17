from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.models import Currency
from src.risk_analyzer import RiskAnalyzer
from src.transaction import ExternalRecipient, Transaction, TransactionType


NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def operation(transaction_type=TransactionType.WITHDRAWAL, **changes):
    values = dict(transaction_type=transaction_type, client_id="ivan", amount=Decimal("10"),
                  currency=Currency.RUB, sender_id="source")
    if transaction_type is TransactionType.TRANSFER:
        values["recipient_id"] = "recipient"
    values.update(changes)
    return Transaction(**values)


@pytest.mark.parametrize("amount,score,level", [("99999.99", 0, "LOW"), ("100000", 2, "MEDIUM")])
def test_large_amount_threshold_in_rub(amount, score, level):
    analyzer = RiskAnalyzer()
    result = analyzer.analyze(operation(amount=Decimal(amount)), NOW, Decimal(amount))
    assert result == {"score": score, "level": level, "reasons": ["large_amount"] if score else []}


@pytest.mark.parametrize("now,night", [
    (datetime(2026, 10, 15, 20, 59, 59, tzinfo=timezone.utc), False),
    (datetime(2026, 10, 15, 21, 0, tzinfo=timezone.utc), True),
    (datetime(2026, 10, 16, 1, 59, 59, tzinfo=timezone.utc), True),
    (datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc), False),
])
def test_night_rule_uses_bank_timezone_and_window_boundaries(now, night):
    result = RiskAnalyzer().analyze(operation(), now, Decimal("10"))
    assert result["reasons"] == (["night_operation"] if night else [])
    assert result["score"] == (1 if night else 0)


def test_recipient_becomes_known_only_after_success_and_for_that_client():
    analyzer = RiskAnalyzer()
    first = operation(TransactionType.TRANSFER)
    assert analyzer.analyze(first, NOW, Decimal("10"))["reasons"] == ["new_recipient"]
    assert analyzer.analyze(operation(TransactionType.TRANSFER), NOW, Decimal("10"))["reasons"] == ["new_recipient"]
    analyzer.remember_success(first)
    assert analyzer.analyze(operation(TransactionType.TRANSFER), NOW, Decimal("10"))["level"] == "LOW"
    other = operation(TransactionType.TRANSFER, client_id="maria")
    assert analyzer.analyze(other, NOW, Decimal("10"))["reasons"] == ["new_recipient"]


def test_external_recipient_identity_includes_bank_and_account():
    analyzer = RiskAnalyzer()
    def external(bank, account):
        return operation(TransactionType.TRANSFER, recipient_id=None, is_external=True,
                         external_recipient=ExternalRecipient(bank, account, Currency.USD))
    first = external("BANK-A", "ACCOUNT-1")
    assert analyzer.analyze(first, NOW, Decimal("10"))["reasons"] == ["new_recipient"]
    analyzer.remember_success(first)
    assert analyzer.analyze(external("BANK-A", "ACCOUNT-1"), NOW, Decimal("10"))["level"] == "LOW"
    assert analyzer.analyze(external("BANK-B", "ACCOUNT-1"), NOW, Decimal("10"))["reasons"] == ["new_recipient"]
    assert analyzer.analyze(external("BANK-A", "ACCOUNT-2"), NOW, Decimal("10"))["reasons"] == ["new_recipient"]


def test_frequency_counts_unique_ids_and_expires_without_recounting_retry():
    analyzer = RiskAnalyzer()
    first_five = [operation() for _ in range(5)]
    for transaction in first_five:
        assert analyzer.analyze(transaction, NOW, Decimal("10"))["level"] == "LOW"
    for _ in range(5):
        assert analyzer.analyze(first_five[0], NOW + timedelta(seconds=30), Decimal("10"))["level"] == "LOW"
    sixth = operation(TransactionType.TRANSFER)
    assert analyzer.analyze(sixth, NOW + timedelta(seconds=59), Decimal("10")) == {
        "score": 3, "level": "HIGH", "reasons": ["frequent_operations", "new_recipient"],
    }
    # Exactly one minute later the original five have left the window.
    assert analyzer.analyze(first_five[0], NOW + timedelta(minutes=1), Decimal("10"))["level"] == "LOW"
    assert analyzer.analyze(operation(client_id="maria"), NOW, Decimal("10"))["level"] == "LOW"
    assert analyzer.get_client_risk_profile("ivan")["checked_transactions"] == 6


def test_profile_counts_unique_suspicious_and_blocked_operations_across_rechecks():
    analyzer = RiskAnalyzer()
    large = operation(TransactionType.TRANSFER, amount=Decimal("100000"))
    for _ in range(2):
        assert analyzer.analyze(large, NOW, Decimal("100000"))["level"] == "HIGH"
    small = operation(TransactionType.TRANSFER)
    analyzer.analyze(small, NOW, Decimal("10"))
    analyzer.remember_success(small)
    assert analyzer.analyze(large, NOW + timedelta(minutes=1), Decimal("100000"))["level"] == "MEDIUM"
    assert analyzer.get_client_risk_profile("ivan") == {
        "client_id": "ivan", "checked_transactions": 2, "suspicious_transactions": 2,
        "blocked_transactions": 1, "last_risk_level": "MEDIUM",
        "common_reasons": {"new_recipient": 2, "large_amount": 1},
    }
    assert analyzer.get_client_risk_profile("unknown")["checked_transactions"] == 0
    assert analyzer.get_client_risk_profile("unknown")["last_risk_level"] is None
