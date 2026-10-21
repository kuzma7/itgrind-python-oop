import csv
import json
import runpy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from src.audit_log import AuditLog
from src.bank import Bank
from src.client import Client
from src.demo import collect_balance_snapshot
from src.models import BankAccount, Currency
from src.report_builder import ReportBuilder
from src.risk_analyzer import RiskAnalyzer
from src.transaction import Transaction, TransactionType
from src.transaction_processor import TransactionProcessor
from src.transaction_queue import TransactionQueue


NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


@pytest.fixture
def reporting(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    bank = Bank("Report Bank", clock=lambda: NOW, audit_log=audit, risk_analyzer=RiskAnalyzer())
    ivan = Client("Иван", date(1990, 1, 1), {"email": "ivan@example.com"}, "password123")
    maria = Client("Мария", date(1990, 1, 1), {"email": "maria@example.com"}, "password123")
    accounts = {
        "ivan": BankAccount(ivan.full_name),
        "maria": BankAccount(maria.full_name),
        "maria_usd": BankAccount(maria.full_name, currency=Currency.USD),
    }
    for client in (ivan, maria):
        bank.add_client(client)
    bank.open_account(ivan.client_id, accounts["ivan"])
    bank.open_account(maria.client_id, accounts["maria"])
    bank.open_account(maria.client_id, accounts["maria_usd"])
    bank.deposit(ivan.client_id, accounts["ivan"].uuid, Decimal("1000000.00"))

    transactions = []
    for operation, amount, recipient in (
        (TransactionType.DEPOSIT, "50.00", "ivan"),
        (TransactionType.TRANSFER, "10.00", "maria"),
        (TransactionType.WITHDRAWAL, "20.00", None),
        (TransactionType.WITHDRAWAL, "2000000.00", None),
        (TransactionType.TRANSFER, "100000.00", "maria_usd"),
    ):
        transactions.append(Transaction(
            operation, ivan.client_id, Decimal(amount), Currency.RUB,
            sender_id=accounts["ivan"].uuid if operation is not TransactionType.DEPOSIT else None,
            recipient_id=accounts[recipient].uuid if recipient else None,
        ))

    queue = TransactionQueue()
    processor = TransactionProcessor(bank, queue)
    history = {}
    collect_balance_snapshot(accounts, NOW - timedelta(seconds=1), history)
    for index, transaction in enumerate(transactions):
        queue.add(transaction)
        now = NOW + timedelta(seconds=index)
        processor.process_next(now)
        collect_balance_snapshot(accounts, now, history)
    return ReportBuilder(bank, transactions, audit), ivan, maria, history


def test_client_and_bank_reports_match_processed_operations(reporting):
    builder, ivan, maria, _ = reporting
    client = builder.build_client_report(ivan.client_id)
    assert client["full_name"] == "Иван"
    assert client["accounts"][0]["balance"] == "1000020.00"
    assert client["transaction_count"] == 5
    incoming = builder.build_client_report(maria.client_id)
    assert incoming["transaction_count"] == 2
    assert {tx["type"] for tx in incoming["transactions"]} == {"transfer"}
    bank = builder.build_bank_report()
    assert (bank["clients_count"], bank["accounts_count"], bank["transactions_count"]) == (2, 3, 5)
    assert bank["transactions_by_status"] == {"completed": 3, "failed": 2}
    assert bank["transactions_by_type"] == {"deposit": 1, "transfer": 2, "withdrawal": 2}
    assert bank["balances"] == {"RUB": "1000030.00", "USD": "0.00"}
    assert bank["top_3_clients"][0]["client_id"] == ivan.client_id


def test_risk_report_counts_unique_transactions_and_execution_errors(reporting):
    builder, ivan, _, _ = reporting
    blocked = builder.transactions[-1]
    # A later check of the same operation must not count as another transaction
    # or replace its previously observed high risk with a lower level.
    builder.audit.record(
        "WARNING", "risk_analyzed", "Repeated check",
        client_id=ivan.client_id, transaction_id=blocked.id,
        details={"risk_level": "MEDIUM", "score": 1, "reasons": ["new_recipient"]},
    )
    report = builder.build_risk_report()
    assert report["suspicious_count"] == 3
    assert report["medium_risk_count"] == 2
    assert report["high_risk_count"] == 1
    assert report["risk_reasons"] == {"new_recipient": 2, "large_amount": 2}
    assert report["error_statistics"] == {"InsufficientFundsError": 1}


@pytest.mark.parametrize("kind", ["client", "bank", "risk"])
def test_report_exports_preserve_data(reporting, tmp_path, kind):
    builder, ivan, _, _ = reporting
    if kind == "client":
        report = builder.build_client_report(ivan.client_id)
    elif kind == "bank":
        report = builder.build_bank_report()
    else:
        report = builder.build_risk_report()
    directory = tmp_path / "exports"
    builder.export_to_json(report, directory / f"{kind}.json")
    builder.export_to_csv(report, directory / f"{kind}.csv")
    builder.export_to_txt(report, directory / f"{kind}.txt")
    assert json.loads((directory / f"{kind}.json").read_text(encoding="utf-8")) == report
    with (directory / f"{kind}.csv").open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.reader(source))
    assert rows[0] == ["Field", "Value"]
    csv_data = dict(rows[1:])
    text = (directory / f"{kind}.txt").read_text(encoding="utf-8")
    for key, value in report.items():
        if isinstance(value, (dict, list)):
            assert json.loads(csv_data[key]) == value
        else:
            assert csv_data[key] == str(value)
        assert f"{key}:" in text
    if kind == "client":
        assert "Иван" in text


def test_charts_show_actual_balances_and_save_three_pngs(reporting, tmp_path):
    builder, _, _, history = reporting
    before = plt.get_fignums()
    figure = builder.build_balance_history_chart(history, "ivan")
    try:
        assert list(figure.axes[0].lines[0].get_ydata()) == [
            1000000, 1000050, 1000040, 1000020, 1000020, 1000020,
        ]
        assert figure.axes[0].get_ylabel() == "Balance (RUB)"
    finally:
        plt.close(figure)
    directory = tmp_path / "charts"
    builder.save_charts(directory, history, "ivan")
    assert {path.name for path in directory.iterdir()} == {
        "transaction_statuses.png", "client_balances.png", "balance_history.png",
    }
    for path in directory.iterdir():
        pixels = plt.imread(path)
        assert pixels.shape[0] > 0 and pixels.shape[1] > 0
        assert pixels.min() < pixels.max()
    assert plt.get_fignums() == before


def test_demo_exports_all_reports_and_charts(tmp_path, monkeypatch, capsys):
    demo_path = Path(__file__).resolve().parents[1] / "src" / "demo.py"
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(demo_path), run_name="__main__")
    for name in ("client", "bank", "risk"):
        for extension in ("json", "csv", "txt"):
            assert (tmp_path / "reports" / f"{name}.{extension}").stat().st_size > 0
    assert len(list((tmp_path / "reports" / "charts").glob("*.png"))) == 3
    bank = json.loads((tmp_path / "reports" / "bank.json").read_text(encoding="utf-8"))
    assert bank["transactions_count"] == 40
    assert sum(bank["transactions_by_status"].values()) == 40
    assert set(bank["transactions_by_status"]) == {"completed", "failed"}
    assert "Reports and charts saved" in capsys.readouterr().out
