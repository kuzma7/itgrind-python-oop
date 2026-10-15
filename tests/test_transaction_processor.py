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
from src.transaction import Transaction, TransactionStatus, TransactionType
from src.transaction_processor import TransactionProcessor
from src.transaction_queue import TransactionQueue


NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


@pytest.fixture
def system():
    bank = Bank("Day 4 Bank")
    ivan = Client("Ivan", date(1990, 1, 1), {"email": "ivan@example.com"}, "secret")
    maria = Client("Maria", date(1990, 1, 1), {"email": "maria@example.com"}, "secret")
    bank.add_client(ivan)
    bank.add_client(maria)
    sender = BankAccount(ivan.full_name)
    recipient = BankAccount(maria.full_name)
    queue = TransactionQueue()
    with patch.object(bank, "_get_current_time", return_value=NOW):
        bank.open_account(ivan.client_id, sender)
        bank.open_account(maria.client_id, recipient)
        yield bank, ivan, maria, sender, recipient, queue, TransactionProcessor(bank, queue)


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
    assert recipient._balance == Decimal("400")
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
    assert len(processor.errors) == 3
    assert processor.process_all(NOW + timedelta(hours=1)) == [transactions[-1]]
    assert sender._balance == Decimal("459")
    assert recipient._balance == Decimal("450")
    assert len(queue) == 0
    assert processor.process_all(NOW + timedelta(days=1)) == []


def test_currency_conversion_and_fee_rounding(system):
    bank, ivan, maria, sender, _, queue, processor = system
    usd = BankAccount(maria.full_name, Currency.USD)
    bank.open_account(maria.client_id, usd)
    bank.deposit(ivan.client_id, sender.uuid, Decimal("200"))
    transaction = transfer(system, amount=Decimal("100.50"), recipient_id=usd.uuid, is_external=True)
    queue.add(transaction)
    processor.process_all(NOW)
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.fee == Decimal("1.01")
    assert sender._balance == Decimal("98.49")
    assert usd._balance == Decimal("1.12")
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
    assert recipient._balance == Decimal("100")


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
    transaction = transfer(system)
    queue.add(transaction)
    with patch.object(bank, "execute_transaction", side_effect=TemporaryTransactionError("busy")) as execute:
        for attempt in range(3):
            processor.process_all(NOW + timedelta(minutes=attempt))
        assert execute.call_count == 3
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
    transaction = transfer(system, is_external=True)
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
    assert sender._balance == Decimal("99")
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

    def lost_ack(*args):
        original_execute(*args)
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
    duplicate = transfer(
        system, transaction_type=operation, sender_id=transaction.sender_id,
        recipient_id=transaction.recipient_id,
    )
    duplicate.id = transaction.id
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
    with patch.object(bank, "_get_current_time", return_value=night):
        processor.process_all(night)
    assert transaction.status is TransactionStatus.RETRY_WAIT
    assert transaction.scheduled_at == morning
    assert transaction.attempts == 0
    assert sender._balance == Decimal("200")
    assert recipient._balance == 0
    with patch.object(bank, "_get_current_time", return_value=morning):
        processor.process_all(morning)
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

    def unreliable_execute(*args):
        nonlocal calls
        calls += 1
        if calls == 3:
            original(*args)
        raise TimeoutError("unavailable response")

    with patch.object(bank, "execute_transaction", side_effect=unreliable_execute):
        for minute in range(3):
            processor.process_all(NOW + timedelta(minutes=minute))
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.attempts == 3
    assert len(transaction.errors) == 3
    assert transaction.fee == 0
    assert sender._balance == recipient._balance == Decimal("100")
