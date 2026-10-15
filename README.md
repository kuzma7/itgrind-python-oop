# Bank Management System — Python OOP

A banking management system developed as part of the **ItGrind ML/NLP course**, Python Object-Oriented Programming module.

The project demonstrates abstraction, inheritance, encapsulation, polymorphism, composition, and custom exception handling.

Built incrementally across four assignments, the system supports multiple bank account types, client management, authentication, account security, financial analytics, and queued transactions.

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
| `execute_transaction()` | Atomically apply a queued operation and remember its result by ID |

### Security

- Password hashing using PBKDF2-HMAC-SHA256 with a random salt.
- Automatic client blocking after three consecutive failed login attempts.
- Reset of the failed-login counter after successful authentication.
- Logging of suspicious activities.
- Restrictions on account-management operations from **00:00 to 05:00**.
- Prevention of invalid account status transitions.

The nighttime restriction applies to account management and money operations through `Bank`, using the bank's local time. Registered accounts reject direct money operations; they must go through `Bank`.

**Note:** This is an educational in-memory application, not a production banking or authentication system.

### Financial Analytics

The system supports:

- Aggregating bank balances by currency.
- Including investment portfolios in total asset calculations.
- Accounting for negative Premium account balances.
- Ranking clients by total funds in a selected currency.

Different currencies are calculated separately without automatic conversion.

### Day 4: Transaction System

Only three new source modules are used: `transaction.py`, `transaction_queue.py`, and `transaction_processor.py`. Processing is single-threaded, with an ordinary list and no database or external services.

`Transaction` stores a full UUID, operation type (`DEPOSIT`, `WITHDRAWAL`, `TRANSFER`), client ID, sender/recipient account IDs, amount, currency, charged fee, status, failure reason, and UTC timestamps. It also stores priority, schedule, attempt count, error history, and conversion results. A deposit requires only a recipient, a withdrawal only a sender, and a transfer two distinct accounts.

`TransactionQueue` provides `add(transaction)`, `get_next(now=None)`, and `cancel(transaction_id)`. Higher integer priorities run first; equal priorities preserve insertion order. Scheduled operations wait until `scheduled_at`, which must include a timezone; past dates are allowed. `get_next` claims an operation by setting `PROCESSING`. Only `PENDING` and `RETRY_WAIT` operations can be cancelled. `len(queue)` counts waiting operations, including future ones. Results remain in the queue's list for duplicate-ID protection.

`TransactionProcessor(bank, queue)` provides `process_next(now=None)` and `process_all(now=None)`. A pass processes ready work and returns without sleeping when only future work remains. Call it again when the next schedule arrives. The optional `now` controls queue eligibility and result timestamps; bank access restrictions independently use the bank's clock.

Business rules:

- All amounts are positive finite `Decimal` values. Deposit and withdrawal currencies must match their account. A transfer amount and its fee are in the sender's currency.
- Internal transfers have no percentage fee. An external transfer (`is_external=True`) charges **1%**, rounded to cents with `ROUND_HALF_UP`, in addition to the principal. Both endpoints are registered accounts in this educational bank; no real external bank connection is involved.
- Existing account rules remain active. Premium withdrawals/transfers also charge the Day 3 fixed fee once; `transaction.fee` reports the total charged fee. For a Premium transfer, the withdrawal limit applies to principal plus external fee, and the overdraft check also includes the fixed fee. Savings minimum balances and investment available balances are respected.
- Frozen or closed sender/recipient accounts reject money operations. The initiating client must be active and own the debited account (or the credited account for a deposit). Only Premium accounts may transfer from a negative balance and use overdraft, within its limit.
- Fixed educational quotes, in RUB per currency unit: RUB `1`, USD `90`, EUR `100`, KZT `0.20`, CNY `12.50`. Conversion uses `source_quote / target_quote`; the recipient amount is rounded to cents with `ROUND_HALF_UP`. Amounts rounding to zero are rejected. These are illustrative constants, not live exchange rates.
- Temporary failures (`TemporaryTransactionError`, `TimeoutError`, `ConnectionError`) wait one minute before the next attempt. There are at most **3 attempts total**, including the first. Business errors and unexpected errors are logged and fail immediately.
- A nighttime restriction sets `RETRY_WAIT` until 05:00 in the bank's local time, without consuming the temporary-error attempt budget. Waiting operations are retained and can be cancelled.
- Failed operations restore account balances. Successful results are remembered by transaction ID in `Bank`, so even a retry after a lost response does not debit twice. If a response fails after commit, the processor retrieves the recorded result and marks the operation completed immediately. Completed, failed, and cancelled operations are not selected again.
- `transaction.errors` and `processor.errors` record the transaction ID, attempt, timestamp, exception type, and message. A successful retry clears `failure_reason` but preserves the error history.

