from abc import ABC, abstractmethod
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

    def deposit(self, amount):
        if self.account_status == AccountStatus.FROZEN:
            raise AccountFrozenError("AccountFrozenError")

        elif self.account_status == AccountStatus.CLOSED:
            raise AccountClosedError("AccountClosedError")

        if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0:
            raise InvalidOperationError("InvalidOperationError")
        self._balance += amount

    def withdraw(self, amount):
        if self.account_status == AccountStatus.FROZEN:
            raise AccountFrozenError("AccountFrozenError")

        if self.account_status == AccountStatus.CLOSED:
            raise AccountClosedError("AccountClosedError")

        if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0:
            raise InvalidOperationError("Invalid withdrawal amount")

        if amount > self._balance:
            raise InsufficientFundsError("Insufficient funds")
        self._balance -= amount

    def get_account_info(self):
        return {
            "Account ID": self.uuid,
            "Owner": self.owner
        }

    def __str__(self):
        return f"Account type: {type(self).__name__}\nOwner: {self.owner}\nAccount ID (last 4 chars): {self.uuid[-4:]}\nAccount status: {self.account_status.value}\nBalance {self._balance} {self.currency.value}"
