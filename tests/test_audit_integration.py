import json
from copy import copy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.audit_log import AuditLog
from src.bank import Bank
from src.client import Client, ClientStatus
from src.exceptions import AccountFrozenError, BankOperationRestrictedError, InsufficientFundsError, RiskBlockedError
from src.models import BankAccount, Currency
from src.risk_analyzer import RiskAnalyzer
from src.transaction import ExternalRecipient, Transaction, TransactionStatus, TransactionType
from src.transaction_processor import ExternalTransferAdapter, TransactionProcessor
from src.transaction_queue import TransactionQueue


NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


@pytest.fixture
def system(tmp_path):
    time = {"now": NOW}
    clock = lambda: time["now"]
    audit = AuditLog(tmp_path / "audit.jsonl", clock=clock)
    risk = RiskAnalyzer()
    bank = Bank("Day 5 Bank", clock=clock, audit_log=audit, risk_analyzer=risk)
    client = Client("Ivan", date(1990, 1, 1), {"email": "ivan@example.com"}, "private-password")
    other = Client("Maria", date(1990, 1, 1), {"email": "maria@example.com"}, "another-password")
    bank.add_client(client)
    bank.add_client(other)
    sender = BankAccount(client.full_name)
    recipient = BankAccount(other.full_name)
    sender.deposit(Decimal("1000000"))
    bank.open_account(client.client_id, sender)
    bank.open_account(other.client_id, recipient)
    queue = TransactionQueue()
    processor = TransactionProcessor(bank, queue)
    return dict(bank=bank, audit=audit, risk=risk, client=client, other=other, sender=sender,
                recipient=recipient, queue=queue, processor=processor, time=time)


def enqueue(system, amount="10", **changes):
    operation = changes.get("transaction_type", TransactionType.TRANSFER)
    values = dict(transaction_type=operation, client_id=system["client"].client_id,
                  amount=Decimal(amount), currency=Currency.RUB,
                  sender_id=system["sender"].uuid, recipient_id=system["recipient"].uuid)
    if operation is TransactionType.DEPOSIT:
        values.update(sender_id=None, recipient_id=system["sender"].uuid)
    elif operation is TransactionType.WITHDRAWAL:
        values["recipient_id"] = None
    values.update(changes)
    if values.get("is_external"):
        values["recipient_id"] = None
        values.setdefault("external_recipient", ExternalRecipient("OTHER-BANK", "EXT-1", Currency.RUB))
    transaction = Transaction(**values)
    system["queue"].add(transaction)
    return transaction


def test_success_introduces_recipient_and_reports_medium_and_low_risk(system):
    first = enqueue(system)
    system["processor"].process_all()
    familiar = enqueue(system, "20")
    system["processor"].process_all()
    large = enqueue(system, "100000")
    system["processor"].process_all()
    assert all(item.status is TransactionStatus.COMPLETED for item in (first, familiar, large))
    assert system["sender"]._balance == Decimal("899970")
    assert system["recipient"]._balance == Decimal("100030")
    analyses = system["audit"].filter(event="risk_analyzed")
    assert [item["details"]["risk_level"] for item in analyses] == ["MEDIUM", "LOW", "MEDIUM"]
    assert [item["transaction_id"] for item in system["audit"].get_suspicious_operations()] == [first.id, large.id]
    assert len(system["audit"].filter(event="transaction_completed")) == 3
    assert system["audit"].get_error_statistics() == {}
    profile = system["risk"].get_client_risk_profile(system["client"].client_id)
    assert (profile["checked_transactions"], profile["suspicious_transactions"], profile["blocked_transactions"]) == (3, 2, 0)
    assert profile["common_reasons"] == {"new_recipient": 1, "large_amount": 1}
    text = system["audit"].file_path.read_text(encoding="utf-8")
    assert [json.loads(line) for line in text.splitlines()] == system["audit"].records
    assert "private-password" not in text and "another-password" not in text
    assert "_password_hash" not in text and "_password_salt" not in text


@pytest.mark.parametrize("external", [False, True])
def test_high_risk_blocks_before_any_debit_or_external_send_without_banning_client(system, external):
    transaction = enqueue(system, "100000", is_external=external)
    adapter = system["processor"].external_adapter
    with patch.object(adapter, "send", wraps=adapter.send) as send:
        system["processor"].process_all()
        assert send.call_count == 0
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.errors[-1]["error_type"] == "RiskBlockedError"
    assert system["sender"]._balance == Decimal("1000000")
    assert system["recipient"]._balance == 0
    assert adapter.get_receipt(transaction.id) is None
    blocked = system["audit"].filter(event="transaction_blocked")
    assert len(blocked) == 1 and blocked[0]["level"] == "WARNING"
    assert blocked[0]["details"]["reasons"] == ["large_amount", "new_recipient"]
    assert system["audit"].get_error_statistics() == {}
    assert system["client"].status is ClientStatus.ACTIVE
    small = enqueue(system, "10", is_external=external)
    system["processor"].process_all()
    assert small.status is TransactionStatus.COMPLETED


