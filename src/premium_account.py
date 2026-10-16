from decimal import Decimal

from src.exceptions import InvalidOperationError, InsufficientFundsError
from src.models import BankAccount, AccountStatus, Currency, validate_money_precision


class PremiumAccount(BankAccount):
    def __init__(self,
                 owner: str,
                 currency: Currency = Currency.RUB,
                 account_id: str | None = None,
                 status: AccountStatus = AccountStatus.ACTIVE,
                 withdrawal_limit: Decimal = Decimal("100000.00"),
                 overdraft_limit: Decimal = Decimal("50000.00"),
                 fixed_fee: Decimal = Decimal("100.00")):
        for value in (withdrawal_limit, overdraft_limit, fixed_fee):
            if not isinstance(value, Decimal) or not value.is_finite():
                raise InvalidOperationError("Premium account parameters must be finite Decimal values")
            validate_money_precision(value)
        if withdrawal_limit <= 0 or overdraft_limit < 0 or fixed_fee < 0:
            raise InvalidOperationError("InvalidOperationError")
        super().__init__(owner, currency, account_id, status)
        self.withdrawal_limit = withdrawal_limit
        self.overdraft_limit = overdraft_limit
        self.fixed_fee = fixed_fee

    def withdraw(self, amount: Decimal):
        self._validate_status()
        self._validate_amount(amount)

        if amount > self.withdrawal_limit:
            raise InvalidOperationError("Withdrawal limit exceeded")
        total_debit = amount + self.fixed_fee
        if self._balance - total_debit < -self.overdraft_limit:
            raise InsufficientFundsError("Overdraft limit exceeded")

        self._balance -= total_debit

    def get_account_info(self):
        info = super().get_account_info()
        info["withdrawal_limit"] = self.withdrawal_limit
        info["overdraft_limit"] = self.overdraft_limit
        info["fixed_fee"] = self.fixed_fee
        return info

    def __str__(self):
        parent_str = super().__str__()
        return (
            f"{parent_str}"
            f"\nWithdrawal limit: {self.withdrawal_limit}"
            f"\nOverdraft limit: {self.overdraft_limit}"
            f"\nFixed fee: {self.fixed_fee}"
        )
