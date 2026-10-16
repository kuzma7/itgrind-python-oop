from copy import copy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.bank import Bank
from src.client import Client, ClientStatus
from src.exceptions import InvalidOperationError, TemporaryTransactionError
from src.investment_account import InvestmentAccount
from src.models import AccountStatus, BankAccount, Currency
from src.premium_account import PremiumAccount
from src.savings_account import SavingsAccount
from src.transaction import ExternalRecipient, Transaction, TransactionStatus, TransactionType
from src.transaction_processor import ExternalTransferAdapter, TransactionProcessor
from src.transaction_queue import TransactionQueue

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


@pytest.fixture
def system():
    bank = Bank("Day 4 Bank", clock=lambda: NOW)
    ivan = Client("Ivan", date(1990, 1, 1), {"email": "ivan@example.com"}, "secret")
    maria = Client("Maria", date(1990, 1, 1), {"email": "maria@example.com"}, "secret")
    bank.add_client(ivan)
    bank.add_client(maria)
    sender = BankAccount(ivan.full_name)
    recipient = BankAccount(maria.full_name)
    queue = TransactionQueue()
    bank.open_account(ivan.client_id, sender)
    bank.open_account(maria.client_id, recipient)
    return bank, ivan, maria, sender, recipient, queue, TransactionProcessor(bank, queue)


def transfer(system, **changes):
    _, ivan, _, sender, recipient, _, _ = system
    values = dict(
        transaction_type=TransactionType.TRANSFER,
        client_id=ivan.client_id,
        amount=Decimal("100"),
        currency=Currency.RUB,
        sender_id=sender.uuid,
        recipient_id=recipient.uuid,
    )
    values.update(changes)
    if values.get("is_external"):
        values["recipient_id"] = None
        values.setdefault("external_recipient", ExternalRecipient("OTHER-BANK", "EXT-1", Currency.RUB))
    return Transaction(**values)


def test_ten_transactions_complete_with_expected_balances(system):
    bank, ivan, maria, sender, recipient, queue, processor = system
    usd = BankAccount(maria.full_name, Currency.USD)
    premium = PremiumAccount(ivan.full_name)
    savings = SavingsAccount(ivan.full_name, min_balance=Decimal("100"))
    frozen = BankAccount(ivan.full_name)
    for account, client in [(usd, maria), (premium, ivan), (savings, ivan), (frozen, ivan)]:
        bank.open_account(client.client_id, account)
    bank.deposit(ivan.client_id, savings.uuid, Decimal("200"))
    bank.freeze_account(frozen.uuid)
    transactions = [
        transfer(system, transaction_type=TransactionType.DEPOSIT, sender_id=None,
                 recipient_id=sender.uuid, amount=Decimal("1000"), priority=5),
        transfer(system, transaction_type=TransactionType.WITHDRAWAL, recipient_id=None, priority=4),
        transfer(system, amount=Decimal("200"), priority=3),
        transfer(system, is_external=True, priority=2),
        transfer(system, recipient_id=usd.uuid, amount=Decimal("90"), priority=1),
        transfer(system, sender_id=premium.uuid, is_external=True),
        transfer(system, sender_id=savings.uuid, amount=Decimal("101")),
        transfer(system, transaction_type=TransactionType.DEPOSIT, sender_id=None, recipient_id=frozen.uuid),
        transfer(system, transaction_type=TransactionType.WITHDRAWAL, recipient_id=None, amount=Decimal("10000")),
        transfer(system, amount=Decimal("50"), priority=100, scheduled_at=NOW + timedelta(hours=1)),
    ]
    for transaction in transactions:
        queue.add(transaction)
    assert len(processor.process_all(NOW)) == 9
    assert [item.status for item in transactions] == (
            [TransactionStatus.COMPLETED] * 6 + [TransactionStatus.FAILED] * 3 + [TransactionStatus.PENDING]
    )
    assert sender._balance == Decimal("509")
    assert recipient._balance == Decimal("200")
    assert usd._balance == Decimal("1")
    assert premium._balance == Decimal("-201")
    assert savings._balance == Decimal("200")
    assert frozen._balance == 0
    assert [item.fee for item in transactions[:6]] == [
        Decimal("0"), Decimal("0"), Decimal("0"), Decimal("1"), Decimal("0"), Decimal("101"),
    ]
    assert [item.errors[-1]["error_type"] for item in transactions[6:9]] == [
        "InsufficientFundsError", "AccountFrozenError", "InsufficientFundsError",
    ]
    assert transactions[6].failure_reason == "Withdrawal would violate minimum balance"
    assert transactions[8].failure_reason == "Insufficient funds"
    for transaction in (transactions[3], transactions[5]):
        assert processor.external_adapter.get_receipt(transaction.id)["amount"] == Decimal("100")
    assert len(processor.errors) == 3
    assert processor.process_all(NOW + timedelta(hours=1)) == [transactions[-1]]
    assert sender._balance == Decimal("459")
    assert recipient._balance == Decimal("250")
    assert len(queue) == 0
    assert processor.process_all(NOW + timedelta(days=1)) == []


