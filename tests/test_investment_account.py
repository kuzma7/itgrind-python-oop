from decimal import Decimal

import pytest

from src.exceptions import AccountClosedError, AccountFrozenError, InsufficientFundsError, InvalidOperationError
from src.investment_account import InvestmentAccount
from src.models import AccountStatus


def test_invest_in_all_supported_assets_and_add_to_existing_position():
    account = InvestmentAccount("Ivan")
    account.deposit(Decimal("100000"))
    account.invest("stocks", Decimal("40000"))
    account.invest("stocks", Decimal("10000"))
    account.invest("bonds", Decimal("30000"))
    account.invest("etf", Decimal("20000"))
    assert account._balance == 0
    assert account._portfolio == {
        "stocks": Decimal("50000"), "bonds": Decimal("30000"), "etf": Decimal("20000"),
    }
    info = account.get_account_info()
    assert info["portfolio_value"] == Decimal("100000")
    assert info["available_balance"] == 0


def test_clients_have_independent_portfolios():
    first = InvestmentAccount("Ivan")
    second = InvestmentAccount("Maria")
    first.deposit(Decimal("1000"))
    second.deposit(Decimal("1000"))
    first.invest("stocks", Decimal("500"))
    second.invest("stocks", Decimal("200"))
    assert first._portfolio["stocks"] == Decimal("500")
    assert second._portfolio["stocks"] == Decimal("200")
    assert first._balance == Decimal("500")
    assert second._balance == Decimal("800")


def test_invested_money_cannot_be_spent_or_invested_twice():
    account = InvestmentAccount("Ivan")
    account.deposit(Decimal("1000"))
    account.invest("stocks", Decimal("900"))
    for operation in (lambda: account.invest("bonds", Decimal("100.01")),
                      lambda: account.withdraw(Decimal("100.01"))):
        with pytest.raises(InsufficientFundsError):
            operation()
        assert account._balance == Decimal("100")
        assert account._portfolio == {
            "stocks": Decimal("900"), "bonds": Decimal("0"), "etf": Decimal("0"),
        }
    account.withdraw(Decimal("100"))
    assert account._balance == 0
    assert account._portfolio["stocks"] == Decimal("900")


def test_unsupported_asset_does_not_spend_money():
    account = InvestmentAccount("Ivan")
    account.deposit(Decimal("100"))
    with pytest.raises(InvalidOperationError, match="Unsupported asset type"):
        account.invest("crypto", Decimal("100"))
    assert account._balance == Decimal("100")
    assert sum(account._portfolio.values()) == 0


def test_growth_sums_asset_returns_without_changing_funds():
    account = InvestmentAccount("Ivan")
    account.deposit(Decimal("100000"))
    account.invest("stocks", Decimal("50000"))
    account.invest("bonds", Decimal("30000"))
    account.invest("etf", Decimal("20000"))
    portfolio_before = account._portfolio.copy()
    rates = {"stocks": Decimal("0.10"), "bonds": Decimal("0.04"), "etf": Decimal("0.07")}
    assert account.project_yearly_growth(rates) == Decimal("7600")
    assert account._portfolio == portfolio_before
    assert account._balance == 0


@pytest.mark.parametrize("investment,rate,expected", [
    ("0", "0.10", "0"),
    ("10000", "-0.10", "-1000"),
    ("100", "0.01235", "1.24"),
])
def test_growth_handles_empty_portfolio_losses_and_rounding(investment, rate, expected):
    account = InvestmentAccount("Ivan")
    if Decimal(investment) > 0:
        account.deposit(Decimal(investment))
        account.invest("stocks", Decimal(investment))
    rates = {"stocks": Decimal(rate), "bonds": Decimal("0.04"), "etf": Decimal("0.07")}
    assert account.project_yearly_growth(rates) == Decimal(expected)


@pytest.mark.parametrize("status,error", [
    (AccountStatus.FROZEN, AccountFrozenError),
    (AccountStatus.CLOSED, AccountClosedError),
])
@pytest.mark.parametrize("operation", ["invest", "project_yearly_growth"])
def test_inactive_investment_account_rejects_operations(status, error, operation):
    account = InvestmentAccount("Ivan")
    account.deposit(Decimal("100"))
    account.account_status = status
    with pytest.raises(error):
        if operation == "invest":
            account.invest("stocks", Decimal("100"))
        else:
            account.project_yearly_growth({
                "stocks": Decimal("0.1"), "bonds": Decimal("0"), "etf": Decimal("0"),
            })
    assert account._balance == Decimal("100")
    assert sum(account._portfolio.values()) == 0
