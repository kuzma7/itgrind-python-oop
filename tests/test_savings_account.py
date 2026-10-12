from decimal import Decimal

import pytest

from src.models import AccountStatus
from src.savings_account import SavingsAccount
from src.exceptions import (AccountFrozenError, InsufficientFundsError, InvalidOperationError)


@pytest.fixture
def savings_account():
    account = SavingsAccount(
        owner="Nikita",
        min_balance=Decimal("10000"),
        monthly_rate=Decimal("0.05"),
    )

    account.deposit(Decimal("15000"))
    return account


def test_withdraw_success(savings_account):
    savings_account.withdraw(Decimal("3000"))

    assert savings_account._balance == Decimal("12000")


def test_withdraw_exact_minimum(savings_account):
    savings_account.withdraw(Decimal("5000"))

    assert savings_account._balance == Decimal("10000")


def test_monthly_interest(savings_account):
    interest = savings_account.apply_monthly_interest()

    assert interest == Decimal("750.00")
    assert savings_account._balance == Decimal("15750.00")


def test_withdraw_below_minimum(savings_account):
    initial_balance = savings_account._balance

    with pytest.raises(InsufficientFundsError):
        savings_account.withdraw(Decimal("5000.01"))

    assert savings_account._balance == initial_balance


@pytest.mark.parametrize(
    "min_balance",
    [
        Decimal("-1000"),
        Decimal("NaN"),
        Decimal("Infinity"),
        "1000",
        None,
    ],
)
def test_invalid_min_balance(min_balance):
    with pytest.raises(InvalidOperationError):
        SavingsAccount(
            owner="Nikita",
            min_balance=min_balance,
            monthly_rate=Decimal("0.05"),
        )


@pytest.mark.parametrize(
    "monthly_rate",
    [
        Decimal("-0.05"),
        Decimal("NaN"),
        Decimal("Infinity"),
        "0.05",
        None,
    ],
)
def test_invalid_monthly_rate(monthly_rate):
    with pytest.raises(InvalidOperationError):
        SavingsAccount(
            owner="Nikita",
            min_balance=Decimal("10000"),
            monthly_rate=monthly_rate,
        )


def test_interest_compounding(savings_account):
    first_interest = savings_account.apply_monthly_interest()
    second_interest = savings_account.apply_monthly_interest()

    assert first_interest == Decimal("750.00")
    assert second_interest == Decimal("787.50")
    assert savings_account._balance == Decimal("16537.50")


def test_zero_interest():
    account = SavingsAccount(
        owner="Nikita",
        monthly_rate=Decimal("0.00"),
    )
    account.deposit(Decimal("10000.00"))

    interest = account.apply_monthly_interest()

    assert interest == Decimal("0.00")
    assert account._balance == Decimal("10000.00")


def test_frozen_interest():
    account = SavingsAccount(
        owner="Nikita",
        status=AccountStatus.FROZEN,
        monthly_rate=Decimal("0.05"),
    )

    with pytest.raises(AccountFrozenError):
        account.apply_monthly_interest()

    assert account._balance == Decimal("0.00")


def test_account_info(savings_account):
    info = savings_account.get_account_info()

    assert isinstance(info, dict)
    assert info["Owner"] == "Nikita"
    assert info["min_balance"] == Decimal("10000")
    assert info["monthly_rate"] == Decimal("0.05")


def test_string_representation(savings_account):
    result = str(savings_account)

    assert "SavingsAccount" in result
    assert "Nikita" in result
    assert "Min balance: 10000" in result
    assert "Monthly rate: 5" in result
