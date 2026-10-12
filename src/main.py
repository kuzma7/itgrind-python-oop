from decimal import Decimal

from src.exceptions import AccountFrozenError
from src.models import AccountStatus, BankAccount, Currency


def main():
    active_account = BankAccount(
        owner="Nikita",
        currency=Currency.RUB,
    )

    frozen_account = BankAccount(
        owner="Alex",
        currency=Currency.USD,
        status=AccountStatus.FROZEN,
    )

    print("=== Active account ===")
    print(active_account)

    active_account.deposit(Decimal("1000.00"))
    active_account.withdraw(Decimal("250.00"))

    print("\nAfter operations:")
    print(active_account)

    print("\n=== Frozen account ===")
    print(frozen_account)

    try:
        frozen_account.deposit(Decimal("100.00"))
    except AccountFrozenError as error:
        print(f"Expected error: {error}")


if __name__ == "__main__":
    main()
