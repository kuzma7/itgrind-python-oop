import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

from src.audit_log import AuditLog
from src.bank import Bank
from src.models import Currency
from src.transaction import Transaction


class ReportBuilder:
    def __init__(self, bank: Bank, transactions: list[Transaction], audit: AuditLog):
        self.bank = bank
        self.transactions = transactions
        self.audit = audit

    def build_client_report(self, client_id: str) -> dict:
        if client_id not in self.bank._clients:
            raise ValueError("Client not found")

        client = self.bank._clients[client_id]
        accounts = self.bank.search_accounts(client_id=client_id)

        account_data = []
        for account in accounts:
            account_data.append({
                "account_id": account.uuid,
                "type": type(account).__name__,
                "balance": str(account._balance),
                "currency": account.currency.value,
                "status": account.account_status.value,
            })

        account_ids = set(client.account_ids)
        transactions = []

        for transaction in self.transactions:
            if (transaction.client_id == client_id
                    or transaction.sender_id in account_ids
                    or transaction.recipient_id in account_ids):
                transactions.append({
                    "transaction_id": transaction.id,
                    "type": transaction.transaction_type.value,
                    "amount": str(transaction.amount),
                    "currency": transaction.currency.value,
                    "status": transaction.status.value,
                    "fee": str(transaction.fee),
                    "failure_reason": transaction.failure_reason,
                })

        return {
            "client_id": client.client_id,
            "full_name": client.full_name,
            "status": client.status.value,
            "accounts": account_data,
            "transaction_count": len(transactions),
            "transactions": transactions,
        }

    def build_bank_report(self) -> dict:
        status_counts = Counter(tx.status.value for tx in self.transactions)
        type_counts = Counter(tx.transaction_type.value for tx in self.transactions)

        balances = {
            currency.value: str(amount)
            for currency, amount in self.bank.get_total_balance().items()
        }

        top_clients = []
        for client, balance in self.bank.get_clients_ranking(Currency.RUB)[:3]:
            top_clients.append({
                "client_id": client.client_id,
                "full_name": client.full_name,
                "balance": str(balance),
                "currency": "RUB",
            })

        return {
            "bank_name": self.bank.name,
            "clients_count": len(self.bank._clients),
            "accounts_count": len(self.bank._accounts),
            "transactions_count": len(self.transactions),
            "transactions_by_status": dict(status_counts),
            "transactions_by_type": dict(type_counts),
            "balances": balances,
            "top_3_clients": top_clients,
        }

    def build_risk_report(self) -> dict:
        suspicious_events = self.audit.get_suspicious_operations()
        suspicious_transactions = {}

        for event in suspicious_events:
            transaction_id = event["transaction_id"]
            details = event["details"]

            if transaction_id not in suspicious_transactions:
                suspicious_transactions[transaction_id] = {
                    "transaction_id": transaction_id,
                    "client_id": event["client_id"],
                    "risk_level": details["risk_level"],
                    "score": details["score"],
                    "reasons": details["reasons"].copy(),
                }
            else:
                current = suspicious_transactions[transaction_id]

                if details["score"] > current["score"]:
                    current["score"] = details["score"]
                    current["risk_level"] = details["risk_level"]

                current["reasons"] = sorted(set(current["reasons"]) | set(details["reasons"]))

        risk_counts = Counter(item["risk_level"] for item in suspicious_transactions.values())
        reason_counts = Counter()

        for item in suspicious_transactions.values():
            reason_counts.update(item["reasons"])

        return {
            "suspicious_count": len(suspicious_transactions),
            "medium_risk_count": risk_counts["MEDIUM"],
            "high_risk_count": risk_counts["HIGH"],
            "risk_reasons": dict(reason_counts),
            "suspicious_transactions": list(suspicious_transactions.values()),
            "error_statistics": self.audit.get_error_statistics(),
        }

    def export_to_json(self, report: dict, file_path: str) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=4, default=str)

    def export_to_csv(self, report: dict, file_path: str) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Field", "Value"])

            for key, value in report.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False, default=str)

                writer.writerow([key, value])

    def build_text_report(self, report: dict) -> str:
        lines = []

        for key, value in report.items():
            if isinstance(value, (dict, list)):
                formatted = json.dumps(value, ensure_ascii=False, indent=2, default=str)
                lines.append(f"{key}:\n{formatted}")
            else:
                lines.append(f"{key}: {value}")

        return "\n\n".join(lines)

    def export_to_txt(self, report: dict, file_path: str) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.build_text_report(report), encoding="utf-8")

    def build_transaction_pie_chart(self):
        statuses = Counter(tx.status.value for tx in self.transactions)

        if not statuses:
            raise ValueError("No transactions to visualize")

        fig, ax = plt.subplots(figsize=(7, 5))
        ax.pie(statuses.values(), labels=statuses.keys(), autopct="%1.1f%%", startangle=90)
        ax.set_title("Transaction statuses")
        fig.tight_layout()

        return fig

    def build_client_bar_chart(self):
        ranking = self.bank.get_clients_ranking(Currency.RUB)[:3]

        if not ranking:
            raise ValueError("No clients to visualize")

        names = [client.full_name for client, balance in ranking]
        balances = [float(balance) for client, balance in ranking]

        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(names, balances)
        ax.set_title("Top 3 clients by RUB balance")
        ax.set_ylabel("Balance (RUB)")
        ax.tick_params(axis="x", rotation=15)
        fig.tight_layout()

        return fig

    def build_balance_history_chart(self, history: dict, account_name: str):
        snapshots = history.get(account_name)
        if not snapshots:
            raise ValueError("No balance history for account")

        timestamps = [item["timestamp"] for item in snapshots]
        balances = [float(item["balance"]) for item in snapshots]
        currency = snapshots[0]["currency"]

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.step(timestamps, balances, where="post", marker="o")
        ax.set_title(f"Balance history: {account_name}")
        ax.set_xlabel("Time")
        ax.set_ylabel(f"Balance ({currency})")
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        fig.tight_layout()
        return fig

    def save_charts(self, directory: str | Path, history: dict, account_name: str) -> None:
        """Save three PNG charts and close each figure after saving."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        for filename, build_chart in (
            ("transaction_statuses.png", self.build_transaction_pie_chart),
            ("client_balances.png", self.build_client_bar_chart),
            ("balance_history.png", lambda: self.build_balance_history_chart(history, account_name)),
        ):
            figure = build_chart()
            try:
                figure.savefig(directory / filename, dpi=150)
            finally:
                plt.close(figure)
