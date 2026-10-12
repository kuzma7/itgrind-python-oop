# Bank Account Management — Python OOP

A simple bank account management system developed as part of the **ItGrind ML/NLP course**.

The project demonstrates core Object-Oriented Programming (OOP) concepts in Python, including abstraction, inheritance, encapsulation, polymorphism, and custom exception handling.

## Features

- Abstract `AbstractAccount` class defining a common interface for bank accounts.
- Concrete `BankAccount` implementation.
- Automatic generation of a short UUID for new accounts.
- Support for five currencies: RUB, USD, EUR, KZT, CNY.
- Account statuses: `ACTIVE`, `FROZEN`, `CLOSED`.
- Deposits and withdrawals using `Decimal` for precise monetary calculations.
- Validation of input data and transaction amounts.
- Custom exceptions for invalid operations and account restrictions.
- Human-readable account information.
- Automated tests using `pytest`.

## Project Structure

```text
homework_1/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   └── exceptions.py
├── tests/
│   └── test_account.py
├── .gitignore
├── requirements.txt
└── README.md
```

## Technologies

- Python 3.10+
- pytest
- Python Standard Library (`abc`, `enum`, `uuid`, `decimal`)

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

The demonstration includes creating accounts, performing deposits and withdrawals, and handling restricted operations.

## Testing

Run all automated tests:

```bash
python -m pytest -v
```

Tests cover account creation, monetary operations, invalid input, account statuses, and custom exceptions.

## Custom Exceptions

| Exception | Description |
|---|---|
| `AccountFrozenError` | Operation attempted on a frozen account |
| `AccountClosedError` | Operation attempted on a closed account |
| `InvalidOperationError` | Invalid input or transaction amount |
| `InsufficientFundsError` | Withdrawal amount exceeds available balance |

## Learning Objectives

- Practice abstract classes and inheritance.
- Apply encapsulation to object attributes.
- Work with enums and the `Decimal` type.
- Implement business rules and custom exceptions.
- Write automated tests using pytest.
- Follow Python coding conventions (PEP 8).

## Course

**ItGrind — ML/NLP**

Module: Python / Object-Oriented Programming  
Assignment: Day 1 — Bank Account Model
