# Bank Account Management — Python OOP

A bank account management system developed as part of the **ItGrind ML/NLP course**.

The project demonstrates core Object-Oriented Programming (OOP) concepts in Python, including **abstraction, inheritance, encapsulation, polymorphism, method overriding, and custom exception handling**.

The system supports multiple account types with different business rules, monetary operations, and automated tests.

## Features

### Core Functionality
- Abstract `AbstractAccount` class defining a common interface.
- Concrete `BankAccount` implementation.
- Unique account identifiers generated using UUID.
- Support for five currencies: RUB, USD, EUR, KZT, CNY.
- Account statuses: `ACTIVE`, `FROZEN`, `CLOSED`.
- Deposits and withdrawals using `Decimal` for monetary calculations.
- Input validation and transaction restrictions.
- Custom exceptions for invalid operations.
- Human-readable account information.

### Account Types

**BankAccount — Standard Account**
- Supports deposits and withdrawals.
- Prevents withdrawals exceeding the available balance.
- Restricts transactions on frozen and closed accounts.

**SavingsAccount — Savings Account**
- Minimum balance restriction.
- Configurable monthly interest rate.
- Monthly interest calculation and capitalization.
- Prevents withdrawals that violate the minimum balance.

**PremiumAccount — Premium Account**
- Configurable per-transaction withdrawal limit.
- Overdraft support allowing a negative balance.
- Fixed fee charged for each withdrawal.
- Validation of overdraft and withdrawal limits.

**InvestmentAccount — Investment Account**
- Investment portfolio containing three asset types: `stocks`, `bonds`, and `etf`.
- Allocation of available funds to investment assets.
- Portfolio value calculation.
- Projected yearly growth based on configurable asset growth rates.
- Withdrawal restrictions for invested funds.
- Monetary rounding using `ROUND_HALF_UP`.

## Project Structure

```text
homework_1/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── exceptions.py
│   ├── savings_account.py
│   ├── premium_account.py
│   └── investment_account.py
├── tests/
│   ├── test_account.py
│   ├── test_savings_account.py
│   ├── test_premium_account.py
│   └── test_investment_account.py
├── .gitignore
├── requirements.txt
└── README.md
```

## Technologies

- Python 3.10+
- pytest
- Python Standard Library:
  - `abc` — Abstract Base Classes
  - `enum` — Enumerations
  - `uuid` — Unique account identifiers
  - `decimal` — Precise decimal arithmetic

## Installation

Clone the repository:

```bash
git clone https://github.com/kuzma7/itgrind-python-oop.git
cd itgrind-python-oop
```

Create and activate a virtual environment.

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Usage

Run the application demonstration from the project root:

```bash
python -m src.main
```

The demonstration includes:
- Standard account deposits and withdrawals.
- Savings account interest calculation.
- Premium account overdraft and withdrawal fees.
- Investment portfolio allocation and projected yearly growth.
- Handling operations on frozen accounts.
- Polymorphism using different account types through a common interface.

### Investment Account Example

```python
from decimal import Decimal
from src.investment_account import InvestmentAccount

account = InvestmentAccount(owner="Nikita")

account.deposit(Decimal("100000.00"))

account.invest("stocks", Decimal("50000.00"))
account.invest("bonds", Decimal("30000.00"))
account.invest("etf", Decimal("20000.00"))

growth_rates = {
    "stocks": Decimal("0.10"),
    "bonds": Decimal("0.04"),
    "etf": Decimal("0.07"),
}

projected_growth = account.project_yearly_growth(growth_rates)

print(f"Available balance: {account._balance}")
print(f"Projected yearly growth: {projected_growth}")
```

Expected output:

```text
Available balance: 0.00
Projected yearly growth: 7600.00
```

The projection does not modify the account balance or portfolio.

## Testing

Automated tests are implemented using **pytest**.

Run the complete test suite:

```bash
python -m pytest -v
```

Run tests for a specific account type:

```bash
python -m pytest tests/test_investment_account.py -v
```

The test suite covers:

- Account creation and validation.
- Deposits and withdrawals.
- Minimum balance restrictions.
- Monthly interest calculation.
- Premium account fees and overdraft.
- Investment portfolio allocation.
- Yearly growth projection and rounding.
- Invalid asset types and transaction amounts.
- Account status restrictions.
- Boundary values and error handling.
- Preservation of account state after failed operations.
- Polymorphism and method overriding.

## Custom Exceptions

| Exception | Description |
|---|---|
| `AccountFrozenError` | Operation attempted on a frozen account |
| `AccountClosedError` | Operation attempted on a closed account |
| `InvalidOperationError` | Invalid input, configuration, or transaction |
| `InsufficientFundsError` | Insufficient available funds or exceeded financial limits |

## OOP Concepts

**Abstraction**

The `AbstractAccount` class defines the common contract for bank accounts.

**Inheritance**

`SavingsAccount`, `PremiumAccount`, and `InvestmentAccount` extend `BankAccount` and reuse its common functionality.

**Encapsulation**

Account balances and investment portfolios are stored using protected attributes (`_balance`, `_portfolio`). Validation and business rules are implemented through class methods.

**Polymorphism**

Different account types implement their own versions of `withdraw()`, `get_account_info()`, and `__str__()`, allowing them to be used through a common interface.

**Method Overriding**

Child classes customize account behavior while reusing parent functionality with `super()`.

## Learning Objectives

- Practice abstract classes and inheritance.
- Understand encapsulation and polymorphism.
- Implement method overriding and `super()`.
- Work with dictionaries, enums, and `Decimal`.
- Implement financial business rules.
- Create and handle custom exceptions.
- Write parameterized automated tests using pytest.
- Follow Python coding conventions (PEP 8).
- Practice Git branching and Pull Request workflows.

## Course

**ItGrind — ML/NLP**

Module: Python / Object-Oriented Programming

Assignments:
- **Day 1:** Bank Account Model
- **Day 2:** Advanced Bank Accounts — Savings, Premium, and Investment Accounts