@pytest.mark.parametrize("amount,expected", [("1111.11", TransactionStatus.COMPLETED), ("1111.12", TransactionStatus.FAILED)])
def test_large_amount_uses_currency_equivalent_in_rub(system, amount, expected):
    bank, client = system["bank"], system["client"]
    usd = BankAccount(client.full_name, Currency.USD)
    bank.open_account(client.client_id, usd)
    bank.deposit(client.client_id, usd.uuid, Decimal("2000"))
    transaction = enqueue(system, amount, sender_id=usd.uuid, currency=Currency.USD)
    system["processor"].process_all()
    assert transaction.status is expected
    risk = system["audit"].filter(event="risk_analyzed")[0]["details"]
    assert ("large_amount" in risk["reasons"]) is (expected is TransactionStatus.FAILED)
    assert Decimal(risk["amount_in_rub"]) == Decimal(amount) * Decimal("90")
    if expected is TransactionStatus.FAILED:
        assert usd._balance == Decimal("2000")
        assert system["recipient"]._balance == 0
    else:
        assert usd._balance == Decimal("888.89")
        assert system["recipient"]._balance == Decimal("99999.90")


def test_sixth_new_operation_is_blocked_and_frequency_window_expires(system):
    first_five = [enqueue(system, "1", transaction_type=TransactionType.WITHDRAWAL) for _ in range(5)]
    sixth = enqueue(system)
    system["processor"].process_all()
    assert all(item.status is TransactionStatus.COMPLETED for item in first_five)
    assert sixth.status is TransactionStatus.FAILED
    assert system["sender"]._balance == Decimal("999995")
    assert system["recipient"]._balance == 0
    assert system["audit"].filter(event="transaction_blocked")[0]["details"]["reasons"] == [
        "frequent_operations", "new_recipient",
    ]
    system["time"]["now"] += timedelta(minutes=1)
    later = enqueue(system)
    system["processor"].process_all()
    assert later.status is TransactionStatus.COMPLETED
    assert system["sender"]._balance == Decimal("999985")


def test_retries_are_logged_per_attempt_but_do_not_inflate_risk_profile_or_duplicate_success(system):
    processor = system["processor"]
    adapter = ExternalTransferAdapter(failures_remaining=2)
    processor.external_adapter = adapter
    transaction = enqueue(system, is_external=True)
    for minute in range(3):
        system["time"]["now"] = NOW + timedelta(minutes=minute)
        processor.process_all()
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.attempts == 3
    assert system["sender"]._balance == Decimal("999989.90")
    assert adapter.get_receipt(transaction.id)["amount"] == Decimal("10")
    assert system["audit"].get_error_statistics() == {"TemporaryTransactionError": 2}
    assert len(system["audit"].get_suspicious_operations()) == 3
    profile = system["risk"].get_client_risk_profile(system["client"].client_id)
    assert profile["checked_transactions"] == profile["suspicious_transactions"] == 1
    assert profile["common_reasons"] == {"new_recipient": 1}
    known = enqueue(system, is_external=True)
    processor.process_all()
    assert known.status is TransactionStatus.COMPLETED
    assert system["audit"].filter(event="risk_analyzed")[-1]["details"]["risk_level"] == "LOW"
    records_before = len(system["audit"].records)
    replay = copy(transaction)
    replay.status = TransactionStatus.PENDING
    replay_queue = TransactionQueue()
    replay_queue.add(replay)
    TransactionProcessor(system["bank"], replay_queue, adapter).process_all()
    assert replay.status is TransactionStatus.COMPLETED
    assert len(system["audit"].records) == records_before
    assert len(system["audit"].filter(event="transaction_completed")) == 2
    assert system["sender"]._balance == Decimal("999979.80")


