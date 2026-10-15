from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from src.exceptions import InvalidOperationError
from src.models import Currency


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


class Transaction:

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
    ):
        if not isinstance(transaction_type, TransactionType):
            raise InvalidOperationError("Invalid transaction type")
        if not isinstance(client_id, str) or not client_id.strip():
            raise InvalidOperationError("Client ID must be a non-empty string")
        if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0:
            raise InvalidOperationError("Amount must be a positive finite Decimal")
        if not isinstance(currency, Currency):
            raise InvalidOperationError("Invalid currency")
        if type(priority) is not int:
            raise InvalidOperationError("Priority must be an integer")
        if not isinstance(is_external, bool):
            raise InvalidOperationError("External flag must be a boolean")
        if is_external and transaction_type is not TransactionType.TRANSFER:
            raise InvalidOperationError("Only transfers can be external")
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
        elif sender_id is None or recipient_id is None or sender_id == recipient_id:
            raise InvalidOperationError("Transfer requires two different accounts")

        self.id = uuid4().hex
        self.transaction_type = transaction_type
        self.client_id = client_id
        self.amount = amount
        self.currency = currency
        self.sender_id = sender_id
        self.recipient_id = recipient_id
        self.priority = priority
        self.scheduled_at = scheduled_at
        self.is_external = is_external

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
