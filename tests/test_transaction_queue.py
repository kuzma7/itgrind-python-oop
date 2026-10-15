from datetime import datetime, timedelta, timezone
from decimal import Decimal
from copy import copy

import pytest

from src.exceptions import InvalidOperationError
from src.models import Currency
from src.transaction import Transaction, TransactionStatus, TransactionType
from src.transaction_queue import TransactionQueue

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def make_transaction(**changes):
    values = dict(
        transaction_type=TransactionType.DEPOSIT,
        client_id="client-1",
        amount=Decimal("100"),
        currency=Currency.RUB,
        recipient_id="account-1",
    )
    values.update(changes)
    return Transaction(**values)


def test_higher_priority_runs_first_and_equal_priorities_preserve_order():
    queue = TransactionQueue()
    low = make_transaction(priority=-1)
    first_high = make_transaction(priority=10)
    second_high = make_transaction(priority=10)
    for transaction in (low, first_high, second_high):
        queue.add(transaction)
    assert [queue.get_next(NOW) for _ in range(3)] == [first_high, second_high, low]
    assert queue.get_next(NOW) is None
    assert len(queue) == 0


def test_future_operation_waits_without_blocking_ready_work():
    queue = TransactionQueue()
    local_zone = timezone(timedelta(hours=3))
    due = (NOW + timedelta(hours=1)).astimezone(local_zone)
    future = make_transaction(priority=100, scheduled_at=due)
    ready = make_transaction(priority=0)
    queue.add(future)
    queue.add(ready)
    assert queue.get_next(NOW) is ready
    assert queue.get_next(NOW) is None
    assert len(queue) == 1
    assert future.status is TransactionStatus.PENDING
    assert queue.get_next(due) is future


@pytest.mark.parametrize("status", [TransactionStatus.PENDING, TransactionStatus.RETRY_WAIT])
def test_waiting_operation_can_be_cancelled(status):
    queue = TransactionQueue()
    transaction = make_transaction(scheduled_at=NOW + timedelta(days=1))
    queue.add(transaction)
    transaction.status = status
    queue.cancel(transaction.id)
    assert transaction.status is TransactionStatus.CANCELLED
    assert queue.get_next(NOW + timedelta(days=2)) is None
    assert len(queue) == 0


@pytest.mark.parametrize("status", [
    TransactionStatus.PROCESSING, TransactionStatus.COMPLETED,
    TransactionStatus.FAILED, TransactionStatus.CANCELLED,
])
def test_running_or_finished_operation_cannot_be_cancelled(status):
    queue = TransactionQueue()
    transaction = make_transaction()
    queue.add(transaction)
    transaction.status = status
    with pytest.raises(InvalidOperationError, match="Only waiting transactions can be cancelled"):
        queue.cancel(transaction.id)
    assert transaction.status is status


def test_duplicate_transaction_id_cannot_enter_queue_twice():
    queue = TransactionQueue()
    transaction = make_transaction()
    queue.add(transaction)
    duplicate = copy(transaction)
    for repeated in (transaction, duplicate):
        with pytest.raises(InvalidOperationError, match="Transaction already exists in queue"):
            queue.add(repeated)
    assert queue.get_next(NOW) is transaction
    assert queue.get_next(NOW) is None


@pytest.mark.parametrize("status", [TransactionStatus.COMPLETED, TransactionStatus.FAILED, TransactionStatus.CANCELLED])
def test_finished_transaction_cannot_be_submitted_again(status):
    transaction = make_transaction()
    transaction.status = status
    with pytest.raises(InvalidOperationError, match="Only pending transactions can be added"):
        TransactionQueue().add(transaction)
