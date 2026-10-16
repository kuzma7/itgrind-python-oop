from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from src.exceptions import InvalidOperationError
from src.models import Currency, validate_money_precision


class TransactionType(Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"


class TransactionStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY_WAIT = "retry_wait"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ExternalRecipient:
    bank_code: str
    account_number: str
    currency: Currency

    def __post_init__(self):
        if not isinstance(self.bank_code, str) or not self.bank_code.strip():
            raise InvalidOperationError("External bank code is required")
        if not isinstance(self.account_number, str) or not self.account_number.strip():
            raise InvalidOperationError("External account number is required")
        if not isinstance(self.currency, Currency):
            raise InvalidOperationError("Invalid external recipient currency")


@dataclass(frozen=True)
class TransactionDetails:
    id: str
    transaction_type: TransactionType
    client_id: str
    amount: Decimal
    currency: Currency
    sender_id: str | None
    recipient_id: str | None
    priority: int
    scheduled_at: datetime | None
    is_external: bool
    external_recipient: ExternalRecipient | None


class Transaction:

    def __getattr__(self, name):
        if name in TransactionDetails.__dataclass_fields__:
            return getattr(self._details, name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in TransactionDetails.__dataclass_fields__:
            raise AttributeError(f"Transaction instruction '{name}' is immutable")
        if name == "_details" and "_details" in self.__dict__:
            raise AttributeError("Transaction instructions are immutable")
        super().__setattr__(name, value)

    def __init__(
            self,
            transaction_type: TransactionType,
            client_id: str,
            amount: Decimal,
            currency: Currency,
            sender_id: str | None = None,
            recipient_id: str | None = None,
            priority: int = 0,
            scheduled_at: datetime | None = None,
            is_external: bool = False,
            external_recipient: ExternalRecipient | None = None,
    ):
        if not isinstance(transaction_type, TransactionType):
            raise InvalidOperationError("Invalid transaction type")
        if not isinstance(client_id, str) or not client_id.strip():
            raise InvalidOperationError("Client ID must be a non-empty string")
        if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0:
            raise InvalidOperationError("Amount must be a positive finite Decimal")
        validate_money_precision(amount)
        if not isinstance(currency, Currency):
            raise InvalidOperationError("Invalid currency")
        if type(priority) is not int:
            raise InvalidOperationError("Priority must be an integer")
        if not isinstance(is_external, bool):
            raise InvalidOperationError("External flag must be a boolean")
        if is_external and transaction_type is not TransactionType.TRANSFER:
            raise InvalidOperationError("Only transfers can be external")
        if is_external:
            if not isinstance(external_recipient, ExternalRecipient) or recipient_id is not None:
                raise InvalidOperationError("External transfer requires external recipient details and no local recipient")
        elif external_recipient is not None:
            raise InvalidOperationError("External recipient requires an external transfer")
        if scheduled_at is not None:
            if not isinstance(scheduled_at, datetime) or scheduled_at.utcoffset() is None:
                raise InvalidOperationError("Scheduled time must be a timezone-aware datetime")

        for account_id in (sender_id, recipient_id):
            if account_id is not None and (not isinstance(account_id, str) or not account_id.strip()):
                raise InvalidOperationError("Account ID must be a non-empty string")

        if transaction_type is TransactionType.DEPOSIT:
            if recipient_id is None or sender_id is not None:
                raise InvalidOperationError("Deposit requires a recipient and no sender")
        elif transaction_type is TransactionType.WITHDRAWAL:
            if sender_id is None or recipient_id is not None:
                raise InvalidOperationError("Withdrawal requires a sender and no recipient")
        elif is_external:
            if sender_id is None:
                raise InvalidOperationError("External transfer requires a sender")
        elif sender_id is None or recipient_id is None or sender_id == recipient_id:
            raise InvalidOperationError("Transfer requires two different accounts")

        self._details = TransactionDetails(
            uuid4().hex, transaction_type, client_id, amount, currency,
            sender_id, recipient_id, priority, scheduled_at, is_external, external_recipient,
        )

        self.status = TransactionStatus.PENDING
        self.fee = Decimal("0.00")
        self.failure_reason: str | None = None

        self.created_at = datetime.now(timezone.utc)
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.attempts = 0
        self.last_attempt_at: datetime | None = None
        self.errors: list[dict] = []
        self.exchange_rate: Decimal | None = None
        self.recipient_amount: Decimal | None = None
        self.recipient_currency: Currency | None = None
        self.retry_at: datetime | None = None
        self.external_reference: str | None = None