def test_night_risk_is_recorded_before_deferral_and_high_risk_blocks_before_window_check(system):
    night = datetime(2026, 10, 15, 23, tzinfo=timezone.utc)
    morning = datetime(2026, 10, 16, 2, tzinfo=timezone.utc)
    system["time"]["now"] = night
    small = enqueue(system, transaction_type=TransactionType.WITHDRAWAL)
    dangerous = enqueue(system, "100000", transaction_type=TransactionType.WITHDRAWAL)
    system["processor"].process_all()
    assert small.status is TransactionStatus.RETRY_WAIT
    assert small.retry_at == morning and small.attempts == 0
    assert dangerous.status is TransactionStatus.FAILED
    assert dangerous.errors[-1]["error_type"] == "RiskBlockedError"
    assert system["sender"]._balance == Decimal("1000000")
    analyses = system["audit"].filter(event="risk_analyzed")
    assert [entry["details"]["reasons"] for entry in analyses] == [["night_operation"], ["large_amount", "night_operation"]]
    assert system["audit"].get_error_statistics() == {}
    assert len(system["audit"].filter(event="transaction_deferred")) == 1
    system["time"]["now"] = morning
    system["processor"].process_all()
    assert small.status is TransactionStatus.COMPLETED
    assert system["sender"]._balance == Decimal("999990")
    profile = system["risk"].get_client_risk_profile(system["client"].client_id)
    assert (profile["checked_transactions"], profile["suspicious_transactions"], profile["blocked_transactions"]) == (2, 2, 1)
    assert profile["last_risk_level"] == "LOW"


def test_execution_errors_are_logged_once_without_becoming_risk_by_themselves(system):
    bank, client = system["bank"], system["client"]
    empty = BankAccount(client.full_name)
    bank.open_account(client.client_id, empty)
    insufficient = enqueue(system, sender_id=empty.uuid, transaction_type=TransactionType.WITHDRAWAL)
    system["processor"].process_all()
    bank.freeze_account(system["sender"].uuid)
    frozen = enqueue(system)
    system["processor"].process_all()
    assert insufficient.status is frozen.status is TransactionStatus.FAILED
    assert empty._balance == 0 and system["sender"]._balance == Decimal("1000000")
    assert system["audit"].get_error_statistics() == {"InsufficientFundsError": 1, "AccountFrozenError": 1}
    assert system["audit"].get_suspicious_operations() == []
    assert system["risk"].get_client_risk_profile(client.client_id)["suspicious_transactions"] == 0


def test_failed_transfer_does_not_make_recipient_known(system):
    bank, client = system["bank"], system["client"]
    empty = BankAccount(client.full_name)
    bank.open_account(client.client_id, empty)
    failed = enqueue(system, sender_id=empty.uuid)
    system["processor"].process_all()
    bank.deposit(client.client_id, empty.uuid, Decimal("20"))
    successful = enqueue(system, sender_id=empty.uuid)
    system["processor"].process_all()
    familiar = enqueue(system, sender_id=empty.uuid)
    system["processor"].process_all()
    assert failed.status is TransactionStatus.FAILED
    assert successful.status is familiar.status is TransactionStatus.COMPLETED
    assert [entry["details"]["risk_level"] for entry in system["audit"].filter(event="risk_analyzed")] == [
        "MEDIUM", "MEDIUM", "LOW",
    ]
    assert empty._balance == 0 and system["recipient"]._balance == Decimal("20")


def test_large_deposit_is_audited_without_spending_risk_rules(system):
    transaction = enqueue(system, "2000000", transaction_type=TransactionType.DEPOSIT)
    system["processor"].process_all()
    assert transaction.status is TransactionStatus.COMPLETED
    assert system["sender"]._balance == Decimal("3000000")
    assert len(system["audit"].filter(event="transaction_completed")) == 1
    assert system["audit"].get_suspicious_operations() == []
    assert system["risk"].get_client_risk_profile(system["client"].client_id)["checked_transactions"] == 0


def test_audit_write_failure_after_commit_does_not_rollback_or_repeat_payment(system):
    audit = system["audit"]
    original = audit.record
    def unavailable_success_record(level, event, *args, **kwargs):
        if event == "transaction_completed":
            raise OSError("Audit file temporarily unavailable")
        return original(level, event, *args, **kwargs)
    transaction = enqueue(system)
    with patch.object(audit, "record", side_effect=unavailable_success_record):
        system["processor"].process_all()
    assert transaction.status is TransactionStatus.COMPLETED
    assert system["sender"]._balance == Decimal("999990")
    assert system["recipient"]._balance == Decimal("10")
    assert audit.get_error_statistics() == {"OSError": 1}
    assert system["processor"].process_all() == []
    familiar = enqueue(system)
    system["processor"].process_all()
    assert familiar.status is TransactionStatus.COMPLETED
    assert audit.filter(event="risk_analyzed")[-1]["details"]["risk_level"] == "LOW"


def test_direct_withdraw_cannot_bypass_risk_block_after_queued_withdrawals(system):
    bank, client, sender = system["bank"], system["client"], system["sender"]
    for _ in range(5):
        enqueue(system, "1", transaction_type=TransactionType.WITHDRAWAL)
    queued = enqueue(system, "100000", transaction_type=TransactionType.WITHDRAWAL)
    system["processor"].process_all()
    assert queued.status is TransactionStatus.FAILED
    assert queued.errors[-1]["error_type"] == "RiskBlockedError"
    with pytest.raises(RiskBlockedError, match="large_amount, frequent_operations"):
        bank.withdraw(client.client_id, sender.uuid, Decimal("100000"))
    assert sender._balance == Decimal("999995")
    blocks = system["audit"].filter(event="transaction_blocked")
    assert len(blocks) == 2
    assert all(entry["details"]["reasons"] == ["large_amount", "frequent_operations"] for entry in blocks)
    profile = system["risk"].get_client_risk_profile(client.client_id)
    assert profile["checked_transactions"] == 7 and profile["blocked_transactions"] == 2
    assert system["audit"].get_error_statistics() == {}


