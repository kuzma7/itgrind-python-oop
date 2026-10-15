from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from src.bank import Bank
from src.exceptions import (
    BankOperationRestrictedError,
    InvalidOperationError,
    TemporaryTransactionError,
)
from src.models import Currency
from src.transaction import Transaction, TransactionStatus, TransactionType
from src.transaction_queue import TransactionQueue


class TransactionProcessor:
    MAX_ATTEMPTS = 3
    RETRY_DELAY = timedelta(minutes=1)
    EXTERNAL_FEE_RATE = Decimal("0.01")
    # Educational fixed quotes: RUB per unit of each currency.
    EXCHANGE_RATES = {
        Currency.RUB: Decimal("1"),
        Currency.USD: Decimal("90"),
        Currency.EUR: Decimal("100"),
        Currency.KZT: Decimal("0.20"),
        Currency.CNY: Decimal("12.50"),
    }

    def __init__(self, bank: Bank, queue: TransactionQueue):
        if not isinstance(bank, Bank) or not isinstance(queue, TransactionQueue):
            raise InvalidOperationError("Expected Bank and TransactionQueue instances")
        self.bank = bank
        self.queue = queue
        self.errors: list[dict] = []

    def calculate_fee(self, transaction: Transaction) -> Decimal:
        """External transfer fee in the sender's currency, excluding account fees."""
        if transaction.transaction_type is TransactionType.TRANSFER and transaction.is_external:
            return (transaction.amount * self.EXTERNAL_FEE_RATE).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return Decimal("0.00")

    def get_exchange_rate(self, source: Currency, target: Currency) -> Decimal:
        if not isinstance(source, Currency) or not isinstance(target, Currency):
            raise InvalidOperationError("Invalid currency")
        return self.EXCHANGE_RATES[source] / self.EXCHANGE_RATES[target]

    def _record_error(self, transaction: Transaction, error: Exception, now: datetime) -> None:
        entry = {
            "transaction_id": transaction.id,
            "attempt": transaction.attempts,
            "timestamp": now,
            "error_type": type(error).__name__,
            "reason": str(error),
        }
        transaction.failure_reason = str(error)
        transaction.errors.append(entry.copy())
        self.errors.append(entry)

    def _complete(self, transaction: Transaction, result: dict, now: datetime) -> None:
        transaction.fee = result["fee"]
        transaction.exchange_rate = result["exchange_rate"]
        transaction.recipient_amount = result["recipient_amount"]
        transaction.recipient_currency = result["recipient_currency"]
        transaction.failure_reason = None
        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = now

    def process_next(self, now: datetime | None = None) -> Transaction | None:
        """Process one due transaction; deferred retries remain in the queue."""
        now = now if now is not None else datetime.now(timezone.utc)
        transaction = self.queue.get_next(now)
        if transaction is None:
            return None
        now = now.astimezone(timezone.utc)
        transaction.attempts += 1
        transaction.last_attempt_at = now
        try:
            rate = Decimal("1")
            if transaction.transaction_type is TransactionType.TRANSFER:
                recipient_currency = self.bank.get_account_currency(transaction.recipient_id)
                rate = self.get_exchange_rate(transaction.currency, recipient_currency)
            result = self.bank.execute_transaction(transaction, self.calculate_fee(transaction), rate)
        except BankOperationRestrictedError as error:
            # A closed operating window does not consume a temporary-error attempt.
            transaction.attempts -= 1
            self._record_error(transaction, error, now)
            transaction.status = TransactionStatus.RETRY_WAIT
            transaction.scheduled_at = error.retry_at if error.retry_at > now else now + self.RETRY_DELAY
        except (TemporaryTransactionError, TimeoutError, ConnectionError) as error:
            self._record_error(transaction, error, now)
            committed = self.bank.get_transaction_result(transaction.id)
            if committed is not None:
                # The response may be lost after the bank has committed.
                self._complete(transaction, committed, now)
            elif transaction.attempts < self.MAX_ATTEMPTS:
                transaction.status = TransactionStatus.RETRY_WAIT
                transaction.scheduled_at = now + self.RETRY_DELAY
            else:
                transaction.status = TransactionStatus.FAILED
                transaction.completed_at = now
        except Exception as error:
            # Business errors and unexpected failures are recorded without retries.
            self._record_error(transaction, error, now)
            committed = self.bank.get_transaction_result(transaction.id)
            if committed is not None:
                self._complete(transaction, committed, now)
            else:
                transaction.status = TransactionStatus.FAILED
                transaction.completed_at = now
        else:
            self._complete(transaction, result, now)
        return transaction

    def process_all(self, now: datetime | None = None) -> list[Transaction]:
        """Drain ready work once, without sleeping for future operations."""
        processed = []
        while True:
            transaction = self.process_next(now)
            if transaction is None:
                return processed
            processed.append(transaction)
