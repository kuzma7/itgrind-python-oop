from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal

from src.client import Client, ClientStatus
from src.exceptions import InvalidOperationError
from src.investment_account import InvestmentAccount
from src.models import BankAccount, AccountStatus, Currency, _bank_operation_token


class Bank:
    def __init__(self, name: str):
        self.name = name
        self._clients: dict[str, Client] = {}
        self._accounts: dict[str, BankAccount] = {}
        self.suspicious_activities: list[str] = []
        self._operation_token = object()

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
            raise InvalidOperationError("Account already exists")
        client = self._clients[client_id]
        if account.owner != client.full_name:
            raise InvalidOperationError("Account owner does not match client")
        if account.account_status is not AccountStatus.ACTIVE:
            raise InvalidOperationError("Only active accounts can be opened")

        if account._bank_token is not None:
            raise InvalidOperationError("Account already belongs to a bank")
        self._accounts[account.uuid] = account
        client.account_ids.append(account.uuid)
        account._bank_token = self._operation_token

    def _validate_account_access(self, client_id: str, account_id: str, operation: str) -> BankAccount:
        self._validate_operation_time(operation)
        if client_id not in self._clients:
            raise InvalidOperationError("Client not found")
        client = self._clients[client_id]
        if client.status is ClientStatus.BLOCKED:
            raise InvalidOperationError("Client is blocked")
        if account_id not in self._accounts or account_id not in client.account_ids:
            raise InvalidOperationError("Account not found or does not belong to client")
        return self._accounts[account_id]

    @contextmanager
    def _authorize_account_operation(self):
        token = _bank_operation_token.set(self._operation_token)
        try:
            yield
        finally:
            _bank_operation_token.reset(token)

    def deposit(self, client_id: str, account_id: str, amount: Decimal) -> None:
        account = self._validate_account_access(client_id, account_id, "deposit")
        with self._authorize_account_operation():
            account.deposit(amount)

    def withdraw(self, client_id: str, account_id: str, amount: Decimal) -> None:
        account = self._validate_account_access(client_id, account_id, "withdraw")
        with self._authorize_account_operation():
            account.withdraw(amount)

    def invest(self, client_id: str, account_id: str, asset_type: str, amount: Decimal) -> None:
        account = self._validate_account_access(client_id, account_id, "invest")
        if not isinstance(account, InvestmentAccount):
            raise InvalidOperationError("Investment operations require InvestmentAccount")
        with self._authorize_account_operation():
            account.invest(asset_type, amount)

    def project_yearly_growth(self, client_id: str, account_id: str, growth_rates: dict[str, Decimal]) -> Decimal:
        account = self._validate_account_access(client_id, account_id, "project_yearly_growth")
        if not isinstance(account, InvestmentAccount):
            raise InvalidOperationError("Growth projection requires InvestmentAccount")
        with self._authorize_account_operation():
            return account.project_yearly_growth(growth_rates)

    def apply_monthly_interest(self, client_id: str, account_id: str) -> Decimal:
        from src.savings_account import SavingsAccount
        account = self._validate_account_access(client_id, account_id, "apply_monthly_interest")
        if not isinstance(account, SavingsAccount):
            raise InvalidOperationError("Interest operation requires SavingsAccount")
        with self._authorize_account_operation():
            return account.apply_monthly_interest()

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
            portfolio_total = sum(account._portfolio.values(), Decimal("0.00"))
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
            self.suspicious_activities.append(
                f"Client {client_id}: 3 failed login attempts"
            )
            raise InvalidOperationError(
                "Client blocked after 3 failed login attempts"
            )

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
