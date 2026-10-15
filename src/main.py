from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from src.bank import Bank
from src.client import Client
from src.exceptions import InvalidOperationError
from src.investment_account import InvestmentAccount
from src.models import AccountStatus, BankAccount, Currency
from src.premium_account import PremiumAccount
from src.savings_account import SavingsAccount
from src.transaction import ExternalRecipient, Transaction, TransactionType
from src.transaction_processor import ExternalTransferAdapter, TransactionProcessor
from src.transaction_queue import TransactionQueue


def demonstrate_transactions() -> None:
    print("\nDay 4: ten queued transactions")
    now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    bank = Bank("Transaction Demo Bank", clock=lambda: now)
    ivan = Client("Ivan Ivanov", date(1998, 5, 15), {"email": "ivan@example.com"}, "ivan-pass")
    maria = Client("Maria Petrova", date(1995, 8, 20), {"email": "maria@example.com"}, "maria-pass")
    bank.add_client(ivan)
    bank.add_client(maria)
    sender = BankAccount(ivan.full_name)
    premium = PremiumAccount(ivan.full_name)
    recipient = BankAccount(maria.full_name)
    usd = BankAccount(maria.full_name, Currency.USD)
    frozen = BankAccount(maria.full_name)

    for client, account in [
        (ivan, sender), (ivan, premium), (maria, recipient), (maria, usd), (maria, frozen),
    ]:
        bank.open_account(client.client_id, account)
    bank.freeze_account(frozen.uuid)
    external = ExternalRecipient("OTHER-BANK", "EXTERNAL-ACCOUNT-001", Currency.RUB)

    transactions = [
        Transaction(TransactionType.DEPOSIT, ivan.client_id, Decimal("1000"), Currency.RUB,
                    recipient_id=sender.uuid, priority=10),
        Transaction(TransactionType.WITHDRAWAL, ivan.client_id, Decimal("100"), Currency.RUB,
                    sender_id=sender.uuid, priority=9),
        Transaction(TransactionType.TRANSFER, ivan.client_id, Decimal("200"), Currency.RUB,
                    sender.uuid, recipient.uuid, priority=8),
        Transaction(TransactionType.TRANSFER, ivan.client_id, Decimal("100"), Currency.RUB,
                    sender_id=sender.uuid, priority=7, is_external=True, external_recipient=external),
        Transaction(TransactionType.TRANSFER, ivan.client_id, Decimal("90"), Currency.RUB,
                    sender.uuid, usd.uuid, priority=6),
        Transaction(TransactionType.TRANSFER, ivan.client_id, Decimal("50"), Currency.RUB,
                    premium.uuid, recipient.uuid, priority=5),
        Transaction(TransactionType.TRANSFER, ivan.client_id, Decimal("100000"), Currency.RUB,
                    sender.uuid, recipient.uuid, priority=4),
        Transaction(TransactionType.TRANSFER, ivan.client_id, Decimal("10"), Currency.RUB,
                    sender.uuid, frozen.uuid, priority=3),
        Transaction(TransactionType.DEPOSIT, ivan.client_id, Decimal("25"), Currency.RUB,
                    recipient_id=sender.uuid, scheduled_at=now + timedelta(minutes=1)),
        Transaction(TransactionType.WITHDRAWAL, ivan.client_id, Decimal("1"), Currency.RUB,
                    sender_id=sender.uuid),
    ]
    queue = TransactionQueue(clock=bank._get_current_time)
    for transaction in transactions:
        queue.add(transaction)
    queue.cancel(transactions[-1].id)
    adapter = ExternalTransferAdapter(failures_remaining=1)
    processor = TransactionProcessor(bank, queue, external_adapter=adapter)
    processor.process_all()
    print(f"Waiting after first pass: {len(queue)}")

    now += timedelta(minutes=1)
    processor.process_all()

    for index, transaction in enumerate(transactions, 1):
        print(
            f"  {index:2}. {transaction.transaction_type.value}: {transaction.status.value}"
            f" | amount={transaction.amount} {transaction.currency.value}"
            f" | fee={transaction.fee} | attempts={transaction.attempts}"
            f" | reason={transaction.failure_reason or '-'}"
        )
    receipt = adapter.get_receipt(transactions[3].id)
    print(f"External recipient: {receipt['recipient'].account_number}"
          f" | credited={receipt['amount']} {receipt['currency'].value}")
    print(f"Errors recorded: {len(processor.errors)} | Waiting: {len(queue)}")
    for account in (sender, premium, recipient, usd, frozen):
        print(f"  {account.owner} / {type(account).__name__}: {account._balance} {account.currency.value}")


