from collections import Counter
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from src.audit_log import AuditLog
from src.bank import Bank
from src.client import Client
from src.investment_account import InvestmentAccount
from src.models import BankAccount, Currency
from src.premium_account import PremiumAccount
from src.risk_analyzer import RiskAnalyzer
from src.savings_account import SavingsAccount
from src.transaction import TransactionType, ExternalRecipient, Transaction, TransactionStatus
from src.transaction_processor import TransactionProcessor
from src.transaction_queue import TransactionQueue


def create_demo_bank():
    now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    audit = AuditLog("logs/day6_audit.jsonl")
    risk = RiskAnalyzer()
    bank = Bank("ItGrind Demo Bank", clock=lambda: now, audit_log=audit, risk_analyzer=risk)

    clients = {
        "nikita": Client("Nikita Kuznetsov", date(2003, 5, 28), {"phone": "+79200000001"}, "password123"),
        "ivan": Client("Ivan Ivanov", date(1998, 5, 15), {"email": "ivan@example.com"}, "password123"),
        "maria": Client("Maria Petrova", date(1995, 8, 20), {"phone": "+79200000002"}, "password123"),
        "alex": Client("Alex Smirnov", date(1992, 3, 12), {"email": "alex@example.com"}, "password123"),
        "anna": Client("Anna Sokolova", date(2000, 11, 7), {"email": "anna@example.com"}, "password123"),
        "dmitry": Client("Dmitry Volkov", date(1989, 6, 24), {"phone": "+79200000003"}, "password123"),
        "elena": Client("Elena Morozova", date(1997, 9, 3), {"email": "elena@example.com"}, "password123"),
    }
    accounts = {
        "nikita_standard": BankAccount(owner=clients["nikita"].full_name),
        "nikita_savings": SavingsAccount(owner=clients["nikita"].full_name),
        "ivan_standard": BankAccount(owner=clients["ivan"].full_name),
        "ivan_premium": PremiumAccount(owner=clients["ivan"].full_name),
        "maria_standard": BankAccount(owner=clients["maria"].full_name),
        "maria_investment": InvestmentAccount(owner=clients["maria"].full_name),
        "alex_standard": BankAccount(owner=clients["alex"].full_name),
        "alex_usd": BankAccount(owner=clients["alex"].full_name, currency=Currency.USD),
        "anna_standard": BankAccount(owner=clients["anna"].full_name),
        "dmitry_savings": SavingsAccount(owner=clients["dmitry"].full_name),
        "elena_standard": BankAccount(owner=clients["elena"].full_name),
        "elena_premium": PremiumAccount(owner=clients["elena"].full_name),
    }

    # TODO: Создать и зарегистрировать 7 клиентов
    for client in clients.values():
        bank.add_client(client)

    # TODO: Создать и открыть 12 счетов
    bank.open_account(clients["nikita"].client_id, accounts["nikita_standard"])
    bank.open_account(clients["nikita"].client_id, accounts["nikita_savings"])

    bank.open_account(clients["ivan"].client_id, accounts["ivan_standard"])
    bank.open_account(clients["ivan"].client_id, accounts["ivan_premium"])

    bank.open_account(clients["maria"].client_id, accounts["maria_standard"])
    bank.open_account(clients["maria"].client_id, accounts["maria_investment"])

    bank.open_account(clients["alex"].client_id, accounts["alex_standard"])
    bank.open_account(clients["alex"].client_id, accounts["alex_usd"])

    bank.open_account(clients["anna"].client_id, accounts["anna_standard"])
    bank.open_account(clients["dmitry"].client_id, accounts["dmitry_savings"])

    bank.open_account(clients["elena"].client_id, accounts["elena_standard"])
    bank.open_account(clients["elena"].client_id, accounts["elena_premium"])

    queue = TransactionQueue()
    processor = TransactionProcessor(bank, queue)
    return bank, clients, accounts, queue, processor, audit, risk


