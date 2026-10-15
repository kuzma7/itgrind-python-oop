from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from src.bank import Bank
from src.exceptions import (
    BankOperationRestrictedError,
    InvalidOperationError,
    TemporaryTransactionError,
)
from src.models import Currency
from src.transaction import ExternalRecipient, Transaction, TransactionStatus, TransactionType
from src.transaction_queue import TransactionQueue


class ExternalTransferAdapter:

    def __init__(self, failures_remaining: int = 0):
        self.failures_remaining = failures_remaining
        self._receipts: dict[str, dict] = {}

    def get_receipt(self, transaction_id: str) -> dict | None:
        receipt = self._receipts.get(transaction_id)
        return receipt.copy() if receipt is not None else None

    def send(self, transaction_id: str, recipient: ExternalRecipient, amount: Decimal) -> dict:
        existing = self.get_receipt(transaction_id)
        if existing is not None:
            if existing["recipient"] != recipient or existing["amount"] != amount:
                raise InvalidOperationError("External payment ID already has different instructions")
            return existing
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise TemporaryTransactionError("External bank temporarily unavailable")
        receipt = {
            "reference": uuid4().hex,
            "recipient": recipient,
            "amount": amount,
            "currency": recipient.currency,
        }
        self._receipts[transaction_id] = receipt
        return receipt.copy()


class TransactionProcessor:
    MAX_ATTEMPTS = 3
    RETRY_DELAY = timedelta(minutes=1)
    EXTERNAL_FEE_RATE = Decimal("0.01")
    EXCHANGE_RATES = {
        Currency.RUB: Decimal("1"),
        Currency.USD: Decimal("90"),
        Currency.EUR: Decimal("100"),
        Currency.KZT: Decimal("0.20"),
        Currency.CNY: Decimal("12.50"),
    }

    def __init__(
        self, bank: Bank, queue: TransactionQueue, external_adapter: ExternalTransferAdapter | None = None,
    ):
        if not isinstance(bank, Bank) or not isinstance(queue, TransactionQueue):
            raise InvalidOperationError("Expected Bank and TransactionQueue instances")
        self.bank = bank
        self.queue = queue
        self.queue.clock = bank._get_current_time
        self.external_adapter = external_adapter if external_adapter is not None else ExternalTransferAdapter()
        self.errors: list[dict] = []

    def _send_external(self, transaction: Transaction, amount: Decimal) -> dict:
        try:
            return self.external_adapter.send(transaction.id, transaction.external_recipient, amount)
        except Exception as error:
            receipt = self.external_adapter.get_receipt(transaction.id)
            if receipt is None or receipt["recipient"] != transaction.external_recipient or receipt["amount"] != amount:
                raise
            self._record_error(transaction, error, transaction.last_attempt_at)
            return receipt

    def calculate_fee(self, transaction: Transaction) -> Decimal:
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
        transaction.external_reference = result["external_reference"]
        transaction.failure_reason = None
        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = now

    def process_next(self, now: datetime | None = None) -> Transaction | None:
        now = now if now is not None else self.bank._get_current_time()
        transaction = self.queue.get_next(now)
        if transaction is None:
            return None
        now = now.astimezone(timezone.utc)
        transaction.attempts += 1
        transaction.last_attempt_at = now
        try:
            rate = Decimal("1")
            if transaction.transaction_type is TransactionType.TRANSFER:
                recipient_currency = (
                    transaction.external_recipient.currency if transaction.is_external
                    else self.bank.get_account_currency(transaction.recipient_id)
                )
                rate = self.get_exchange_rate(transaction.currency, recipient_currency)
            result = self.bank.execute_transaction(
                transaction, self.calculate_fee(transaction), rate, now=now, external_send=self._send_external,
            )
        except BankOperationRestrictedError as error:
            transaction.attempts -= 1
            self._record_error(transaction, error, now)
            transaction.status = TransactionStatus.RETRY_WAIT
            transaction.retry_at = error.retry_at if error.retry_at > now else now + self.RETRY_DELAY
        except (TemporaryTransactionError, TimeoutError, ConnectionError) as error:
            self._record_error(transaction, error, now)
            committed = self.bank.get_transaction_result(transaction.id)
            if committed is not None:
                self._complete(transaction, committed, now)
            elif transaction.attempts < self.MAX_ATTEMPTS:
                transaction.status = TransactionStatus.RETRY_WAIT
                transaction.retry_at = now + self.RETRY_DELAY
            else:
                transaction.status = TransactionStatus.FAILED
                transaction.completed_at = now
        except Exception as error:
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
        processed = []
        while True:
            transaction = self.process_next(now)
            if transaction is None:
                return processed
            processed.append(transaction)
