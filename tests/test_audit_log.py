import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.audit_log import AuditLog


NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def test_events_are_appended_as_jsonl_without_passwords(tmp_path):
    path = tmp_path / "logs" / "audit.jsonl"
    audit = AuditLog(path, clock=lambda: NOW)
    audit.record("INFO", "transaction_completed", "Перевод выполнен", client_id="ivan", transaction_id="tx-1",
                 details={"amount": Decimal("10.50"), "password": "secret-plaintext",
                          "nested": {"_password_hash": "secret-hash", "currency": "RUB"}})
    audit.record("ERROR", "transaction_error", "Insufficient funds", client_id="maria", transaction_id="tx-2",
                 details={"error_type": "InsufficientFundsError"}, timestamp=NOW + timedelta(seconds=1))
    content = path.read_text(encoding="utf-8")
    assert [json.loads(line) for line in content.splitlines()] == audit.records
    assert audit.records[0]["details"]["amount"] == "10.50"
    assert audit.records[0]["timestamp"] == NOW.isoformat()
    assert "secret-plaintext" not in content
    assert "secret-hash" not in content
    # A new logger appends without overwriting an existing file.
    AuditLog(path, clock=lambda: NOW).record("INFO", "demo_finished", "Done")
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3


def test_filter_combines_client_level_event_and_inclusive_time_bounds(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    for index, (client, level, event) in enumerate([
        ("ivan", "INFO", "transaction_completed"),
        ("ivan", "WARNING", "risk_analyzed"),
        ("maria", "WARNING", "risk_analyzed"),
        ("ivan", "ERROR", "transaction_error"),
    ]):
        audit.record(level, event, "Event", client_id=client, transaction_id=f"tx-{index}",
                     timestamp=NOW + timedelta(minutes=index))
    assert [entry["transaction_id"] for entry in audit.filter(client_id="ivan")] == ["tx-0", "tx-1", "tx-3"]
    assert [entry["transaction_id"] for entry in audit.filter(
        level="WARNING", client_id="ivan", event="risk_analyzed",
    )] == ["tx-1"]
    local = timezone(timedelta(hours=3))
    start = (NOW + timedelta(minutes=1)).astimezone(local)
    end = (NOW + timedelta(minutes=2)).astimezone(local)
    assert [entry["transaction_id"] for entry in audit.filter(date_from=start, date_to=end)] == ["tx-1", "tx-2"]
    assert audit.filter(client_id="missing") == []


def test_reports_separate_risk_decisions_from_execution_errors(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl", clock=lambda: NOW)
    for index, level in enumerate(("LOW", "MEDIUM", "HIGH")):
        audit.record("INFO" if level == "LOW" else "WARNING", "risk_analyzed", "Risk evaluated",
                     transaction_id=f"risk-{index}", details={"risk_level": level})
    audit.record("WARNING", "transaction_blocked", "Blocked", transaction_id="risk-2",
                 details={"risk_level": "HIGH", "error_type": "RiskBlockedError"})
    audit.record("WARNING", "transaction_deferred", "Night restriction",
                 details={"error_type": "BankOperationRestrictedError"})
    for error, count in [("InsufficientFundsError", 3), ("AccountFrozenError", 1), ("TemporaryTransactionError", 2)]:
        for _ in range(count):
            audit.record("ERROR", "transaction_error", error, details={"error_type": error})
    assert [entry["transaction_id"] for entry in audit.get_suspicious_operations()] == ["risk-1", "risk-2"]
    assert audit.get_error_statistics() == {
        "InsufficientFundsError": 3, "AccountFrozenError": 1, "TemporaryTransactionError": 2,
    }
