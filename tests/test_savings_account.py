"""Savings minimum balance and interest accrual."""
from decimal import Decimal

import pytest

from src.exceptions import AccountClosedError, AccountFrozenError, InsufficientFundsError
from src.models import AccountStatus
from src.savings_account import SavingsAccount


def test_withdraw_up_to_minimum_and_reject_exceeding_it():
    account = SavingsAccount("Ivan", min_balance=Decimal("10000"))
    account.deposit(Decimal("15000"))
    account.withdraw(Decimal("3000"))
    assert account._balance == Decimal("12000")
    account.withdraw(Decimal("2000"))
    assert account._balance == Decimal("10000")
    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("0.01"))
    assert account._balance == Decimal("10000")


def test_monthly_interest_is_credited_and_compounds():
    account = SavingsAccount("Ivan", monthly_rate=Decimal("0.05"))
    account.deposit(Decimal("15000"))
    assert account.apply_monthly_interest() == Decimal("750.00")
    assert account._balance == Decimal("15750.00")
    assert account.apply_monthly_interest() == Decimal("787.50")
    assert account._balance == Decimal("16537.50")


def test_zero_rate_does_not_change_balance():
    account = SavingsAccount("Ivan", monthly_rate=Decimal("0"))
    account.deposit(Decimal("10000"))
    assert account.apply_monthly_interest() == 0
    assert account._balance == Decimal("10000")


@pytest.mark.parametrize("status,error", [
    (AccountStatus.FROZEN, AccountFrozenError),
    (AccountStatus.CLOSED, AccountClosedError),
])
def test_inactive_savings_account_cannot_accrue_interest(status, error):
    account = SavingsAccount("Ivan")
    account.deposit(Decimal("10000"))
    account.account_status = status
    with pytest.raises(error):
        account.apply_monthly_interest()
    assert account._balance == Decimal("10000")
