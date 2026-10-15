"""Premium fees, withdrawal limits and overdraft."""
from decimal import Decimal

import pytest

from src.exceptions import AccountClosedError, AccountFrozenError, InsufficientFundsError, InvalidOperationError
from src.models import AccountStatus
from src.premium_account import PremiumAccount


def test_each_withdrawal_charges_fee_and_deposit_repays_overdraft():
    account = PremiumAccount("Ivan", fixed_fee=Decimal("100"))
    account.deposit(Decimal("1000"))
    account.withdraw(Decimal("500"))
    assert account._balance == Decimal("400")
    account.withdraw(Decimal("1000"))
    assert account._balance == Decimal("-700")
    account.deposit(Decimal("1000"))
    assert account._balance == Decimal("300")


def test_overdraft_includes_fee_and_cannot_exceed_limit():
    account = PremiumAccount("Ivan", overdraft_limit=Decimal("5000"), fixed_fee=Decimal("100"))
    account.deposit(Decimal("1000"))
    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("5900.01"))
    assert account._balance == Decimal("1000")
    account.withdraw(Decimal("5900"))
    assert account._balance == Decimal("-5000")
    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("0.01"))
    assert account._balance == Decimal("-5000")


def test_withdrawal_limit_boundary():
    account = PremiumAccount("Ivan", withdrawal_limit=Decimal("10000"), fixed_fee=Decimal("100"))
    account.deposit(Decimal("20000"))
    with pytest.raises(InvalidOperationError, match="Withdrawal limit exceeded"):
        account.withdraw(Decimal("10000.01"))
    assert account._balance == Decimal("20000")
    account.withdraw(Decimal("10000"))
    assert account._balance == Decimal("9900")


def test_zero_overdraft_does_not_allow_spending_fee_from_credit():
    account = PremiumAccount("Ivan", overdraft_limit=Decimal("0"), fixed_fee=Decimal("100"))
    account.deposit(Decimal("1000"))
    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("1000"))
    assert account._balance == Decimal("1000")


def test_zero_fee_allows_spending_entire_balance():
    account = PremiumAccount("Ivan", overdraft_limit=Decimal("0"), fixed_fee=Decimal("0"))
    account.deposit(Decimal("1000"))
    account.withdraw(Decimal("1000"))
    assert account._balance == 0


@pytest.mark.parametrize("status,error", [
    (AccountStatus.FROZEN, AccountFrozenError),
    (AccountStatus.CLOSED, AccountClosedError),
])
def test_inactive_premium_cannot_use_overdraft(status, error):
    account = PremiumAccount("Ivan", status=status)
    with pytest.raises(error):
        account.withdraw(Decimal("100"))
    assert account._balance == 0
