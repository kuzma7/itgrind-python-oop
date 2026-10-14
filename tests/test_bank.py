"""Functional scenarios for Day 3 Bank system."""
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.bank import Bank
from src.client import Client, ClientStatus
from src.exceptions import AccountFrozenError, InvalidOperationError
from src.investment_account import InvestmentAccount
from src.models import AccountStatus, BankAccount, Currency
from src.premium_account import PremiumAccount
from src.savings_account import SavingsAccount


@pytest.fixture
def bank():
    bank = Bank("ItGrind Bank")
    # Admin operations work deterministically regardless of when tests run.
    with patch.object(bank, "_get_current_time", return_value=datetime(2026, 10, 15, 12, 0)):
        yield bank


def register(bank, name="Ivan Ivanov", password="secret"):
    client = Client(name, date(2000, 5, 15), {"email": "user@example.com"}, password)
    bank.add_client(client)
    return client


def test_register_client_and_reject_duplicate(bank):
    client = register(bank)
    assert bank._clients[client.client_id] is client
    with pytest.raises(InvalidOperationError, match="already exists"):
        bank.add_client(client)


def test_client_must_be_adult():
    with pytest.raises(InvalidOperationError, match="at least 18"):
        Client("Young Client", date.today(), {"phone": "+79990000000"}, "secret")


def test_open_multiple_account_types_and_search(bank):
    ivan = register(bank)
    maria = register(bank, "Maria Petrova")
    standard = BankAccount(owner=ivan.full_name)
    savings = SavingsAccount(owner=ivan.full_name)
    investment = InvestmentAccount(owner=maria.full_name)
    for client, account in [(ivan, standard), (ivan, savings), (maria, investment)]:
        bank.open_account(client.client_id, account)

    assert ivan.account_ids == [standard.uuid, savings.uuid]
    assert bank.search_accounts(client_id=ivan.client_id) == [standard, savings]
    assert bank.search_accounts(client_id=maria.client_id) == [investment]
    assert len(bank.search_accounts()) == 3


def test_open_account_rejects_wrong_owner_and_unknown_client(bank):
    client = register(bank)
    with pytest.raises(InvalidOperationError, match="owner"):
        bank.open_account(client.client_id, BankAccount(owner="Another Person"))
    with pytest.raises(InvalidOperationError, match="not found"):
        bank.open_account("missing", BankAccount(owner=client.full_name))
    assert client.account_ids == []


def test_freeze_unfreeze_and_search_status(bank):
    client = register(bank)
    account = BankAccount(owner=client.full_name)
    bank.open_account(client.client_id, account)
    bank.freeze_account(account.uuid)
    assert account.account_status is AccountStatus.FROZEN
    assert bank.search_accounts(status=AccountStatus.FROZEN) == [account]
    with pytest.raises(AccountFrozenError):
        account.deposit(Decimal("100"))
    bank.unfreeze_account(account.uuid)
    account.deposit(Decimal("100"))
    assert account._balance == Decimal("100")


def test_close_account_only_when_empty_and_keep_history(bank):
    client = register(bank)
    account = BankAccount(owner=client.full_name)
    bank.open_account(client.client_id, account)
    account.deposit(Decimal("100"))
    with pytest.raises(InvalidOperationError, match="balance must be zero"):
        bank.close_account(account.uuid)
    account.withdraw(Decimal("100"))
    bank.close_account(account.uuid)
    assert account.account_status is AccountStatus.CLOSED
    assert bank.search_accounts(status=AccountStatus.CLOSED) == [account]
    with pytest.raises(InvalidOperationError, match="already closed"):
        bank.close_account(account.uuid)


def test_cannot_close_investment_with_portfolio(bank):
    client = register(bank)
    account = InvestmentAccount(owner=client.full_name)
    bank.open_account(client.client_id, account)
    account.deposit(Decimal("1000"))
    account.invest("stocks", Decimal("1000"))
    assert account._balance == 0
    with pytest.raises(InvalidOperationError, match="portfolio is not empty"):
        bank.close_account(account.uuid)


def test_authentication_reset_and_lockout_is_logged(bank):
    client = register(bank)
    assert bank.authenticate_client(client.client_id, "wrong") is False
    assert bank.authenticate_client(client.client_id, "secret") is True
    assert client.failed_login_attempts == 0
    assert bank.authenticate_client(client.client_id, "wrong") is False
    assert bank.authenticate_client(client.client_id, "wrong") is False
    with pytest.raises(InvalidOperationError, match="blocked after 3"):
        bank.authenticate_client(client.client_id, "wrong")
    assert client.status is ClientStatus.BLOCKED
    assert len(bank.suspicious_activities) == 1
    with pytest.raises(InvalidOperationError, match="blocked"):
        bank.authenticate_client(client.client_id, "secret")


def test_blocked_client_cannot_open_account(bank):
    client = register(bank)
    for _ in range(2):
        bank.authenticate_client(client.client_id, "wrong")
    with pytest.raises(InvalidOperationError):
        bank.authenticate_client(client.client_id, "wrong")
    with pytest.raises(InvalidOperationError, match="blocked"):
        bank.open_account(client.client_id, BankAccount(owner=client.full_name))


def test_night_restriction_and_morning_boundary(bank):
    client = register(bank)
    account = BankAccount(owner=client.full_name)
    with patch.object(bank, "_get_current_time", return_value=datetime(2026, 10, 15, 4, 59)):
        with pytest.raises(InvalidOperationError, match="00:00 to 05:00"):
            bank.open_account(client.client_id, account)
    assert bank.search_accounts() == []
    assert len(bank.suspicious_activities) == 1
    with patch.object(bank, "_get_current_time", return_value=datetime(2026, 10, 15, 5, 0)):
        bank.open_account(client.client_id, account)
    assert bank.search_accounts() == [account]


def test_totals_and_ranking_multiple_currencies(bank):
    ivan = register(bank)
    maria = register(bank, "Maria Petrova")

    standard = BankAccount(owner=ivan.full_name, currency=Currency.RUB)
    standard.deposit(Decimal("10000"))
    bank.open_account(ivan.client_id, standard)

    premium = PremiumAccount(owner=ivan.full_name, currency=Currency.RUB)
    premium.withdraw(Decimal("4900"))  # 4900 + 100 fee => -5000
    bank.open_account(ivan.client_id, premium)

    investment = InvestmentAccount(owner=maria.full_name, currency=Currency.RUB)
    investment.deposit(Decimal("20000"))
    investment.invest("stocks", Decimal("15000"))
    bank.open_account(maria.client_id, investment)

    usd = BankAccount(owner=maria.full_name, currency=Currency.USD)
    usd.deposit(Decimal("200"))
    bank.open_account(maria.client_id, usd)

    assert bank.get_total_balance() == {
        Currency.RUB: Decimal("25000"),
        Currency.USD: Decimal("200"),
    }
    assert bank.get_clients_ranking(Currency.RUB) == [
        (maria, Decimal("20000")),
        (ivan, Decimal("5000")),
    ]
    assert bank.get_clients_ranking(Currency.USD) == [
        (maria, Decimal("200")),
        (ivan, Decimal("0")),
    ]
