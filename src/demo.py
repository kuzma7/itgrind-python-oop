from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

import matplotlib

matplotlib.use("Agg")

from src.audit_log import AuditLog
from src.bank import Bank
from src.client import Client
from src.investment_account import InvestmentAccount
from src.models import BankAccount, Currency
from src.premium_account import PremiumAccount
from src.report_builder import ReportBuilder
from src.risk_analyzer import RiskAnalyzer
from src.savings_account import SavingsAccount
from src.transaction import TransactionType, ExternalRecipient, Transaction
from src.transaction_processor import TransactionProcessor
from src.transaction_queue import TransactionQueue


def create_demo_bank():
    now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    audit = AuditLog("logs/day7_audit.jsonl")
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

    for client in clients.values():
        bank.add_client(client)

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


def collect_balance_snapshot(accounts: dict, timestamp: datetime, history: dict) -> None:
    for name, account in accounts.items():
        history.setdefault(name, []).append({
            "timestamp": timestamp,
            "balance": account._balance,
            "currency": account.currency.value,
        })


def run_simulation(
    queue: TransactionQueue, processor: TransactionProcessor,
    transactions: list[Transaction], accounts: dict,
) -> dict:
    history = {}
    start = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)

    collect_balance_snapshot(accounts, start - timedelta(seconds=1), history)

    for transaction in transactions:
        queue.add(transaction)

    for minute in range(85):
        now = start + timedelta(minutes=minute)

        while True:
            processed = processor.process_next(now)
            if processed is None:
                break

            collect_balance_snapshot(accounts, now, history)

    next_day = start + timedelta(days=1)

    while True:
        processed = processor.process_next(next_day)
        if processed is None:
            break

        collect_balance_snapshot(accounts, next_day, history)

    return history


if __name__ == "__main__":
    bank, clients, accounts, queue, processor, audit, risk = create_demo_bank()
    fund_demo_accounts(bank, clients, accounts)
    transactions = create_demo_transactions(clients, accounts)
    history = run_simulation(queue, processor, transactions, accounts)

    builder = ReportBuilder(bank, transactions, audit)
    reports = {
        "client": builder.build_client_report(clients["nikita"].client_id),
        "bank": builder.build_bank_report(),
        "risk": builder.build_risk_report(),
    }
    for name, report in reports.items():
        print(f"\n=== DAY 7: {name.upper()} REPORT ===")
        print(builder.build_text_report(report))
        builder.export_to_json(report, f"reports/{name}.json")
        builder.export_to_csv(report, f"reports/{name}.csv")
        builder.export_to_txt(report, f"reports/{name}.txt")

    builder.save_charts("reports/charts", history, "nikita_standard")
    print("\nDay 7: Reports and charts saved to reports/")
