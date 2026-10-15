from collections import Counter
from datetime import datetime, timedelta, timezone, tzinfo
from decimal import Decimal

from src.exceptions import InvalidOperationError
from src.models import DEFAULT_BANK_TIMEZONE
from src.transaction import Transaction, TransactionType


class RiskAnalyzer:
    """Apply four educational rules to withdrawals and transfers."""

    LARGE_AMOUNT_RUB = Decimal("100000")

    def __init__(self, bank_timezone: tzinfo = DEFAULT_BANK_TIMEZONE):
        self.bank_timezone = bank_timezone
        self.history: list[dict] = []
        self._operation_times: dict[str, dict[str, datetime]] = {}
        self._known_recipients: dict[str, set[tuple]] = {}

    @staticmethod
    def _recipient_key(transaction: Transaction) -> tuple:
        if transaction.is_external:
            recipient = transaction.external_recipient
            return "external", recipient.bank_code, recipient.account_number
        return "internal", transaction.recipient_id

    def analyze(self, transaction: Transaction, now: datetime, amount_in_rub: Decimal) -> dict:
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise InvalidOperationError("Risk analysis time must include a timezone")
        if not isinstance(amount_in_rub, Decimal) or not amount_in_rub.is_finite() or amount_in_rub <= 0:
            raise InvalidOperationError("Risk analysis requires a positive RUB equivalent")
        if transaction.transaction_type is TransactionType.DEPOSIT:
            return {"score": 0, "level": "LOW", "reasons": []}

        now = now.astimezone(timezone.utc)
        operations = self._operation_times.setdefault(transaction.client_id, {})
        operations.setdefault(transaction.id, now)
        recent_count = sum(now - timedelta(minutes=1) < started <= now for started in operations.values())
        reasons = []
        score = 0
        if amount_in_rub >= self.LARGE_AMOUNT_RUB:
            reasons.append("large_amount")
            score += 2
        if recent_count >= 6:
            reasons.append("frequent_operations")
            score += 2
        if transaction.transaction_type is TransactionType.TRANSFER:
            known = self._known_recipients.get(transaction.client_id, set())
            if self._recipient_key(transaction) not in known:
                reasons.append("new_recipient")
                score += 1
        if 0 <= now.astimezone(self.bank_timezone).hour < 5:
            reasons.append("night_operation")
            score += 1

        level = "LOW" if score == 0 else "MEDIUM" if score < 3 else "HIGH"
        result = {"score": score, "level": level, "reasons": reasons}
        self.history.append({
            "timestamp": now,
            "client_id": transaction.client_id,
            "transaction_id": transaction.id,
            "score": score,
            "level": level,
            "reasons": reasons.copy(),
        })
        return result

    def remember_success(self, transaction: Transaction) -> None:
        if transaction.transaction_type is TransactionType.TRANSFER:
            known = self._known_recipients.setdefault(transaction.client_id, set())
            known.add(self._recipient_key(transaction))

    def get_client_risk_profile(self, client_id: str) -> dict:
        entries = [entry for entry in self.history if entry["client_id"] == client_id]
        unique_ids = {entry["transaction_id"] for entry in entries}
        suspicious = {entry["transaction_id"] for entry in entries if entry["level"] != "LOW"}
        blocked = {entry["transaction_id"] for entry in entries if entry["level"] == "HIGH"}
        reasons_by_transaction: dict[str, set[str]] = {}
        for entry in entries:
            reasons_by_transaction.setdefault(entry["transaction_id"], set()).update(entry["reasons"])
        reasons = Counter(reason for values in reasons_by_transaction.values() for reason in sorted(values))
        return {
            "client_id": client_id,
            "checked_transactions": len(unique_ids),
            "suspicious_transactions": len(suspicious),
            "blocked_transactions": len(blocked),
            "last_risk_level": entries[-1]["level"] if entries else None,
            "common_reasons": dict(reasons.most_common()),
        }