def fund_demo_accounts(bank: Bank, clients: dict, accounts: dict) -> None:
    bank.deposit(clients["nikita"].client_id, accounts["nikita_standard"].uuid, Decimal("150000.00"))
    bank.deposit(clients["nikita"].client_id, accounts["nikita_savings"].uuid, Decimal("300000.00"))

    bank.deposit(clients["ivan"].client_id, accounts["ivan_standard"].uuid, Decimal("80000.00"))
    bank.deposit(clients["ivan"].client_id, accounts["ivan_premium"].uuid, Decimal("50000.00"))

    bank.deposit(clients["maria"].client_id, accounts["maria_standard"].uuid, Decimal("120000.00"))
    bank.deposit(clients["maria"].client_id, accounts["maria_investment"].uuid, Decimal("200000.00"))

    bank.deposit(clients["alex"].client_id, accounts["alex_standard"].uuid, Decimal("90000.00"))
    bank.deposit(clients["alex"].client_id, accounts["alex_usd"].uuid, Decimal("5000.00"))

    bank.deposit(clients["anna"].client_id, accounts["anna_standard"].uuid, Decimal("70000.00"))

    bank.deposit(clients["dmitry"].client_id, accounts["dmitry_savings"].uuid, Decimal("250000.00"))

    bank.deposit(clients["elena"].client_id, accounts["elena_standard"].uuid, Decimal("60000.00"))
    bank.deposit(clients["elena"].client_id, accounts["elena_premium"].uuid, Decimal("40000.00"))


def create_demo_transactions(clients: dict, accounts: dict) -> list[Transaction]:
    transactions = []
    start = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)

    def add(operation, client, amount, sender=None, recipient=None, external=None, priority=0, scheduled_at=None):
        account = accounts[sender or recipient]
        transaction = Transaction(
            transaction_type=operation,
            client_id=clients[client].client_id,
            amount=Decimal(str(amount)),
            currency=account.currency,
            sender_id=accounts[sender].uuid if sender else None,
            recipient_id=accounts[recipient].uuid if recipient else None,
            priority=priority,
            scheduled_at=scheduled_at if scheduled_at is not None else start + timedelta(minutes=len(transactions) * 2),
            is_external=external is not None,
            external_recipient=external,
        )
        transactions.append(transaction)

    # Deposits
    add(TransactionType.DEPOSIT, "nikita", "10000", recipient="nikita_standard")
    add(TransactionType.DEPOSIT, "ivan", "5000", recipient="ivan_standard")
    add(TransactionType.DEPOSIT, "maria", "15000", recipient="maria_standard")
    add(TransactionType.DEPOSIT, "alex", "2000", recipient="alex_standard")
    add(TransactionType.DEPOSIT, "anna", "7500", recipient="anna_standard")
    add(TransactionType.DEPOSIT, "dmitry", "12000", recipient="dmitry_savings")
    add(TransactionType.DEPOSIT, "elena", "8000", recipient="elena_standard")
    add(TransactionType.DEPOSIT, "alex", "100", recipient="alex_usd")

    # Withdrawals
    add(TransactionType.WITHDRAWAL, "nikita", "3000", sender="nikita_standard")
    add(TransactionType.WITHDRAWAL, "ivan", "2500", sender="ivan_standard")
    add(TransactionType.WITHDRAWAL, "maria", "4000", sender="maria_standard")
    add(TransactionType.WITHDRAWAL, "alex", "100", sender="alex_usd")
    add(TransactionType.WITHDRAWAL, "anna", "5000", sender="anna_standard")
    add(TransactionType.WITHDRAWAL, "elena", "2000", sender="elena_premium")

    # Internal transfers
    add(TransactionType.TRANSFER, "nikita", "5000", "nikita_standard", "ivan_standard")
    add(TransactionType.TRANSFER, "ivan", "3000", "ivan_standard", "maria_standard")
    add(TransactionType.TRANSFER, "maria", "7000", "maria_standard", "alex_standard")
    add(TransactionType.TRANSFER, "alex", "2500", "alex_standard", "anna_standard")
    add(TransactionType.TRANSFER, "anna", "1500", "anna_standard", "elena_standard")
    add(TransactionType.TRANSFER, "elena", "4000", "elena_standard", "nikita_standard")
    add(TransactionType.TRANSFER, "dmitry", "6000", "dmitry_savings", "ivan_standard")
    add(TransactionType.TRANSFER, "nikita", "12000", "nikita_standard", "nikita_savings")
    add(TransactionType.TRANSFER, "ivan", "8000", "ivan_standard", "ivan_premium")
    add(TransactionType.TRANSFER, "maria", "10000", "maria_standard", "maria_investment")
    add(TransactionType.TRANSFER, "elena", "3500", "elena_standard", "elena_premium")
    add(TransactionType.TRANSFER, "alex", "4500", "alex_standard", "dmitry_savings")

    # External transfers
    external_rub = ExternalRecipient("OTHER-BANK", "40817810000000000001", Currency.RUB)
    external_usd = ExternalRecipient("FOREIGN-BANK", "US-ACCOUNT-001", Currency.USD)

    add(TransactionType.TRANSFER, "nikita", "2000", sender="nikita_standard", external=external_rub)
    add(TransactionType.TRANSFER, "ivan", "3500", sender="ivan_standard", external=external_rub)
    add(TransactionType.TRANSFER, "maria", "5000", sender="maria_standard", external=external_usd)
    add(TransactionType.TRANSFER, "alex", "50", sender="alex_usd", external=external_usd)
    add(TransactionType.TRANSFER, "elena", "3000", sender="elena_premium", external=external_rub)

    # Currency conversion
    add(TransactionType.TRANSFER, "alex", "100", "alex_usd", "nikita_standard")
    add(TransactionType.TRANSFER, "nikita", "9000", "nikita_standard", "alex_usd")
    add(TransactionType.TRANSFER, "alex", "200", "alex_usd", "maria_standard")

    # Invalid operations
    add(TransactionType.WITHDRAWAL, "anna", "99999999", sender="anna_standard")
    add(TransactionType.WITHDRAWAL, "dmitry", "400000", sender="dmitry_savings")
    add(TransactionType.WITHDRAWAL, "ivan", "1000", sender="nikita_standard")

    # Suspicious operations
    add(TransactionType.TRANSFER, "nikita", "120000", "nikita_standard", "elena_standard")
    add(TransactionType.TRANSFER, "maria", "110000", "maria_standard", "dmitry_savings")

    # Delayed transaction
    add(
        TransactionType.TRANSFER, "ivan", "1000",
        sender="ivan_standard", recipient="anna_standard",
        priority=10, scheduled_at=start + timedelta(days=1),
    )
    return transactions


