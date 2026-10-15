from contextlib import contextmanager
from datetime import datetime, timezone, tzinfo
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable

from src.audit_log import AuditLog
from src.client import Client, ClientStatus
from src.exceptions import BankOperationRestrictedError, InvalidOperationError, RiskBlockedError
from src.investment_account import InvestmentAccount
from src.models import (
    BankAccount, AccountStatus, Currency, DEFAULT_BANK_TIMEZONE,
    EXCHANGE_RATES_IN_RUB, _bank_operation_token, validate_money_precision,
)
from src.premium_account import PremiumAccount
from src.risk_analyzer import RiskAnalyzer
from src.transaction import Transaction, TransactionStatus, TransactionType


class Bank:
    def __init__(
            self,
            name: str,
            clock: Callable[[], datetime] | None = None,
            bank_timezone: tzinfo = DEFAULT_BANK_TIMEZONE,
            audit_log: AuditLog | None = None,
            risk_analyzer: RiskAnalyzer | None = None,
    ):
        self.name = name
        self.clock = clock if clock is not None else lambda: datetime.now(timezone.utc)
        self.bank_timezone = bank_timezone
        self.audit_log = audit_log
        self.risk_analyzer = risk_analyzer
        if self.risk_analyzer is not None:
            self.risk_analyzer.bank_timezone = bank_timezone
        self._clients: dict[str, Client] = {}
        self._accounts: dict[str, BankAccount] = {}
        self.suspicious_activities: list[str] = []
        self._operation_token = object()
        self._transaction_results: dict[str, dict] = {}
        self.transaction_errors: list[dict] = []

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

    def _validate_account_access(
            self, client_id: str, account_id: str, operation: str, now: datetime | None = None,
            *, check_time: bool = True,
    ) -> BankAccount:
        if check_time:
            self._validate_operation_time(operation, now)
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
        self._execute_immediate_transaction(TransactionType.DEPOSIT, client_id, account_id, amount)

    def withdraw(self, client_id: str, account_id: str, amount: Decimal) -> None:
        self._execute_immediate_transaction(TransactionType.WITHDRAWAL, client_id, account_id, amount)

    def _execute_immediate_transaction(
        self, operation: TransactionType, client_id: str, account_id: str, amount: Decimal,
    ) -> None:
        now = self._get_current_time()
        transaction = Transaction(
            operation, client_id, amount, self.get_account_currency(account_id),
            sender_id=account_id if operation is TransactionType.WITHDRAWAL else None,
            recipient_id=account_id if operation is TransactionType.DEPOSIT else None,
        )
        transaction.created_at = transaction.started_at = transaction.last_attempt_at = now
        transaction.status = TransactionStatus.PROCESSING
        transaction.attempts = 1
        try:
            result = self.execute_transaction(transaction, now=now)
        except Exception as error:
            if isinstance(error, BankOperationRestrictedError):
                transaction.attempts = 0
            self.record_transaction_error(transaction, error, now)
            result = self.get_transaction_result(transaction.id)
            if result is None:
                transaction.status = TransactionStatus.FAILED
                transaction.completed_at = now
                raise
            # A reporting error after commit must not invite a second debit.
        for field, value in result.items():
            setattr(transaction, field, value)
        transaction.status = TransactionStatus.COMPLETED
        transaction.failure_reason = None
        transaction.completed_at = now

    def get_account_currency(self, account_id: str) -> Currency:
        if account_id not in self._accounts:
            raise InvalidOperationError("Account not found")
        return self._accounts[account_id].currency

    def get_transaction_result(self, transaction_id: str) -> dict | None:
        result = self._transaction_results.get(transaction_id)
        return result.copy() if result is not None else None

    def _audit_transaction(
        self, transaction: Transaction, now: datetime, level: str, event: str, message: str, details: dict,
    ) -> None:
        if self.audit_log is not None:
            self.audit_log.record(
                level, event, message, client_id=transaction.client_id,
                transaction_id=transaction.id, details=details, timestamp=now,
            )

    def record_transaction_error(self, transaction: Transaction, error: Exception, now: datetime) -> list[dict]:
        entry = {
            "transaction_id": transaction.id, "attempt": transaction.attempts, "timestamp": now,
            "error_type": type(error).__name__, "reason": str(error),
        }
        transaction.failure_reason = str(error)
        transaction.errors.append(entry.copy())
        self.transaction_errors.append(entry.copy())
        recorded = [entry]
        if self.audit_log is None or isinstance(error, RiskBlockedError):
            return recorded
        deferred = isinstance(error, BankOperationRestrictedError)
        try:
            self._audit_transaction(
                transaction, now, "WARNING" if deferred else "ERROR",
                "transaction_deferred" if deferred else "transaction_error", str(error),
                {"error_type": type(error).__name__, "attempt": transaction.attempts,
                 "amount": transaction.amount, "currency": transaction.currency},
            )
        except OSError as audit_error:
            failure = {**entry, "error_type": type(audit_error).__name__,
                       "reason": f"Audit write failed: {audit_error}"}
            transaction.errors.append(failure.copy())
            self.transaction_errors.append(failure.copy())
            recorded.append(failure)
        return recorded

    def _check_transaction_risk(self, transaction: Transaction, now: datetime) -> None:
        if self.risk_analyzer is None or transaction.transaction_type is TransactionType.DEPOSIT:
            return
        amount_in_rub = transaction.amount * EXCHANGE_RATES_IN_RUB[transaction.currency]
        risk = self.risk_analyzer.analyze(transaction, now, amount_in_rub)
        details = {
            "risk_level": risk["level"], "score": risk["score"], "reasons": risk["reasons"],
            "amount": transaction.amount, "currency": transaction.currency,
            "amount_in_rub": amount_in_rub,
        }
        self._audit_transaction(
            transaction, now, "INFO" if risk["level"] == "LOW" else "WARNING",
            "risk_analyzed", "Transaction risk evaluated", details,
        )
        if risk["level"] == "HIGH":
            self._audit_transaction(
                transaction, now, "WARNING", "transaction_blocked",
                "Transaction blocked by risk rules", details,
            )
            raise RiskBlockedError("Transaction blocked by risk rules: " + ", ".join(risk["reasons"]))

    def execute_transaction(
            self,
            transaction: Transaction,
            external_fee: Decimal = Decimal("0.00"),
            exchange_rate: Decimal = Decimal("1"),
            *,
            now: datetime | None = None,
            external_send: Callable[[Transaction, Decimal], dict] | None = None,
    ) -> dict:
        if not isinstance(transaction, Transaction):
            raise InvalidOperationError("Expected Transaction instance")
        if transaction.status is not TransactionStatus.PROCESSING:
            raise InvalidOperationError("Transaction must be processing")
        if transaction.id in self._transaction_results:
            return self._transaction_results[transaction.id].copy()
        now = now if now is not None else self._get_current_time()
        if not isinstance(external_fee, Decimal) or not external_fee.is_finite() or external_fee < 0:
            raise InvalidOperationError("Invalid external fee")
        validate_money_precision(external_fee)
        if not isinstance(exchange_rate, Decimal) or not exchange_rate.is_finite() or exchange_rate <= 0:
            raise InvalidOperationError("Invalid exchange rate")
        if not isinstance(transaction.transaction_type, TransactionType):
            raise InvalidOperationError("Invalid transaction type")

        is_transfer = transaction.transaction_type is TransactionType.TRANSFER
        if not is_transfer and external_fee != 0:
            raise InvalidOperationError("Only transfers can have an external fee")
        if not transaction.is_external and external_fee != 0:
            raise InvalidOperationError("Internal operations cannot have an external fee")
        account_id = (
            transaction.recipient_id if transaction.transaction_type is TransactionType.DEPOSIT
            else transaction.sender_id
        )
        account = self._validate_account_access(
            transaction.client_id, account_id, "transaction", now, check_time=False,
        )
        if account.currency is not transaction.currency:
            raise InvalidOperationError("Transaction currency must match account currency")
        account._validate_amount(transaction.amount)

        recipient = None
        recipient_amount = None
        recipient_currency = None
        if is_transfer:
            if transaction.is_external:
                if external_send is None:
                    raise InvalidOperationError("External transfer adapter is required")
                recipient_currency = transaction.external_recipient.currency
            else:
                if transaction.recipient_id == transaction.sender_id:
                    raise InvalidOperationError("Transfer requires two different accounts")
                if transaction.recipient_id not in self._accounts:
                    raise InvalidOperationError("Recipient account not found")
                recipient = self._accounts[transaction.recipient_id]
                recipient_currency = recipient.currency
            if recipient_currency is account.currency and exchange_rate != Decimal("1"):
                raise InvalidOperationError("Same-currency exchange rate must be one")
            recipient_amount = (
                transaction.amount if recipient_currency is account.currency
                else (transaction.amount * exchange_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
            account._validate_amount(recipient_amount)
            if account._balance < 0 and not isinstance(account, PremiumAccount):
                raise InvalidOperationError("Transfers from negative balances are prohibited")

        fee = external_fee
        if transaction.transaction_type is not TransactionType.DEPOSIT and isinstance(account, PremiumAccount):
            fee += account.fixed_fee
        balances = [(account, account._balance)]
        if recipient is not None:
            balances.append((recipient, recipient._balance))

        with self._authorize_account_operation():
            account._validate_status()
            if recipient is not None:
                recipient._validate_status()
            self._check_transaction_risk(transaction, now)
            self._validate_operation_time("transaction", now)
            try:
                if transaction.transaction_type is TransactionType.DEPOSIT:
                    account.deposit(transaction.amount)
                elif transaction.transaction_type is TransactionType.WITHDRAWAL:
                    account.withdraw(transaction.amount)
                else:
                    account.withdraw(transaction.amount + external_fee)
                    if recipient is not None:
                        recipient.deposit(recipient_amount)
                result = {
                    "fee": fee,
                    "exchange_rate": exchange_rate if is_transfer else None,
                    "recipient_amount": recipient_amount,
                    "recipient_currency": recipient_currency,
                    "external_reference": None,
                }
                if transaction.is_external:
                    receipt = external_send(transaction, recipient_amount)
                    result["external_reference"] = receipt["reference"]
                self._transaction_results[transaction.id] = result
            except Exception:
                for changed_account, balance in balances:
                    changed_account._balance = balance
                raise
        # The transfer is committed. Reporting failures must not roll it back.
        if self.risk_analyzer is not None:
            self.risk_analyzer.remember_success(transaction)
        self._audit_transaction(
            transaction, now, "INFO", "transaction_completed", "Transaction completed",
            {"transaction_type": transaction.transaction_type, "amount": transaction.amount,
             "currency": transaction.currency, **result},
        )
        return result.copy()

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
        now = self.clock()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise InvalidOperationError("Clock must return a timezone-aware datetime")
        return now.astimezone(timezone.utc)

    def _validate_operation_time(self, operation: str, now: datetime | None = None) -> None:
        current_time = now if now is not None else self._get_current_time()
        if not isinstance(current_time, datetime) or current_time.utcoffset() is None:
            raise InvalidOperationError("Current time must be a timezone-aware datetime")
        current_time = current_time.astimezone(self.bank_timezone)
        if 0 <= current_time.hour < 5:
            self.suspicious_activities.append(
                f"Restricted operation: {operation} at "
                f"{current_time.strftime('%H:%M')}"
            )
            retry_at = current_time.replace(hour=5, minute=0, second=0, microsecond=0)
            raise BankOperationRestrictedError(retry_at.astimezone(timezone.utc))

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