def main() -> None:
    now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    bank = Bank("ItGrind Bank", clock=lambda: now)
    ivan = Client("Ivan Ivanov", date(1998, 5, 15), {"email": "ivan@example.com"}, "ivan-pass")
    maria = Client("Maria Petrova", date(1995, 8, 20), {"phone": "+79990000000"}, "maria-pass")
    bank.add_client(ivan)
    bank.add_client(maria)
    print(f"Bank: {bank.name} | Clients: {len(bank._clients)}")

    standard = BankAccount(owner=ivan.full_name)
    savings = SavingsAccount(owner=ivan.full_name, monthly_rate=Decimal("0.05"))
    premium = PremiumAccount(owner=maria.full_name)
    investment = InvestmentAccount(owner=maria.full_name)
    for client, account in [
        (ivan, standard), (ivan, savings), (maria, premium), (maria, investment),
    ]:
        bank.open_account(client.client_id, account)
    bank.deposit(ivan.client_id, standard.uuid, Decimal("10000.00"))
    bank.deposit(ivan.client_id, savings.uuid, Decimal("20000.00"))
    interest = bank.apply_monthly_interest(ivan.client_id, savings.uuid)
    print(f"Savings monthly interest: {interest} RUB")
    bank.withdraw(maria.client_id, premium.uuid, Decimal("4900.00"))
    bank.deposit(maria.client_id, investment.uuid, Decimal("30000.00"))
    bank.invest(maria.client_id, investment.uuid, "stocks", Decimal("20000.00"))
    bank.invest(maria.client_id, investment.uuid, "bonds", Decimal("10000.00"))
    rates = {"stocks": Decimal("0.10"), "bonds": Decimal("0.04"), "etf": Decimal("0.07")}
    growth = bank.project_yearly_growth(maria.client_id, investment.uuid, rates)
    print(f"Investment projected growth: {growth} RUB")
    bank.freeze_account(standard.uuid)
    print(f"Frozen accounts: {len(bank.search_accounts(status=AccountStatus.FROZEN))}")
    bank.unfreeze_account(standard.uuid)
    empty = BankAccount(owner=ivan.full_name)
    bank.open_account(ivan.client_id, empty)
    bank.close_account(empty.uuid)
    print(f"Closed accounts: {len(bank.search_accounts(status=AccountStatus.CLOSED))}")
    print(f"Ivan authentication: {bank.authenticate_client(ivan.client_id, 'ivan-pass')}")

    for _ in range(3):
        try:
            bank.authenticate_client(maria.client_id, "wrong")
        except InvalidOperationError as error:
            print(f"Authentication restriction: {error}")
    print(f"Maria status: {maria.status.value}")
    try:
        bank.deposit(maria.client_id, premium.uuid, Decimal("100.00"))
    except InvalidOperationError as error:
        print(f"Blocked client restriction: {error}")

    now = datetime(2026, 10, 15, 2, 30, tzinfo=bank.bank_timezone)
    try:
        bank.withdraw(ivan.client_id, standard.uuid, Decimal("100.00"))
    except InvalidOperationError as error:
        print(f"Night restriction: {error}")

    print("\nBalances by currency:")
    for currency, balance in bank.get_total_balance().items():
        print(f"  {currency.value}: {balance}")
    print("\nClient ranking (RUB):")
    for place, (client, balance) in enumerate(bank.get_clients_ranking(Currency.RUB), 1):
        print(f"  {place}. {client.full_name}: {balance} RUB")
    print("\nSuspicious events:")
    for event in bank.suspicious_activities:
        print(f"  - {event}")
    demonstrate_transactions()


if __name__ == "__main__":
    main()