def run_simulation(queue: TransactionQueue, processor: TransactionProcessor, transactions: list[Transaction]) -> None:
    start = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)

    print("\n=== TRANSACTION QUEUE ===")
    for index, transaction in enumerate(transactions, 1):
        queue.add(transaction)
        print(
            f"[QUEUED] #{index:02} | {transaction.transaction_type.value} | {transaction.amount} {transaction.currency.value}")

    print(f"\nTotal queued: {len(queue)}")

    print("\n=== TRANSACTION PROCESSING ===")
    for minute in range(85):
        now = start + timedelta(minutes=minute)
        processed = processor.process_all(now)

        for transaction in processed:
            status = transaction.status.value.upper()
            reason = f" | {transaction.failure_reason}" if transaction.failure_reason else ""
            print(f"[{status}] {transaction.id[:8]} | {transaction.amount} {transaction.currency.value}{reason}")

    print(f"\nWaiting before next day: {len(queue)}")

    print("\n=== DELAYED TRANSACTIONS ===")
    next_day = start + timedelta(days=1)

    for transaction in processor.process_all(next_day):
        status = transaction.status.value.upper()
        reason = f" | {transaction.failure_reason}" if transaction.failure_reason else ""
        print(f"[{status}] {transaction.id[:8]} | {transaction.amount} {transaction.currency.value}{reason}")

    print("\n=== FINAL TRANSACTION STATUSES ===")
    for index, transaction in enumerate(transactions, 1):
        reason = transaction.failure_reason or "-"
        print(
            f"{index:02}. {transaction.transaction_type.value:<10} | {transaction.status.value:<12} | attempts={transaction.attempts} | {reason}")

    completed = sum(tx.status is TransactionStatus.COMPLETED for tx in transactions)
    failed = sum(tx.status is TransactionStatus.FAILED for tx in transactions)
    cancelled = sum(tx.status is TransactionStatus.CANCELLED for tx in transactions)
    pending = sum(tx.status in (TransactionStatus.PENDING, TransactionStatus.RETRY_WAIT) for tx in transactions)

    print("\n=== SIMULATION SUMMARY ===")
    print(f"Total: {len(transactions)}")
    print(f"Completed: {completed}")
    print(f"Failed: {failed}")
    print(f"Cancelled: {cancelled}")
    print(f"Pending: {pending}")
    print(f"Errors recorded: {len(processor.errors)}")


