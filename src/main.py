from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from src.bank import Bank
from src.client import Client
from src.exceptions import InvalidOperationError
from src.investment_account import InvestmentAccount
from src.models import AccountStatus, BankAccount, Currency
from src.premium_account import PremiumAccount
from src.savings_account import SavingsAccount


def main() -> None:
    bank = Bank("ItGrind Bank")

    ivan = Client("Ivan Ivanov", date(1998, 5, 15), {"email": "ivan@example.com"}, "ivan-pass")
    maria = Client("Maria Petrova", date(1995, 8, 20), {"phone": "+79990000000"}, "maria-pass")

    bank.add_client(ivan)
    bank.add_client(maria)
    print(f"Bank: {bank.name} | Clients: {len(bank._clients)}")

    with patch.object(bank, "_get_current_time", return_value=datetime(2026, 10, 15, 12, 0)):
        standard = BankAccount(owner=ivan.full_name)
        savings = SavingsAccount(owner=ivan.full_name, monthly_rate=Decimal("0.05"))
        premium = PremiumAccount(owner=maria.full_name)
        investment = InvestmentAccount(owner=maria.full_name)

        for client, account in [
            (ivan, standard),
            (ivan, savings),
            (maria, premium),
            (maria, investment),
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

    with patch.object(bank, "_get_current_time", return_value=datetime(2026, 10, 15, 2, 30)):
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


if __name__ == "__main__":
    main()