This atomicity and duplicate protection apply within the lifetime of one in-memory `Bank`. Queue state and committed IDs are not persisted across application restarts.

Example (with registered active clients/accounts, during permitted bank hours):

```python
from decimal import Decimal
from src.models import Currency
from src.transaction import Transaction, TransactionType
from src.transaction_queue import TransactionQueue
from src.transaction_processor import TransactionProcessor

queue = TransactionQueue()
transaction = Transaction(
    TransactionType.TRANSFER,
    client_id=ivan.client_id,
    amount=Decimal("5000.00"),
    currency=Currency.RUB,
    sender_id=ivan_account.uuid,
    recipient_id=maria_account.uuid,
    is_external=True,
)
queue.add(transaction)
processor = TransactionProcessor(bank, queue)
processor.process_all()
print(transaction.status.value, transaction.fee)
```

## Project Structure

```text
homework_1/
├── src/
│   ├── main.py
│   ├── models.py
│   ├── exceptions.py
│   ├── client.py
│   ├── bank.py
│   ├── savings_account.py
│   ├── premium_account.py
│   ├── investment_account.py
│   ├── transaction.py
│   ├── transaction_queue.py
│   └── transaction_processor.py
├── tests/
│   ├── test_account.py
│   ├── test_savings_account.py
│   ├── test_premium_account.py
│   ├── test_investment_account.py
│   ├── test_bank.py
│   ├── test_transaction.py
│   ├── test_transaction_queue.py
│   └── test_transaction_processor.py
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
- Creating and queuing **10 transactions**: deposits, withdrawals, internal/external transfers, conversion, Premium overdraft, insufficient funds, a frozen recipient, cancellation, and a deferred deposit. A controlled clock advances the schedule without sleeping. Final results: 7 completed, 2 failed, 1 cancelled.

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

Tests focus on observable business scenarios: balance changes, financial limits, account access, and transaction outcomes. They omit string formatting checks, constructor-field duplication, and exhaustive invalid Python-type combinations.

| Test module | Functional requirements |
|---|---|
| `test_account.py` | Deposits, withdrawals, valid monetary amounts, insufficient funds, frozen/closed accounts |
| `test_savings_account.py` | Minimum balance, monthly interest, compounding, inactive-account restrictions |
| `test_premium_account.py` | Fixed fees, withdrawal limit, overdraft boundary and repayment |
| `test_investment_account.py` | Supported assets, separate portfolios, available funds, projected gains/losses and rounding |
| `test_bank.py` | Client registration, adult clients, ownership, authentication, lockout, account lifecycle, nighttime restrictions, totals and rankings |
| `test_transaction.py` | Positive finite amounts, required operation endpoints, external-transfer eligibility |
| `test_transaction_queue.py` | Priority/FIFO, scheduling with timezones, cancellation, duplicate and finished-operation rejection |
| `test_transaction_processor.py` | Ten-operation batch, fees, actual converted balances, access restrictions, retries, rollback, error records and duplicate-debit prevention |

Day 4 tests also check a batch of ten transactions, priorities, schedules, cancellation, fees, conversion, access restrictions, overdraft, atomic rollback, bounded retries, nighttime deferral, and duplicate protection after a lost acknowledgement.

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
| Day 4 | Transactions, Queue, Processing, Fees, and Conversion | Implemented |

## Learning Objectives

- Apply object-oriented programming principles in Python.
- Design class hierarchies and relationships between objects.
- Implement financial business rules and validation.
- Manage application state using dictionaries and lists.
- Implement basic authentication and access restrictions.
- Write automated functional tests with pytest.
- Practice Git branching, commits, and Pull Requests.
