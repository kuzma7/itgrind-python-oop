from decimal import Decimal

import pytest

from src.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)
from src.investment_account import InvestmentAccount
from src.models import AccountStatus, Currency


@pytest.fixture
def account():
    investment_account = InvestmentAccount(
        owner="Nikita",
        currency=Currency.RUB,
    )
    investment_account.deposit(Decimal("100000.00"))
    return investment_account


@pytest.fixture
def growth_rates():
    return {
        "stocks": Decimal("0.10"),
        "bonds": Decimal("0.04"),
        "etf": Decimal("0.07"),
    }


# === ACCOUNT CREATION ===

def test_account_creation(account):
    assert account.owner == "Nikita"
    assert account.currency == Currency.RUB
    assert account.account_status == AccountStatus.ACTIVE
    assert account._balance == Decimal("100000.00")


def test_initial_portfolio(account):
    assert account._portfolio == {
        "stocks": Decimal("0.00"),
        "bonds": Decimal("0.00"),
        "etf": Decimal("0.00"),
    }


def test_independent_portfolios():
    first = InvestmentAccount(owner="Alice")
    second = InvestmentAccount(owner="Bob")

    first.deposit(Decimal("1000.00"))
    first.invest("stocks", Decimal("500.00"))

    assert first._portfolio["stocks"] == Decimal("500.00")
    assert second._portfolio["stocks"] == Decimal("0.00")


# === INVESTMENTS ===

@pytest.mark.parametrize(
    "asset_type",
    ["stocks", "bonds", "etf"],
)
def test_invest_supported_assets(account, asset_type):
    account.invest(asset_type, Decimal("10000.00"))

    assert account._portfolio[asset_type] == Decimal("10000.00")
    assert account._balance == Decimal("90000.00")


def test_invest_multiple_assets(account):
    account.invest("stocks", Decimal("50000.00"))
    account.invest("bonds", Decimal("30000.00"))
    account.invest("etf", Decimal("20000.00"))

    assert account._portfolio == {
        "stocks": Decimal("50000.00"),
        "bonds": Decimal("30000.00"),
        "etf": Decimal("20000.00"),
    }
    assert account._balance == Decimal("0.00")


def test_repeated_investments(account):
    account.invest("stocks", Decimal("10000.00"))
    account.invest("stocks", Decimal("15000.00"))

    assert account._portfolio["stocks"] == Decimal("25000.00")
    assert account._balance == Decimal("75000.00")


def test_invest_exact_balance(account):
    account.invest("stocks", Decimal("100000.00"))

    assert account._balance == Decimal("0.00")
    assert account._portfolio["stocks"] == Decimal("100000.00")


def test_invest_insufficient_funds(account):
    initial_balance = account._balance
    initial_portfolio = account._portfolio.copy()

    with pytest.raises(InsufficientFundsError):
        account.invest("stocks", Decimal("100000.01"))

    assert account._balance == initial_balance
    assert account._portfolio == initial_portfolio


@pytest.mark.parametrize(
    "asset_type",
    ["crypto", "gold", "STOCKS", "", None, 123, ["stocks"]],
)
def test_invalid_asset_type(account, asset_type):
    with pytest.raises(InvalidOperationError):
        account.invest(asset_type, Decimal("100.00"))

    assert account._balance == Decimal("100000.00")
    assert all(value == 0 for value in account._portfolio.values())


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        "100",
        100,
        None,
    ],
)
def test_invalid_investment_amount(account, amount):
    with pytest.raises(InvalidOperationError):
        account.invest("stocks", amount)

    assert account._balance == Decimal("100000.00")
    assert account._portfolio["stocks"] == Decimal("0.00")


def test_total_funds_preserved(account):
    initial_total = account._balance + sum(account._portfolio.values())

    account.invest("stocks", Decimal("25000.00"))
    account.invest("bonds", Decimal("15000.00"))

    final_total = account._balance + sum(account._portfolio.values())

    assert final_total == initial_total


# === WITHDRAWALS ===

def test_withdraw_available_funds(account):
    account.invest("stocks", Decimal("70000.00"))
    account.withdraw(Decimal("10000.00"))

    assert account._balance == Decimal("20000.00")
    assert account._portfolio["stocks"] == Decimal("70000.00")


def test_cannot_withdraw_invested_funds(account):
    account.invest("stocks", Decimal("90000.00"))

    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("20000.00"))

    assert account._balance == Decimal("10000.00")
    assert account._portfolio["stocks"] == Decimal("90000.00")


# === YEARLY GROWTH ===

