from abc import ABC, abstractmethod
from enum import Enum
import uuid
from decimal import Decimal


class AccountStatus(Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class AbstractAccount(ABC):
    def __init__(self, owner: str):
        self.owner = owner
        self.uuid = uuid.uuid4()
        self.account_status = AccountStatus.ACTIVE
        self.__balance = Decimal("0.00")

    @abstractmethod
    def deposit(self, amount):
        pass

    @abstractmethod
    def withdraw(self, amount):
        pass

    @abstractmethod
    def get_account_info(self):
        pass
