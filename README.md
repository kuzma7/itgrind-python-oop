# Bank Management System — Python OOP

A banking management system developed as part of the **ItGrind ML/NLP course**, Python Object-Oriented Programming module.

The project demonstrates abstraction, inheritance, encapsulation, polymorphism, composition, and custom exception handling.

Built incrementally across three assignments, the system supports multiple bank account types, client management, authentication, account security, and financial analytics.

## Features

### Bank Accounts

The system supports four account types:

| Account | Functionality |
|---|---|
| `BankAccount` | Standard deposits and withdrawals |
| `SavingsAccount` | Minimum balance and monthly interest |
| `PremiumAccount` | Withdrawal limits, overdraft, and fixed transaction fees |
| `InvestmentAccount` | Investment portfolio and projected yearly growth |

Common features include:

- Unique account identifiers generated using UUID.
- Five supported currencies: RUB, USD, EUR, KZT, CNY.
- Account statuses: `ACTIVE`, `FROZEN`, `CLOSED`.
- Monetary calculations using `Decimal`.
- Transaction validation and custom exceptions.

### Client Management

The `Client` class provides:

- Unique client ID.
- Full name and contact information.
- Date of birth and minimum age validation (18+).
- Client statuses: `ACTIVE`, `BLOCKED`.
- List of associated bank account IDs.
- Password verification.

### Bank Management

The `Bank` class manages clients and their accounts.

Supported operations:

| Method | Description |
|---|---|
| `add_client()` | Register a new client |
| `open_account()` | Open an account for an existing client |
| `close_account()` | Close an eligible account |
| `freeze_account()` | Freeze an active account |
| `unfreeze_account()` | Restore a frozen account |
| `authenticate_client()` | Authenticate a client using a password |
| `search_accounts()` | Search accounts by client ID and status |
| `get_total_balance()` | Calculate total account funds grouped by currency |
| `get_clients_ranking()` | Rank clients by their funds in a selected currency |

### Security

- Password hashing using PBKDF2-HMAC-SHA256 with a random salt.
- Automatic client blocking after three consecutive failed login attempts.
- Reset of the failed-login counter after successful authentication.
- Logging of suspicious activities.
- Restrictions on account-management operations from **00:00 to 05:00**.
- Prevention of invalid account status transitions.

The nighttime restriction applies to account-management methods of `Bank`. Direct account transactions are not subject to this check in the current implementation.

**Note:** This is an educational in-memory application, not a production banking or authentication system.

### Financial Analytics

The system supports:

- Aggregating bank balances by currency.
- Including investment portfolios in total asset calculations.
- Accounting for negative Premium account balances.
- Ranking clients by total funds in a selected currency.

Different currencies are calculated separately without automatic conversion.

## Project Structure

```text
homework_1/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── exceptions.py
│   ├── client.py
│   ├── bank.py
│   ├── savings_account.py
│   ├── premium_account.py
│   └── investment_account.py
├── tests/
│   ├── test_account.py
│   ├── test_savings_account.py
│   ├── test_premium_account.py
│   ├── test_investment_account.py
│   └── test_bank.py
├── requirements.txt
├── .gitignore
└── README.md
```

## Technologies

- Python 3.10+
- pytest
- Python Standard Library: `abc`, `enum`, `uuid`, `decimal`, `datetime`, `hashlib`, `hmac`, `secrets`
- Git and GitHub

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

Run the demonstration:

```bash
python -m src.main
```

The demonstration includes:

- Registering multiple clients.
- Opening different account types.
- Deposits, withdrawals, and investments.
- Calculating savings interest and investment growth.
- Freezing and closing accounts.
- Client authentication and account blocking.
- Nighttime operation restrictions.
- Searching accounts and calculating financial statistics.

## Testing

The project uses **pytest** for automated functional testing.

Run the complete test suite:

```bash
python -m pytest -q
```

Run Bank functionality tests:

```bash
python -m pytest tests/test_bank.py -v
```

Tests cover the core banking scenarios, including account operations, client registration, authentication, security restrictions, account management, investment calculations, and financial analytics.

The test suite includes both positive and negative scenarios, with an emphasis on functional behavior rather than excessive isolated checks.

## OOP Concepts

**Abstraction:** `AbstractAccount` defines the common interface for account implementations.

**Inheritance:** Specialized account types extend `BankAccount` and reuse common functionality.

**Encapsulation:** Internal state is stored in attributes such as `_balance` and `_portfolio`, with operations controlled through class methods.

**Polymorphism:** Different account types provide their own implementations of shared methods.

**Composition:** `Bank` manages collections of `Client` and `BankAccount` objects.

**Method overriding:** Specialized accounts customize business rules while reusing parent methods through `super()`.

## Course Progress

**ItGrind — ML/NLP**

Module: Python / Object-Oriented Programming

| Assignment | Topic | Status |
|---|---|---|
| Day 1 | Abstract Account and BankAccount | Completed |
| Day 2 | Savings, Premium, and Investment Accounts | Completed |
| Day 3 | Bank Management, Clients, and Security | Implemented |

## Learning Objectives

- Apply object-oriented programming principles in Python.
- Design class hierarchies and relationships between objects.
- Implement financial business rules and validation.
- Manage application state using dictionaries and lists.
- Implement basic authentication and access restrictions.
- Write automated functional tests with pytest.
- Practice Git branching, commits, and Pull Requests.