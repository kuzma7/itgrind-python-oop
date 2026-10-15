from abc import ABC, abstractmethod
from contextvars import ContextVar

_bank_operation_token: ContextVar[object | None] = ContextVar("bank_operation_token", default=None)
from enum import Enum
import uuid
from decimal import Decimal

from src.exceptions import AccountClosedError
from src.exceptions import AccountFrozenError
from src.exceptions import InvalidOperationError
from src.exceptions import InsufficientFundsError


class AccountStatus(Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class Currency(Enum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"
    KZT = "KZT"
    CNY = "CNY"


class AbstractAccount(ABC):
    def __init__(
            self,
            owner: str,
            account_id: str,
            status: AccountStatus = AccountStatus.ACTIVE
    ):
        self.owner = owner
        self.uuid = account_id
        self.account_status = status
        self._balance = Decimal("0.00")

    @abstractmethod
    def deposit(self, amount):
        pass

    @abstractmethod
    def withdraw(self, amount):
        pass

    @abstractmethod
    def get_account_info(self):
        pass


class BankAccount(AbstractAccount):
    def __init__(
            self,
            owner: str,
            currency: Currency = Currency.RUB,
            account_id: str | None = None,
            status: AccountStatus = AccountStatus.ACTIVE
    ):
        if not isinstance(owner, str) or not owner.strip():
            raise InvalidOperationError("Owner must be a non-empty string")

        if not isinstance(currency, Currency):
            raise InvalidOperationError("Unsupported currency")

        if not isinstance(status, AccountStatus):
            raise InvalidOperationError("Invalid account status")

        if account_id is None:
            account_id = uuid.uuid4().hex[:8]
        elif not isinstance(account_id, str) or not account_id.strip():
            raise InvalidOperationError("Invalid account ID")

        super().__init__(owner, account_id, status)
        self.currency = currency
        self._bank_token: object | None = None

    def _validate_status(self):
        if self._bank_token is not None and _bank_operation_token.get() is not self._bank_token:
            raise InvalidOperationError("Use Bank for transactions on registered accounts")
        if self.account_status == AccountStatus.FROZEN:
            raise AccountFrozenError("Account is frozen")

        if self.account_status == AccountStatus.CLOSED:
            raise AccountClosedError("Account is closed")

    def _validate_amount(self, amount: Decimal):
        if (
                not isinstance(amount, Decimal)
                or not amount.is_finite()
                or amount <= 0
        ):
            raise InvalidOperationError("Invalid transaction amount")

    def _validate_funds(self, amount: Decimal):
        if amount > self._balance:
            raise InsufficientFundsError("Insufficient funds")

    def deposit(self, amount: Decimal):
        self._validate_status()
        self._validate_amount(amount)

        self._balance += amount

    def withdraw(self, amount: Decimal):
        self._validate_status()
        self._validate_amount(amount)
        self._validate_funds(amount)

        self._balance -= amount

    def get_account_info(self):
        return {
            "Account ID": self.uuid,
            "Owner": self.owner
        }

    def __str__(self):
        return f"Account type: {type(self).__name__}\nOwner: {self.owner}\nAccount ID (last 4 chars): {self.uuid[-4:]}\nAccount status: {self.account_status.value}\nBalance {self._balance} {self.currency.value}"