def test_project_yearly_growth(account, growth_rates):
    account.invest("stocks", Decimal("50000.00"))
    account.invest("bonds", Decimal("30000.00"))
    account.invest("etf", Decimal("20000.00"))

    result = account.project_yearly_growth(growth_rates)

    assert result == Decimal("7600.00")


def test_growth_does_not_change_account(account, growth_rates):
    account.invest("stocks", Decimal("40000.00"))

    balance_before = account._balance
    portfolio_before = account._portfolio.copy()

    account.project_yearly_growth(growth_rates)

    assert account._balance == balance_before
    assert account._portfolio == portfolio_before


def test_empty_portfolio_growth(account, growth_rates):
    result = account.project_yearly_growth(growth_rates)

    assert result == Decimal("0.00")


def test_negative_growth(account, growth_rates):
    account.invest("stocks", Decimal("10000.00"))
    growth_rates["stocks"] = Decimal("-0.10")

    assert account.project_yearly_growth(growth_rates) == Decimal("-1000.00")


def test_growth_rounding(account):
    account.invest("stocks", Decimal("100.00"))

    rates = {
        "stocks": Decimal("0.01235"),
        "bonds": Decimal("0.04"),
        "etf": Decimal("0.07"),
    }

    assert account.project_yearly_growth(rates) == Decimal("1.24")


def test_missing_growth_rate(account, growth_rates):
    del growth_rates["etf"]

    with pytest.raises(InvalidOperationError):
        account.project_yearly_growth(growth_rates)


@pytest.mark.parametrize(
    "invalid_rate",
    [
        "0.10",
        None,
        0.10,
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_invalid_growth_rate(account, growth_rates, invalid_rate):
    growth_rates["stocks"] = invalid_rate

    with pytest.raises(InvalidOperationError):
        account.project_yearly_growth(growth_rates)


@pytest.mark.parametrize(
    "rates",
    [
        None,
        "stocks",
        [],
        123,
    ],
)
def test_invalid_growth_rates_container(account, rates):
    with pytest.raises(InvalidOperationError):
        account.project_yearly_growth(rates)


# === ACCOUNT STATUS ===

@pytest.mark.parametrize(
    "status, expected_error",
    [
        (AccountStatus.FROZEN, AccountFrozenError),
        (AccountStatus.CLOSED, AccountClosedError),
    ],
)
def test_invest_in_inactive_account(status, expected_error):
    inactive_account = InvestmentAccount(
        owner="Nikita",
        status=status,
    )

    with pytest.raises(expected_error):
        inactive_account.invest("stocks", Decimal("100.00"))

    assert inactive_account._portfolio["stocks"] == Decimal("0.00")


@pytest.mark.parametrize(
    "status, expected_error",
    [
        (AccountStatus.FROZEN, AccountFrozenError),
        (AccountStatus.CLOSED, AccountClosedError),
    ],
)
def test_growth_in_inactive_account(status, expected_error, growth_rates):
    inactive_account = InvestmentAccount(
        owner="Nikita",
        status=status,
    )

    with pytest.raises(expected_error):
        inactive_account.project_yearly_growth(growth_rates)


@pytest.mark.parametrize(
    "status, expected_error",
    [
        (AccountStatus.FROZEN, AccountFrozenError),
        (AccountStatus.CLOSED, AccountClosedError),
    ],
)
def test_withdraw_from_inactive_account(status, expected_error):
    inactive_account = InvestmentAccount(
        owner="Nikita",
        status=status,
    )

    with pytest.raises(expected_error):
        inactive_account.withdraw(Decimal("100.00"))


# === ACCOUNT INFORMATION ===

def test_get_account_info(account):
    account.invest("stocks", Decimal("30000.00"))

    info = account.get_account_info()

    assert info["Owner"] == "Nikita"
    assert info["portfolio"]["stocks"] == Decimal("30000.00")
    assert info["portfolio_value"] == Decimal("30000.00")
    assert info["available_balance"] == Decimal("70000.00")


def test_account_info_returns_portfolio_copy(account):
    info = account.get_account_info()

    info["portfolio"]["stocks"] = Decimal("999999.00")

    assert account._portfolio["stocks"] == Decimal("0.00")


def test_string_representation(account):
    account.invest("stocks", Decimal("30000.00"))

    result = str(account)

    assert "InvestmentAccount" in result
    assert "Nikita" in result
    assert "Stocks: 30000.00" in result
    assert "Bonds: 0.00" in result
    assert "ETF: 0.00" in result
    assert "Portfolio value: 30000.00 RUB" in result
