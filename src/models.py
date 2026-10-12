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


class AbstractAccount(ABC):
    def __init__(self, owner: str):
        self.owner = owner
        self.uuid = uuid.uuid4()
        self.account_status = AccountStatus.ACTIVE
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
    def __init__(self, owner: str):
        super().__init__(owner)

    def deposit(self, amount):
        if self.account_status == AccountStatus.FROZEN:
            raise AccountFrozenError("AccountFrozenError")
        elif self.account_status == AccountStatus.CLOSED:
            raise AccountClosedError("AccountClosedError")
        if not isinstance(amount, Decimal) and amount <= 0:
            raise InvalidOperationError("InvalidOperationError")
        self._balance += amount


