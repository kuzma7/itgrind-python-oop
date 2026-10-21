# Bank Management System — Python OOP

Educational project for the **ItGrind ML/NLP course**, covering Days 1–7 of the Python OOP module.

## Features

| Account | Functionality |
|---|---|
| `BankAccount` | Deposits and withdrawals |
| `SavingsAccount` | Minimum balance and monthly interest |
| `PremiumAccount` | Withdrawal limits, fixed fees and overdraft |
| `InvestmentAccount` | Portfolio management and projected returns |

- Clients: age validation (18+), password hashing and blocking after three failed logins.
- Bank: account lifecycle, ownership checks, balances by currency and client rankings.
- Transactions: deposits, withdrawals and internal/external transfers; priority, scheduling, cancellation and retries.
- Audit: JSONL events, filtering, suspicious-operation reports, client risk profiles and error statistics.
- Reports: client, bank and risk summaries in TXT, JSON and CSV; pie, bar and balance-history charts with matplotlib.

## Main rules

- Supported currencies: RUB, USD, EUR, KZT and CNY. Input amounts use `Decimal` and must be positive multiples of `0.01`.
- External transfers charge **1%** in addition to the amount; Premium fixed fees also apply. Conversion uses fixed educational rates.
- Frozen/closed accounts cannot move money. Only Premium accounts allow overdraft, within its limit.
- Bank operations are restricted from **00:00 to 05:00, UTC+03:00** by default. Queued operations wait until morning.
- Temporary failures allow **three attempts total**, one minute apart. Failed operations restore balances; committed IDs prevent duplicate debits.
- Transaction instructions are immutable. Public `Bank.deposit()` and `Bank.withdraw()` use the same execution path as queued transactions.

With `AuditLog` and `RiskAnalyzer` passed to `Bank`, withdrawals and transfers are checked before money moves:

| Risk rule | Score |
|---|---:|
| Amount ≥ 100,000 RUB equivalent | +2 |
| Sixth or later unique operation within a minute | +2 |
| Recipient has no successful transfer history with this client | +1 |
| Bank-local time is 00:00–05:00 | +1 |

**LOW:** 0 points. **MEDIUM:** 1–2, warning and execution allowed. **HIGH:** 3+, operation blocked.
Direct and queued withdrawals share frequency history; retries do not count as new operations. Deposits are audited without these spending-risk rules.

## Structure

```text
src/
├── models.py, *_account.py   # Accounts and financial rules
├── client.py, bank.py        # Clients and bank operations
├── transaction*.py           # Transaction model, queue and processor
├── audit_log.py              # Journal, filters and audit reports
├── risk_analyzer.py          # Risk rules and client profiles
├── report_builder.py         # Reports, exports and charts
├── demo.py                   # Day 7 reporting demonstration
├── exceptions.py
└── main.py                   # Demonstrations for Days 1–5
tests/                       # Functional tests
requirements.txt             # pytest, matplotlib
```

## Setup and run

Requires **Python 3.10+**. From the project directory, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m src.main
```

The demonstration processes ten Day 4 transactions and shows Day 5 risk decisions and reports.
Audit events are appended to `logs/audit.jsonl`; generated logs are excluded from Git.

Run `python -m src.demo` for Day 7: 40 transactions, reports in `reports/`, three PNG charts in `reports/charts/` and audit events in `logs/day7_audit.jsonl`.

## Tests

```powershell
python -m pytest -q
```

Functional tests cover balances, account limits, access restrictions, queue behavior, conversion, fees, retries, rollback, duplicate protection, risk blocking, report exports and chart generation.

This is a single-threaded application with balances, queues and risk history kept in memory. External payments use a simulator. Existing JSONL records are not loaded into reports automatically.
