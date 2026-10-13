from decimal import Decimal

from src.exceptions import (
    AccountFrozenError,
    InsufficientFundsError,
)
from src.investment_account import InvestmentAccount
from src.models import AccountStatus, BankAccount, Currency
from src.premium_account import PremiumAccount
from src.savings_account import SavingsAccount


def demonstrate_bank_account():
    print("\n=== BANK ACCOUNT ===")

    account = BankAccount(
        owner="Nikita",
        currency=Currency.RUB,
    )

    account.deposit(Decimal("10000.00"))
    account.withdraw(Decimal("2500.00"))

    print(account)


def demonstrate_savings_account():
    print("\n=== SAVINGS ACCOUNT ===")

    account = SavingsAccount(
        owner="Alex",
        currency=Currency.RUB,
        min_balance=Decimal("10000.00"),
        monthly_rate=Decimal("0.05"),
    )

    account.deposit(Decimal("50000.00"))
    account.withdraw(Decimal("10000.00"))

    interest = account.apply_monthly_interest()

    print(account)
    print(f"Monthly interest earned: {interest}")


def demonstrate_premium_account():
    print("\n=== PREMIUM ACCOUNT ===")

    account = PremiumAccount(
        owner="Maria",
        currency=Currency.RUB,
        withdrawal_limit=Decimal("100000.00"),
        overdraft_limit=Decimal("50000.00"),
        fixed_fee=Decimal("100.00"),
    )

    account.deposit(Decimal("10000.00"))
    account.withdraw(Decimal("20000.00"))

    print(account)

    try:
        account.withdraw(Decimal("50000.00"))
    except InsufficientFundsError as error:
        print(f"Expected error: {error}")


def demonstrate_investment_account():
    print("\n=== INVESTMENT ACCOUNT ===")

    account = InvestmentAccount(
        owner="David",
        currency=Currency.RUB,
    )

    account.deposit(Decimal("100000.00"))

    account.invest("stocks", Decimal("50000.00"))
    account.invest("bonds", Decimal("30000.00"))
    account.invest("etf", Decimal("20000.00"))

    growth_rates = {
        "stocks": Decimal("0.10"),
        "bonds": Decimal("0.04"),
        "etf": Decimal("0.07"),
    }

    expected_growth = account.project_yearly_growth(growth_rates)

    print(account)
    print(f"Projected yearly growth: {expected_growth} RUB")

    try:
        account.withdraw(Decimal("1000.00"))
    except InsufficientFundsError as error:
        print(f"Expected error: {error}")


def demonstrate_frozen_account():
    print("\n=== FROZEN ACCOUNT ===")

    account = BankAccount(
        owner="Frozen User",
        currency=Currency.USD,
        status=AccountStatus.FROZEN,
    )

    print(account)

    try:
        account.deposit(Decimal("100.00"))
    except AccountFrozenError as error:
        print(f"Expected error: {error}")


def demonstrate_polymorphism():
    print("\n=== POLYMORPHISM ===")

    accounts: list[BankAccount] = [
        BankAccount(owner="Alice"),
        SavingsAccount(owner="Bob"),
        PremiumAccount(owner="Charlie"),
        InvestmentAccount(owner="David"),
    ]

    for account in accounts:
        print(f"\nAccount type: {type(account).__name__}")
        print(account.get_account_info())
        print(account)


def main():
    demonstrate_bank_account()
    demonstrate_savings_account()
    demonstrate_premium_account()
    demonstrate_investment_account()
    demonstrate_frozen_account()
    demonstrate_polymorphism()


if __name__ == "__main__":
    main()
