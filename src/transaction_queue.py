from datetime import datetime, timezone
from typing import Callable

from src.exceptions import InvalidOperationError
from src.transaction import Transaction, TransactionStatus


class TransactionQueue:

    def __init__(self, clock: Callable[[], datetime] | None = None):
        self._transactions: list[Transaction] = []
        self.clock = clock if clock is not None else lambda: datetime.now(timezone.utc)

    def add(self, transaction: Transaction) -> None:
        if not isinstance(transaction, Transaction):
            raise InvalidOperationError("Expected Transaction instance")
        if transaction.status is not TransactionStatus.PENDING:
            raise InvalidOperationError("Only pending transactions can be added")
        if any(item.id == transaction.id for item in self._transactions):
            raise InvalidOperationError("Transaction already exists in queue")
        self._transactions.append(transaction)

    def get_next(self, now: datetime | None = None) -> Transaction | None:
        if now is None:
            now = self.clock()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise InvalidOperationError("Current time must be a timezone-aware datetime")
        now = now.astimezone(timezone.utc)

        ready = [
            transaction for transaction in self._transactions
            if transaction.status in (TransactionStatus.PENDING, TransactionStatus.RETRY_WAIT)
               and (transaction.scheduled_at is None or transaction.scheduled_at <= now)
               and (transaction.retry_at is None or transaction.retry_at <= now)
        ]
        if not ready:
            return None

        transaction = max(ready, key=lambda item: item.priority)
        transaction.status = TransactionStatus.PROCESSING
        if transaction.started_at is None:
            transaction.started_at = now
        return transaction

    def cancel(self, transaction_id: str) -> None:
        for transaction in self._transactions:
            if transaction.id == transaction_id:
                if transaction.status not in (TransactionStatus.PENDING, TransactionStatus.RETRY_WAIT):
                    raise InvalidOperationError("Only waiting transactions can be cancelled")
                transaction.status = TransactionStatus.CANCELLED
                transaction.completed_at = self.clock().astimezone(timezone.utc)
                return
        raise InvalidOperationError("Transaction not found")

    def __len__(self) -> int:
        return sum(
            transaction.status in (TransactionStatus.PENDING, TransactionStatus.RETRY_WAIT)
            for transaction in self._transactions
        )
