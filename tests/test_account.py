"""Basic account operations and restrictions."""
from decimal import Decimal

import pytest

from src.exceptions import AccountClosedError, AccountFrozenError, InsufficientFundsError, InvalidOperationError
from src.models import AccountStatus, BankAccount


def test_deposit_withdraw_and_spend_entire_balance():
    account = BankAccount("Ivan")
    account.deposit(Decimal("1000"))
    account.withdraw(Decimal("300"))
    assert account._balance == Decimal("700")
    account.withdraw(Decimal("700"))
    assert account._balance == 0


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")])
@pytest.mark.parametrize("operation", ["deposit", "withdraw"])
def test_invalid_amount_does_not_change_balance(operation, amount):
    account = BankAccount("Ivan")
    account.deposit(Decimal("100"))
    with pytest.raises(InvalidOperationError):
        getattr(account, operation)(amount)
    assert account._balance == Decimal("100")


def test_cannot_withdraw_more_than_available():
    account = BankAccount("Ivan")
    account.deposit(Decimal("100"))
    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("100.01"))
    assert account._balance == Decimal("100")


@pytest.mark.parametrize("status,error", [
    (AccountStatus.FROZEN, AccountFrozenError),
    (AccountStatus.CLOSED, AccountClosedError),
])
@pytest.mark.parametrize("operation", ["deposit", "withdraw"])
def test_inactive_account_cannot_move_money(status, error, operation):
    account = BankAccount("Ivan")
    account.deposit(Decimal("100"))
    account.account_status = status
    with pytest.raises(error):
        getattr(account, operation)(Decimal("10"))
    assert account._balance == Decimal("100")