def test_direct_withdrawals_contribute_to_frequency_of_queued_operations(system):
    bank, client, sender = system["bank"], system["client"], system["sender"]
    for _ in range(5):
        bank.withdraw(client.client_id, sender.uuid, Decimal("1"))
    queued = enqueue(system, "100000", transaction_type=TransactionType.WITHDRAWAL)
    system["processor"].process_all()
    assert queued.status is TransactionStatus.FAILED
    assert queued.errors[-1]["error_type"] == "RiskBlockedError"
    assert sender._balance == Decimal("999995")
    assert len(system["audit"].filter(event="transaction_completed")) == 5
    assert system["risk"].get_client_risk_profile(client.client_id)["checked_transactions"] == 6


def test_public_deposit_and_withdraw_are_audited_and_execute_once(system):
    bank, client, sender, audit = system["bank"], system["client"], system["sender"], system["audit"]
    assert bank.deposit(client.client_id, sender.uuid, Decimal("1000000")) is None
    assert system["risk"].get_client_risk_profile(client.client_id)["checked_transactions"] == 0
    assert bank.withdraw(client.client_id, sender.uuid, Decimal("10")) is None
    assert sender._balance == Decimal("1999990")
    events = audit.filter(event="transaction_completed")
    assert [entry["details"]["transaction_type"] for entry in events] == ["deposit", "withdrawal"]
    assert [entry["details"]["amount"] for entry in events] == ["1000000", "10"]
    assert len({entry["transaction_id"] for entry in events}) == 2
    assert all(entry["timestamp"] == NOW.isoformat() for entry in events)
    assert system["risk"].get_client_risk_profile(client.client_id)["checked_transactions"] == 1
    assert [json.loads(line) for line in audit.file_path.read_text(encoding="utf-8").splitlines()] == audit.records


def test_public_money_errors_are_audited_once_and_keep_original_exceptions(system):
    bank, client, sender = system["bank"], system["client"], system["sender"]
    empty = BankAccount(client.full_name)
    bank.open_account(client.client_id, empty)
    with pytest.raises(InsufficientFundsError):
        bank.withdraw(client.client_id, empty.uuid, Decimal("10"))
    bank.freeze_account(sender.uuid)
    with pytest.raises(AccountFrozenError):
        bank.deposit(client.client_id, sender.uuid, Decimal("10"))
    assert sender._balance == Decimal("1000000") and empty._balance == 0
    assert system["audit"].get_error_statistics() == {"InsufficientFundsError": 1, "AccountFrozenError": 1}
    assert system["audit"].get_suspicious_operations() == []


def test_public_withdraw_checks_night_risk_before_working_window(system):
    bank, client, sender = system["bank"], system["client"], system["sender"]
    system["time"]["now"] = datetime(2026, 10, 15, 23, tzinfo=timezone.utc)
    with pytest.raises(RiskBlockedError, match="large_amount, night_operation"):
        bank.withdraw(client.client_id, sender.uuid, Decimal("100000"))
    with pytest.raises(BankOperationRestrictedError):
        bank.withdraw(client.client_id, sender.uuid, Decimal("1"))
    assert sender._balance == Decimal("1000000")
    assert len(system["audit"].filter(event="transaction_blocked")) == 1
    assert len(system["audit"].filter(event="transaction_deferred")) == 1
    assert system["audit"].get_error_statistics() == {}


def test_public_withdraw_does_not_report_failure_after_committed_debit(system):
    bank, client, sender, audit = system["bank"], system["client"], system["sender"], system["audit"]
    original = audit.record
    def unavailable_success_record(level, event, *args, **kwargs):
        if event == "transaction_completed":
            raise OSError("Audit file temporarily unavailable")
        return original(level, event, *args, **kwargs)
    with patch.object(audit, "record", side_effect=unavailable_success_record):
        assert bank.withdraw(client.client_id, sender.uuid, Decimal("10")) is None
    assert sender._balance == Decimal("999990")
    assert audit.get_error_statistics() == {"OSError": 1}
    assert len(bank.transaction_errors) == 1
    assert bank.get_transaction_result(bank.transaction_errors[0]["transaction_id"]) is not None
    assert system["risk"].get_client_risk_profile(client.client_id)["checked_transactions"] == 1
