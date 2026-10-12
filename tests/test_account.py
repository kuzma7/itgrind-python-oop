from decimal import Decimal

import pytest

from src.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)
from src.models import AccountStatus, BankAccount, Currency


@pytest.fixture
def account():
    return BankAccount(owner="Nikita", currency=Currency.RUB)


def test_create_account(account):
    assert account.owner == "Nikita"
    assert account.account_status == AccountStatus.ACTIVE
    assert account.currency == Currency.RUB
    assert account._balance == Decimal("0.00")


def test_auto_generated_account_id(account):
    assert isinstance(account.uuid, str)
    assert len(account.uuid) == 8


def test_custom_account_id():
    account = BankAccount(owner="Nikita", account_id="12345678")
    assert account.uuid == "12345678"


def test_deposit(account):
    account.deposit(Decimal("500.00"))
    assert account._balance == Decimal("500.00")


def test_withdraw(account):
    account.deposit(Decimal("1000.00"))
    account.withdraw(Decimal("300.00"))

    assert account._balance == Decimal("700.00")


def test_withdraw_entire_balance(account):
    account.deposit(Decimal("100.00"))
    account.withdraw(Decimal("100.00"))

    assert account._balance == Decimal("0.00")


@pytest.mark.parametrize("amount", [
    Decimal("-100"),
    Decimal("0"),
    Decimal("NaN"),
    Decimal("Infinity"),
    "100",
    None,
    100,
])
def test_invalid_deposit(account, amount):
    with pytest.raises(InvalidOperationError):
        account.deposit(amount)


@pytest.mark.parametrize("amount", [
    Decimal("-100"),
    Decimal("0"),
    Decimal("NaN"),
    Decimal("Infinity"),
    "100",
    None,
    100,
])
def test_invalid_withdraw(account, amount):
    account.deposit(Decimal("500.00"))

    with pytest.raises(InvalidOperationError):
        account.withdraw(amount)


def test_insufficient_funds(account):
    account.deposit(Decimal("100.00"))

    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("150.00"))

    assert account._balance == Decimal("100.00")


@pytest.mark.parametrize("operation", ["deposit", "withdraw"])
def test_frozen_account(operation):
    account = BankAccount(
        owner="Nikita",
        status=AccountStatus.FROZEN,
    )

    with pytest.raises(AccountFrozenError):
        getattr(account, operation)(Decimal("100.00"))

    assert account._balance == Decimal("0.00")


@pytest.mark.parametrize("operation", ["deposit", "withdraw"])
def test_closed_account(operation):
    account = BankAccount(
        owner="Nikita",
        status=AccountStatus.CLOSED,
    )

    with pytest.raises(AccountClosedError):
        getattr(account, operation)(Decimal("100.00"))


@pytest.mark.parametrize("owner", ["", "   ", None, 123])
def test_invalid_owner(owner):
    with pytest.raises(InvalidOperationError):
        BankAccount(owner=owner)


def test_invalid_currency():
    with pytest.raises(InvalidOperationError):
        BankAccount(owner="Nikita", currency="BTC")


def test_account_string(account):
    result = str(account)

    assert "BankAccount" in result
    assert "Nikita" in result
    assert account.uuid[-4:] in result
    assert "active" in result
    assert "RUB" in result
    assert "0.00" in result
