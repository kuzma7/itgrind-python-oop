from decimal import Decimal

import pytest

from src.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)
from src.models import AccountStatus, Currency
from src.premium_account import PremiumAccount


@pytest.fixture
def premium_account():
    account = PremiumAccount(
        owner="Nikita",
        currency=Currency.RUB,
        withdrawal_limit=Decimal("10000.00"),
        overdraft_limit=Decimal("5000.00"),
        fixed_fee=Decimal("100.00"),
    )
    account.deposit(Decimal("1000.00"))
    return account


def test_create_premium_account(premium_account):
    assert premium_account.owner == "Nikita"
    assert premium_account.currency == Currency.RUB
    assert premium_account.account_status == AccountStatus.ACTIVE
    assert premium_account._balance == Decimal("1000.00")
    assert premium_account.withdrawal_limit == Decimal("10000.00")
    assert premium_account.overdraft_limit == Decimal("5000.00")
    assert premium_account.fixed_fee == Decimal("100.00")


def test_regular_withdrawal(premium_account):
    premium_account.withdraw(Decimal("500.00"))

    assert premium_account._balance == Decimal("400.00")


def test_withdrawal_with_overdraft(premium_account):
    premium_account.withdraw(Decimal("3000.00"))

    assert premium_account._balance == Decimal("-2100.00")


def test_exact_overdraft_boundary(premium_account):
    premium_account.withdraw(Decimal("5900.00"))

    assert premium_account._balance == Decimal("-5000.00")


def test_overdraft_limit_exceeded(premium_account):
    initial_balance = premium_account._balance

    with pytest.raises(InsufficientFundsError):
        premium_account.withdraw(Decimal("5900.01"))

    assert premium_account._balance == initial_balance


def test_withdrawal_limit_exceeded(premium_account):
    initial_balance = premium_account._balance

    with pytest.raises(InvalidOperationError):
        premium_account.withdraw(Decimal("10000.01"))

    assert premium_account._balance == initial_balance


def test_withdrawal_limit_boundary():
    account = PremiumAccount(
        owner="Nikita",
        withdrawal_limit=Decimal("10000.00"),
        overdraft_limit=Decimal("0.00"),
        fixed_fee=Decimal("100.00"),
    )
    account.deposit(Decimal("10100.00"))

    account.withdraw(Decimal("10000.00"))

    assert account._balance == Decimal("0.00")


def test_overdraft_repayment(premium_account):
    premium_account.withdraw(Decimal("3000.00"))
    premium_account.deposit(Decimal("3000.00"))

    assert premium_account._balance == Decimal("900.00")


def test_multiple_withdrawals(premium_account):
    premium_account.withdraw(Decimal("2000.00"))
    premium_account.withdraw(Decimal("3000.00"))

    assert premium_account._balance == Decimal("-4200.00")


def test_failed_second_withdrawal_preserves_balance(premium_account):
    premium_account.withdraw(Decimal("3000.00"))
    balance_after_first = premium_account._balance

    with pytest.raises(InsufficientFundsError):
        premium_account.withdraw(Decimal("3000.00"))

    assert premium_account._balance == balance_after_first


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("-100"),
        Decimal("0"),
        Decimal("NaN"),
        Decimal("Infinity"),
        "100",
        None,
        100,
    ],
)
def test_invalid_withdrawal_amount(premium_account, amount):
    initial_balance = premium_account._balance

    with pytest.raises(InvalidOperationError):
        premium_account.withdraw(amount)

    assert premium_account._balance == initial_balance


@pytest.mark.parametrize(
    "parameter, value",
    [
        ("withdrawal_limit", Decimal("0")),
        ("withdrawal_limit", Decimal("-100")),
        ("overdraft_limit", Decimal("-100")),
        ("fixed_fee", Decimal("-10")),
        ("withdrawal_limit", Decimal("NaN")),
        ("overdraft_limit", Decimal("Infinity")),
        ("fixed_fee", Decimal("NaN")),
        ("fixed_fee", "100"),
        ("overdraft_limit", None),
    ],
)
def test_invalid_premium_parameters(parameter, value):
    kwargs = {parameter: value}

    with pytest.raises(InvalidOperationError):
        PremiumAccount(owner="Nikita", **kwargs)


@pytest.mark.parametrize(
    "operation",
    ["deposit", "withdraw"],
)
def test_frozen_premium_account(operation):
    account = PremiumAccount(
        owner="Nikita",
        status=AccountStatus.FROZEN,
    )

    with pytest.raises(AccountFrozenError):
        getattr(account, operation)(Decimal("100.00"))

    assert account._balance == Decimal("0.00")


@pytest.mark.parametrize(
    "operation",
    ["deposit", "withdraw"],
)
def test_closed_premium_account(operation):
    account = PremiumAccount(
        owner="Nikita",
        status=AccountStatus.CLOSED,
    )

    with pytest.raises(AccountClosedError):
        getattr(account, operation)(Decimal("100.00"))

    assert account._balance == Decimal("0.00")


def test_zero_fee():
    account = PremiumAccount(
        owner="Nikita",
        fixed_fee=Decimal("0.00"),
        overdraft_limit=Decimal("0.00"),
    )
    account.deposit(Decimal("1000.00"))

    account.withdraw(Decimal("1000.00"))

    assert account._balance == Decimal("0.00")


def test_zero_overdraft():
    account = PremiumAccount(
        owner="Nikita",
        overdraft_limit=Decimal("0.00"),
        fixed_fee=Decimal("100.00"),
    )
    account.deposit(Decimal("1000.00"))

    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("1000.00"))

    assert account._balance == Decimal("1000.00")


def test_account_info(premium_account):
    info = premium_account.get_account_info()

    assert isinstance(info, dict)
    assert info["Owner"] == "Nikita"
    assert info["withdrawal_limit"] == Decimal("10000.00")
    assert info["overdraft_limit"] == Decimal("5000.00")
    assert info["fixed_fee"] == Decimal("100.00")


def test_string_representation(premium_account):
    result = str(premium_account)

    assert "PremiumAccount" in result
    assert "Nikita" in result
    assert "Withdrawal limit: 10000.00" in result
    assert "Overdraft limit: 5000.00" in result
    assert "Fixed fee: 100.00" in result
    assert "RUB" in result