def show_client_info(bank: Bank, client: Client, transactions: list[Transaction]) -> None:
    print(f"\n=== CLIENT PROFILE: {client.full_name} ===")
    print(f"Client ID: {client.client_id}")
    print(f"Status: {client.status.value}")

    accounts = bank.search_accounts(client_id=client.client_id)
    print(f"\nAccounts ({len(accounts)}):")

    for account in accounts:
        print(
            f"  {account.uuid} | {type(account).__name__} | {account._balance} {account.currency.value} | {account.account_status.value}")

    account_ids = set(client.account_ids)
    history = [
        tx for tx in transactions
        if tx.client_id == client.client_id or tx.sender_id in account_ids or tx.recipient_id in account_ids
    ]

    print(f"\nTransaction history ({len(history)}):")

    for tx in history:
        print(
            f"  {tx.id[:8]} | {tx.transaction_type.value:<10} | {tx.amount:>10} {tx.currency.value} | {tx.status.value}")

        if tx.failure_reason:
            print(f"    Reason: {tx.failure_reason}")


def show_suspicious_operations(audit: AuditLog) -> None:
    suspicious = audit.get_suspicious_operations()

    print("\n=== SUSPICIOUS OPERATIONS ===")
    print(f"Suspicious risk checks: {len(suspicious)}")

    if not suspicious:
        print("No suspicious operations detected")
        return

    for entry in suspicious:
        details = entry["details"]
        print(f"  Transaction: {entry['transaction_id'][:8]}")
        print(f"  Client: {entry['client_id']}")
        print(f"  Risk level: {details['risk_level']}")
        print(f"  Score: {details['score']}")
        print(f"  Reasons: {', '.join(details['reasons'])}")
        print()


def show_reports(bank: Bank, transactions: list[Transaction], audit: AuditLog) -> None:
    print("\n=== BANK REPORT ===")

    statuses = Counter(tx.status.value for tx in transactions)
    types = Counter(tx.transaction_type.value for tx in transactions)

    print("\nTransaction statistics:")
    print(f"Total: {len(transactions)}")

    for status in TransactionStatus:
        print(f"  {status.value}: {statuses[status.value]}")

    print("\nTransaction types:")
    for transaction_type in TransactionType:
        print(f"  {transaction_type.value}: {types[transaction_type.value]}")

    print(f"\nTotal processing attempts: {sum(tx.attempts for tx in transactions)}")
    print(f"Recorded errors: {len(bank.transaction_errors)}")

    suspicious = audit.get_suspicious_operations()
    suspicious_ids = {entry["transaction_id"] for entry in suspicious}
    blocked_ids = {
        entry["transaction_id"]
        for entry in suspicious
        if entry["details"]["risk_level"] == "HIGH"
    }

    print(f"Suspicious transactions: {len(suspicious_ids)}")
    print(f"High-risk transactions: {len(blocked_ids)}")

    print("\nTop 3 clients (RUB):")
    ranking = bank.get_clients_ranking(Currency.RUB)

    for place, (client, balance) in enumerate(ranking[:3], 1):
        print(f"  {place}. {client.full_name}: {balance} RUB")

    print("\nTotal bank balance:")
    for currency, balance in bank.get_total_balance().items():
        print(f"  {currency.value}: {balance}")

    print("\nError statistics:")
    for error_type, count in audit.get_error_statistics().items():
        print(f"  {error_type}: {count}")


if __name__ == "__main__":
    bank, clients, accounts, queue, processor, audit, risk = create_demo_bank()
    fund_demo_accounts(bank, clients, accounts)

    transactions = create_demo_transactions(clients, accounts)

    print("\n=== BANK INITIALIZATION ===")
    print(f"Bank: {bank.name}")
    print(f"Clients: {len(clients)}")
    print(f"Accounts: {len(accounts)}")
    print(f"Transactions: {len(transactions)}")

    run_simulation(queue, processor, transactions)

    show_client_info(bank, clients["nikita"], transactions)
    show_client_info(bank, clients["maria"], transactions)

    show_suspicious_operations(audit)
    show_reports(bank, transactions, audit)
