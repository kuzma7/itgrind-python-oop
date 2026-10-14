from datetime import datetime
from decimal import Decimal

from src.client import Client, ClientStatus
from src.exceptions import InvalidOperationError
from src.investment_account import InvestmentAccount
from src.models import BankAccount, AccountStatus, Currency


class Bank:
    def __init__(self, name: str):
        self.name = name
        self._clients: dict[str, Client] = {}
        self._accounts: dict[str, BankAccount] = {}
        self.suspicious_activities: list[str] = []

    def add_client(self, client: Client) -> None:
        if not isinstance(client, Client):
            raise InvalidOperationError("Expected Client instance")

        if client.client_id in self._clients:
            raise InvalidOperationError("Client already exists")

        self._clients[client.client_id] = client

    def open_account(self, client_id: str, account: BankAccount) -> None:
        self._validate_operation_time("open_account")
        if client_id not in self._clients:
            raise InvalidOperationError("Client not found")
        if self._clients[client_id].status is ClientStatus.BLOCKED:
            raise InvalidOperationError("Client is blocked")
        if not isinstance(account, BankAccount):
            raise InvalidOperationError("Invalid account")
        if account.uuid in self._accounts:
            raise InvalidOperationError("Account exist")
        if account.owner != self._clients[client_id].full_name:
            raise InvalidOperationError("Account owner does not match client")

        self._accounts[account.uuid] = account
        self._clients[client_id].account_ids.append(account.uuid)

    def freeze_account(self, account_id: str) -> None:
        self._validate_operation_time("freeze_account")
        if account_id not in self._accounts:
            raise InvalidOperationError("Account does not exist")
        account = self._accounts[account_id]
        if account.account_status is AccountStatus.FROZEN:
            raise InvalidOperationError("Account is already frozen")
        if account.account_status is AccountStatus.CLOSED:
            raise InvalidOperationError("Cannot freeze a closed account")

        account.account_status = AccountStatus.FROZEN

    def unfreeze_account(self, account_id: str) -> None:
        self._validate_operation_time("unfreeze_account")
        if account_id not in self._accounts:
            raise InvalidOperationError("Account does not exist")
        account = self._accounts[account_id]
        if account.account_status is AccountStatus.ACTIVE:
            raise InvalidOperationError("Account is already active")
        if account.account_status is AccountStatus.CLOSED:
            raise InvalidOperationError("Cannot unfreeze a closed account")

        account.account_status = AccountStatus.ACTIVE

    def close_account(self, account_id: str) -> None:
        self._validate_operation_time("close_account")
        if account_id not in self._accounts:
            raise InvalidOperationError("Account does not exist")
        account = self._accounts[account_id]
        if account.account_status is AccountStatus.CLOSED:
            raise InvalidOperationError("Account is already closed")
        if account.account_status is AccountStatus.FROZEN:
            raise InvalidOperationError("Cannot close a frozen account")
        if account._balance != Decimal("0.00"):
            raise InvalidOperationError("Account balance must be zero")
        if isinstance(account, InvestmentAccount):
            portfolio_total = sum(account._portfolio.values(), Decimal("0.00"), )
            if portfolio_total != Decimal("0.00"):
                raise InvalidOperationError("Investment portfolio is not empty")

        account.account_status = AccountStatus.CLOSED

    def authenticate_client(self, client_id: str, password: str) -> bool:
        if client_id not in self._clients:
            raise InvalidOperationError("Client not found")

        client = self._clients[client_id]

        if client.status is ClientStatus.BLOCKED:
            raise InvalidOperationError("Client is blocked")
        if client.verify_password(password):
            client.failed_login_attempts = 0
            return True
        client.failed_login_attempts += 1
        if client.failed_login_attempts >= 3:
            client.status = ClientStatus.BLOCKED
            self.suspicious_activities.append(f"Client {client_id}: 3 failed login attempts")
            raise InvalidOperationError("Client blocked after 3 failed login attempts")

        return False

    def search_accounts(self, client_id: str | None = None, status: AccountStatus | None = None) -> list[BankAccount]:
        if client_id is not None and client_id not in self._clients:
            raise InvalidOperationError("Client does not exist")
        if status is not None and not isinstance(status, AccountStatus):
            raise InvalidOperationError("Invalid account status")

        result = []

        for account in self._accounts.values():
            if status is not None and account.account_status is not status:
                continue
            if client_id is not None:
                client = self._clients[client_id]
                if account.uuid not in client.account_ids:
                    continue

            result.append(account)
        return result

    def _get_current_time(self) -> datetime:
        return datetime.now()

    def _validate_operation_time(self, operation: str) -> None:
        current_time = self._get_current_time()
        if 0 <= current_time.hour < 5:
            self.suspicious_activities.append(
                f"Restricted operation: {operation} at "
                f"{current_time.strftime('%H:%M')}"
            )
            raise InvalidOperationError("Bank operations are restricted from 00:00 to 05:00")

    def _get_account_total(self, account: BankAccount) -> Decimal:
        total = account._balance
        if isinstance(account, InvestmentAccount):
            total += sum(account._portfolio.values(), Decimal("0.00"))

        return total

    def get_total_balance(self) -> dict[Currency, Decimal]:
        totals: dict[Currency, Decimal] = {}
        for account in self._accounts.values():
            currency = account.currency
            amount = self._get_account_total(account)
            if currency not in totals:
                totals[currency] = Decimal("0.00")
            totals[currency] += amount

        return totals

    def get_clients_ranking(self, currency: Currency = Currency.RUB) -> list[tuple[Client, Decimal]]:
        if not isinstance(currency, Currency):
            raise InvalidOperationError("Invalid currency")
        ranking = []

        for client in self._clients.values():
            total = Decimal("0.00")
            for account_id in client.account_ids:
                account = self._accounts[account_id]
                if account.currency is currency:
                    total += self._get_account_total(account)
            ranking.append((client, total))
        ranking.sort(key=lambda item: item[1], reverse=True)
        return ranking