def test_currency_conversion_and_fee_rounding(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    external = ExternalRecipient("FOREIGN-BANK", "USD-ACCOUNT", Currency.USD)
    transaction = transfer(system, amount=Decimal("100.50"), is_external=True, external_recipient=external)
    queue.add(transaction)
    processor.process_all(NOW)
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.fee == Decimal("1.01")
    assert sender._balance == Decimal("98.49")
    assert recipient._balance == 0
    assert processor.external_adapter.get_receipt(transaction.id)["amount"] == Decimal("1.12")
    assert transaction.external_reference is not None
    assert transaction.recipient_amount == Decimal("1.12")
    assert transaction.recipient_currency is Currency.USD
    assert transaction.exchange_rate == Decimal("1") / Decimal("90")


@pytest.mark.parametrize("source,target,amount,expected", [
    (Currency.USD, Currency.RUB, "10", "900"),
    (Currency.EUR, Currency.USD, "90", "100"),
    (Currency.KZT, Currency.RUB, "100", "20"),
    (Currency.CNY, Currency.RUB, "8", "100"),
])
def test_transfer_credits_expected_amount_in_recipient_currency(system, source, target, amount, expected):
    bank, ivan, maria, _, _, queue, processor = system
    sender = BankAccount(ivan.full_name, source)
    recipient = BankAccount(maria.full_name, target)
    bank.open_account(ivan.client_id, sender)
    bank.open_account(maria.client_id, recipient)
    bank.deposit(ivan.client_id, sender.uuid, Decimal(amount))
    transaction = transfer(system, sender_id=sender.uuid, recipient_id=recipient.uuid,
                           currency=source, amount=Decimal(amount))
    queue.add(transaction)
    processor.process_all(NOW)
    assert transaction.status is TransactionStatus.COMPLETED
    assert sender._balance == 0
    assert recipient._balance == Decimal(expected)
    assert transaction.recipient_amount == Decimal(expected)
    assert transaction.recipient_currency is target


@pytest.mark.parametrize("side", ["sender", "recipient"])
@pytest.mark.parametrize("status", [AccountStatus.FROZEN, AccountStatus.CLOSED])
def test_inactive_accounts_reject_transfer_without_balance_changes(system, side, status):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    (sender if side == "sender" else recipient).account_status = status
    transaction = transfer(system)
    queue.add(transaction)
    processor.process_all(NOW)
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.attempts == 1
    expected_error = "AccountFrozenError" if status is AccountStatus.FROZEN else "AccountClosedError"
    assert transaction.errors[-1]["error_type"] == expected_error
    assert sender._balance == Decimal("200")
    assert recipient._balance == 0


@pytest.mark.parametrize("violation,reason", [
    ("owner", "Account not found or does not belong to client"),
    ("blocked", "Client is blocked"),
    ("missing_sender", "Account not found or does not belong to client"),
    ("missing_recipient", "Account not found"),
    ("currency", "Transaction currency must match account currency"),
    ("negative", "Transfers from negative balances are prohibited"),
])
def test_access_and_currency_rules(system, violation, reason):
    bank, ivan, maria, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    changes = {}
    if violation == "owner":
        changes["client_id"] = maria.client_id
    elif violation == "blocked":
        ivan.status = ClientStatus.BLOCKED
    elif violation == "missing_sender":
        changes["sender_id"] = "missing"
    elif violation == "missing_recipient":
        changes["recipient_id"] = "missing"
    elif violation == "currency":
        changes["currency"] = Currency.USD
    else:
        sender._balance = Decimal("-1")  # Simulate invalid legacy state.
    before = sender._balance
    transaction = transfer(system, **changes)
    queue.add(transaction)
    processor.process_all(NOW)
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.failure_reason == reason
    assert transaction.errors[-1]["error_type"] == "InvalidOperationError"
    assert sender._balance == before
    assert recipient._balance == 0
    assert len(processor.errors) == 1
    assert processor.process_all(NOW + timedelta(hours=1)) == []


@pytest.mark.parametrize("operation", [TransactionType.DEPOSIT, TransactionType.WITHDRAWAL])
def test_deposit_and_withdrawal_require_matching_currency(system, operation):
    _, _, _, sender, _, queue, processor = system
    transaction = transfer(system, transaction_type=operation, currency=Currency.USD,
                           sender_id=sender.uuid if operation is TransactionType.WITHDRAWAL else None,
                           recipient_id=sender.uuid if operation is TransactionType.DEPOSIT else None)
    queue.add(transaction)
    processor.process_all(NOW)
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.failure_reason == "Transaction currency must match account currency"
    assert transaction.errors[-1]["error_type"] == "InvalidOperationError"
    assert sender._balance == 0


def test_transfer_is_rejected_when_money_covers_principal_but_not_fee(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("100"))
    transaction = transfer(system, is_external=True)
    queue.add(transaction)
    processor.process_all(NOW)
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.errors[-1]["error_type"] == "InsufficientFundsError"
    assert sender._balance == Decimal("100")
    assert recipient._balance == 0


def test_premium_can_transfer_from_negative_balance_and_respects_overdraft(system):
    bank, ivan, _, _, recipient, queue, processor = system
    premium = PremiumAccount(ivan.full_name, overdraft_limit=Decimal("500"))
    bank.open_account(ivan.client_id, premium)
    bank.withdraw(ivan.client_id, premium.uuid, Decimal("100"))
    assert premium._balance == Decimal("-200")
    first = transfer(system, sender_id=premium.uuid, is_external=True)
    second = transfer(system, sender_id=premium.uuid)
    queue.add(first)
    queue.add(second)
    processor.process_all(NOW)
    assert first.status is TransactionStatus.COMPLETED
    assert second.status is TransactionStatus.FAILED
    assert second.errors[-1]["error_type"] == "InsufficientFundsError"
    assert premium._balance == Decimal("-401")
    assert recipient._balance == 0
    assert processor.external_adapter.get_receipt(first.id)["amount"] == Decimal("100")


def test_investment_transfer_uses_only_available_money(system):
    bank, ivan, _, _, recipient, queue, processor = system
    investment = InvestmentAccount(ivan.full_name)
    bank.open_account(ivan.client_id, investment)
    bank.deposit(ivan.client_id, investment.uuid, Decimal("200"))
    bank.invest(ivan.client_id, investment.uuid, "stocks", Decimal("150"))
    transaction = transfer(system, sender_id=investment.uuid)
    queue.add(transaction)
    processor.process_all(NOW)
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.errors[-1]["error_type"] == "InsufficientFundsError"
    assert investment._balance == Decimal("50")
    assert investment._portfolio["stocks"] == Decimal("150")
    assert recipient._balance == 0


def test_temporary_failures_retry_three_times_and_stop(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    transaction = transfer(system, is_external=True)
    queue.add(transaction)
    processor.external_adapter = ExternalTransferAdapter(failures_remaining=3)
    for attempt in range(3):
        processor.process_all(NOW + timedelta(minutes=attempt))
    assert processor.external_adapter.failures_remaining == 0
    assert processor.external_adapter.get_receipt(transaction.id) is None
    assert processor.process_all(NOW + timedelta(hours=1)) == []
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.attempts == 3
    assert transaction.completed_at == NOW + timedelta(minutes=2)
    assert len(transaction.errors) == len(processor.errors) == 3
    assert sender._balance == Decimal("200")
    assert recipient._balance == 0


def test_retry_rolls_back_both_balances_and_can_succeed(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    transaction = transfer(system)
    queue.add(transaction)
    original_deposit = recipient.deposit

    def interrupted_deposit(amount):
        original_deposit(amount)
        raise TemporaryTransactionError("recipient temporarily unavailable")

    with patch.object(recipient, "deposit", side_effect=interrupted_deposit):
        processor.process_all(NOW)
    assert sender._balance == Decimal("200")
    assert recipient._balance == 0
    assert transaction.status is TransactionStatus.RETRY_WAIT
    assert processor.process_all(NOW + timedelta(seconds=59)) == []
    processor.process_all(NOW + timedelta(minutes=1))
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.attempts == 2
    assert transaction.failure_reason is None
    assert transaction.started_at == NOW
    assert transaction.last_attempt_at == transaction.completed_at == NOW + timedelta(minutes=1)
    assert sender._balance == Decimal("100")
    assert recipient._balance == Decimal("100")
    assert len(transaction.errors) == 1


@pytest.mark.parametrize("operation", [TransactionType.DEPOSIT, TransactionType.WITHDRAWAL, TransactionType.TRANSFER])
def test_lost_acknowledgement_never_reapplies_committed_operation(system, operation):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    transaction = transfer(
        system, transaction_type=operation,
        sender_id=None if operation is TransactionType.DEPOSIT else sender.uuid,
        recipient_id=sender.uuid if operation is TransactionType.DEPOSIT else (
            recipient.uuid if operation is TransactionType.TRANSFER else None
        ),
    )
    queue.add(transaction)
    original_execute = bank.execute_transaction

    def lost_ack(*args, **kwargs):
        original_execute(*args, **kwargs)
        raise TimeoutError("result lost after commit")

    with patch.object(bank, "execute_transaction", side_effect=lost_ack):
        processor.process_all(NOW)
    after_commit = sender._balance, recipient._balance
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.attempts == 1
    assert transaction.failure_reason is None
    assert transaction.errors[0]["error_type"] == "TimeoutError"
    with pytest.raises(InvalidOperationError):
        queue.cancel(transaction.id)
    processor.process_all(NOW + timedelta(minutes=1))
    assert transaction.status is TransactionStatus.COMPLETED
    assert (sender._balance, recipient._balance) == after_commit
    assert after_commit == {
        TransactionType.DEPOSIT: (Decimal("300"), Decimal("0")),
        TransactionType.WITHDRAWAL: (Decimal("100"), Decimal("0")),
        TransactionType.TRANSFER: (Decimal("100"), Decimal("100")),
    }[operation]
    # Even a second processor / queue with the same ID cannot move money twice.
    duplicate = copy(transaction)
    duplicate.status = TransactionStatus.PENDING
    other_queue = TransactionQueue()
    other_queue.add(duplicate)
    TransactionProcessor(bank, other_queue).process_all(NOW + timedelta(minutes=2))
    assert duplicate.status is TransactionStatus.COMPLETED
    assert (sender._balance, recipient._balance) == after_commit


@pytest.mark.parametrize("hour,minute,second", [(0, 0, 0), (2, 30, 0), (4, 59, 59)])
def test_night_restriction_waits_until_five_without_spending_attempts(system, hour, minute, second):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    local_zone = timezone(timedelta(hours=3))
    night = datetime(2026, 10, 15, hour, minute, second, tzinfo=local_zone)
    morning = night.replace(hour=5, minute=0, second=0)
    transaction = transfer(system)
    queue.add(transaction)
    bank.clock = lambda: night
    processor.process_all()
    assert transaction.status is TransactionStatus.RETRY_WAIT
    assert transaction.retry_at == morning
    assert transaction.scheduled_at is None
    assert transaction.attempts == 0
    assert sender._balance == Decimal("200")
    assert recipient._balance == 0
    bank.clock = lambda: morning
    processor.process_all()
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.attempts == 1
    assert sender._balance == Decimal("100")
    assert recipient._balance == Decimal("100")


def test_permanent_error_after_mutation_rolls_back_and_does_not_retry(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    transaction = transfer(system)
    queue.add(transaction)
    original = recipient.deposit

    def broken_deposit(amount):
        original(amount)
        raise RuntimeError("unexpected failure")

    with patch.object(recipient, "deposit", side_effect=broken_deposit):
        processor.process_all(NOW)
    assert transaction.status is TransactionStatus.FAILED
    assert sender._balance == Decimal("200")
    assert recipient._balance == 0
    assert processor.errors[0]["error_type"] == "RuntimeError"
    assert processor.process_all(NOW + timedelta(days=1)) == []


def test_cancelled_transaction_is_not_executed(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    transaction = transfer(system)
    queue.add(transaction)
    queue.cancel(transaction.id)
    assert processor.process_all(NOW) == []
    assert transaction.attempts == 0
    assert sender._balance == Decimal("200")
    assert recipient._balance == 0


def test_too_small_converted_amount_is_rejected_without_debit(system):
    bank, ivan, maria, sender, _, queue, processor = system
    usd = BankAccount(maria.full_name, Currency.USD)
    bank.open_account(maria.client_id, usd)
    bank.deposit(ivan.client_id, sender.uuid, Decimal("1"))
    transaction = transfer(system, amount=Decimal("0.01"), recipient_id=usd.uuid)
    queue.add(transaction)
    processor.process_all(NOW)
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.errors[-1]["error_type"] == "InvalidOperationError"
    assert transaction.failure_reason == "Invalid transaction amount"
    assert sender._balance == Decimal("1")
    assert usd._balance == 0


def test_third_attempt_recovers_committed_result_after_lost_response(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    transaction = transfer(system)
    queue.add(transaction)
    original = bank.execute_transaction
    calls = 0

    def unreliable_execute(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            original(*args, **kwargs)
        raise TimeoutError("unavailable response")

    with patch.object(bank, "execute_transaction", side_effect=unreliable_execute):
        for minute in range(3):
            processor.process_all(NOW + timedelta(minutes=minute))
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.attempts == 3
    assert len(transaction.errors) == 3
    assert transaction.fee == 0
    assert sender._balance == recipient._balance == Decimal("100")


def test_subcent_transfer_is_rejected_instead_of_creating_money(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("1"))
    with pytest.raises(InvalidOperationError, match="multiple of 0.01"):
        queue.add(transfer(system, amount=Decimal("0.005")))
    assert processor.process_all() == []
    assert sender._balance + recipient._balance == Decimal("1")


@pytest.mark.parametrize("operation", ["deposit", "withdraw", "invest"])
def test_direct_money_operations_also_reject_subcent_amounts(system, operation):
    bank, ivan, _, _, _, _, _ = system
    account = InvestmentAccount(ivan.full_name)
    bank.open_account(ivan.client_id, account)
    bank.deposit(ivan.client_id, account.uuid, Decimal("1"))
    with pytest.raises(InvalidOperationError, match="multiple of 0.01"):
        if operation == "invest":
            bank.invest(ivan.client_id, account.uuid, "stocks", Decimal("0.005"))
        else:
            getattr(bank, operation)(ivan.client_id, account.uuid, Decimal("0.005"))
    assert account._balance == Decimal("1")
    assert sum(account._portfolio.values()) == 0


def test_same_currency_transfer_preserves_money_and_accepts_trailing_zeros(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("1"))
    transaction = transfer(system, amount=Decimal("0.0100"))
    queue.add(transaction)
    processor.process_all()
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.amount == transaction.recipient_amount == Decimal("0.01")
    assert transaction.amount.as_tuple().exponent == -4
    assert sender._balance == Decimal("0.99")
    assert recipient._balance == Decimal("0.01")
    assert sender._balance + recipient._balance == Decimal("1")


def test_queued_payment_keeps_original_instructions_and_identity(system):
    bank, ivan, maria, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("100"))
    transaction = transfer(system, amount=Decimal("10"))
    original_id = transaction.id
    queue.add(transaction)
    attempted_changes = {
        "amount": Decimal("90"), "recipient_id": "another-account",
        "sender_id": "another-sender", "client_id": maria.client_id,
        "is_external": True, "id": "another-id", "currency": Currency.USD,
        "transaction_type": TransactionType.WITHDRAWAL, "priority": 999,
        "scheduled_at": NOW + timedelta(days=1),
        "external_recipient": ExternalRecipient("OTHER", "EXT-2", Currency.USD),
    }
    for field, value in attempted_changes.items():
        with pytest.raises(AttributeError, match="immutable"):
            setattr(transaction, field, value)
    processor.process_all()
    assert transaction.id == original_id
    assert transaction.status is TransactionStatus.COMPLETED
    assert sender._balance == Decimal("90")
    assert recipient._balance == Decimal("10")


def test_external_transfer_retries_without_local_recipient_or_double_fee(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    transaction = transfer(system, is_external=True)
    queue.add(transaction)
    processor.external_adapter = ExternalTransferAdapter(failures_remaining=1)
    processor.process_all()
    assert transaction.status is TransactionStatus.RETRY_WAIT
    assert sender._balance == Decimal("200")
    assert processor.external_adapter.get_receipt(transaction.id) is None
    assert transaction.scheduled_at is None
    bank.clock = lambda: NOW + timedelta(seconds=59)
    assert processor.process_all() == []
    bank.clock = lambda: NOW + timedelta(minutes=1)
    processor.process_all()
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.attempts == 2
    assert transaction.fee == Decimal("1")
    assert sender._balance == Decimal("99")
    assert recipient._balance == 0
    assert len(bank.search_accounts()) == 2
    receipt = processor.external_adapter.get_receipt(transaction.id)
    assert receipt["recipient"] == transaction.external_recipient
    assert receipt["amount"] == Decimal("100")
    assert transaction.external_reference == receipt["reference"]
    assert processor.process_all() == []
    assert sender._balance == Decimal("99")


def test_external_acceptance_with_lost_response_keeps_exactly_one_debit(system):
    bank, ivan, _, sender, _, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    transaction = transfer(system, is_external=True)
    queue.add(transaction)
    original = processor.external_adapter.send

    def lose_response(*args, **kwargs):
        original(*args, **kwargs)
        raise TimeoutError("External acceptance response lost")

    with patch.object(processor.external_adapter, "send", side_effect=lose_response) as send:
        processor.process_all()
        assert send.call_count == 1
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.errors[-1]["error_type"] == "TimeoutError"
    assert sender._balance == Decimal("99")
    reference = transaction.external_reference
    duplicate = copy(transaction)
    duplicate.status = TransactionStatus.PENDING
    other_queue = TransactionQueue()
    other_queue.add(duplicate)
    TransactionProcessor(bank, other_queue, processor.external_adapter).process_all()
    assert duplicate.status is TransactionStatus.COMPLETED
    assert duplicate.external_reference == reference
    assert sender._balance == Decimal("99")
    assert processor.external_adapter.get_receipt(transaction.id)["amount"] == Decimal("100")


def test_shared_clock_defers_until_bank_local_morning_and_preserves_schedule(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    night = datetime(2026, 10, 15, 23, tzinfo=timezone.utc)  # 02:00 on Oct 16 in bank timezone.
    morning = datetime(2026, 10, 16, 2, tzinfo=timezone.utc)  # 05:00 UTC+03:00.
    transaction = transfer(system, scheduled_at=night)
    queue.add(transaction)
    bank.clock = lambda: night
    processor.process_all()
    assert transaction.status is TransactionStatus.RETRY_WAIT
    assert transaction.retry_at == morning
    assert transaction.scheduled_at == night
    assert transaction.attempts == 0
    bank.clock = lambda: morning - timedelta(seconds=1)
    assert processor.process_all() == []
    bank.clock = lambda: morning
    processor.process_all()
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.completed_at == morning
    assert transaction.last_attempt_at == morning
    assert transaction.scheduled_at == night
    assert sender._balance == recipient._balance == Decimal("100")


def test_explicit_processing_time_is_used_for_bank_checks_too(system):
    bank, ivan, _, sender, recipient, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    queue.add(transfer(system))
    bank.clock = lambda: datetime(2026, 10, 15, 23, tzinfo=timezone.utc)
    processed = processor.process_all(NOW)
    assert processed[0].status is TransactionStatus.COMPLETED
    assert sender._balance == recipient._balance == Decimal("100")


def test_cancelling_waiting_retry_uses_the_same_clock(system):
    bank, ivan, _, sender, _, queue, processor = system
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    transaction = transfer(system, is_external=True)
    queue.add(transaction)
    processor.external_adapter = ExternalTransferAdapter(failures_remaining=1)
    processor.process_all()
    cancellation_time = NOW + timedelta(seconds=30)
    bank.clock = lambda: cancellation_time
    queue.cancel(transaction.id)
    assert transaction.status is TransactionStatus.CANCELLED
    assert transaction.completed_at == cancellation_time
    bank.clock = lambda: NOW + timedelta(minutes=1)
    assert processor.process_all() == []
    assert sender._balance == Decimal("200")
    assert processor.external_adapter.get_receipt(transaction.id) is None
