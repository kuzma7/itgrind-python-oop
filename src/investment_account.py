from decimal import Decimal, ROUND_HALF_UP

from src.exceptions import InvalidOperationError, InsufficientFundsError
from src.models import BankAccount, Currency, AccountStatus


class InvestmentAccount(BankAccount):

    def __init__(
            self,
            owner: str,
            currency: Currency = Currency.RUB,
            account_id: str | None = None,
            status: AccountStatus = AccountStatus.ACTIVE,
    ):
        super().__init__(owner, currency, account_id, status)

        self._portfolio = {
            "stocks": Decimal("0.00"),
            "bonds": Decimal("0.00"),
            "etf": Decimal("0.00"),
        }

    def withdraw(self, amount: Decimal) -> None:
        super().withdraw(amount)

    def invest(self, asset_type: str, amount: Decimal) -> None:
        self._validate_status()
        self._validate_amount(amount)

        if not isinstance(asset_type, str) or asset_type not in self._portfolio:
            raise InvalidOperationError("Unsupported asset type")

        if amount > self._balance:
            raise InsufficientFundsError("Insufficient funds")

        self._balance -= amount
        self._portfolio[asset_type] += amount

    def project_yearly_growth(self, growth_rates: dict[str, Decimal]) -> Decimal:
        self._validate_status()

        if not isinstance(growth_rates, dict):
            raise InvalidOperationError("Growth rates must be a dictionary")
        for asset_type in self._portfolio:
            if asset_type not in growth_rates:
                raise InvalidOperationError(f"Missing growth rate for {asset_type}")
            rate = growth_rates[asset_type]
            if not isinstance(rate, Decimal) or not rate.is_finite():
                raise InvalidOperationError(f"Invalid growth rate for {asset_type}")

        total_growth = Decimal("0.00")

        for asset_type, amount in self._portfolio.items():
            rate = growth_rates[asset_type]
            total_growth += amount * rate

        return total_growth.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def get_account_info(self) -> dict:
        info = super().get_account_info()

        info["portfolio"] = self._portfolio.copy()
        info["portfolio_value"] = sum(
            self._portfolio.values(),
            Decimal("0.00"),
        )
        info["available_balance"] = self._balance

        return info

    def __str__(self) -> str:
        parent_str = super().__str__()

        portfolio_value = sum(
            self._portfolio.values(),
            Decimal("0.00"),
        )

        return (
            f"{parent_str}"
            f"\nStocks: {self._portfolio['stocks']}"
            f"\nBonds: {self._portfolio['bonds']}"
            f"\nETF: {self._portfolio['etf']}"
            f"\nPortfolio value: {portfolio_value} {self.currency.value}"
        )
