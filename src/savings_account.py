from decimal import Decimal, ROUND_HALF_UP

from src.exceptions import InvalidOperationError, InsufficientFundsError
from src.models import BankAccount, Currency, AccountStatus


class SavingsAccount(BankAccount):

    def __init__(
            self,
            owner: str,
            currency: Currency = Currency.RUB,
            account_id: str | None = None,
            status: AccountStatus = AccountStatus.ACTIVE,
            min_balance: Decimal = Decimal("0.00"),
            monthly_rate: Decimal = Decimal("0.05")):
        if not isinstance(min_balance, Decimal) or not isinstance(monthly_rate, Decimal):
            raise InvalidOperationError("InvalidOperationError")
        if not min_balance.is_finite() or min_balance < 0 or not monthly_rate.is_finite() or monthly_rate < 0:
            raise InvalidOperationError("InvalidOperationError")
        super().__init__(owner, currency, account_id, status)
        self.min_balance = min_balance
        self.monthly_rate = monthly_rate

    def withdraw(self, amount):
        self._validate_status()
        self._validate_amount(amount)
        if self._balance - amount < self.min_balance:
            raise InsufficientFundsError("Withdrawal would violate minimum balance")
        super().withdraw(amount)

    def apply_monthly_interest(self):
        self._validate_status()
        interest = (self._balance * self.monthly_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if interest > 0:
            self.deposit(interest)

        return interest

    def get_account_info(self):
        info = super().get_account_info()
        info["min_balance"] = self.min_balance
        info["monthly_rate"] = self.monthly_rate
        return info

    def __str__(self):
        parent_str = super().__str__()
        return parent_str + f"\nMin balance: {self.min_balance}\nMonthly rate: {self.monthly_rate * 100}%"



