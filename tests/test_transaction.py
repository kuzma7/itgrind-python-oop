"""Business validation of transaction instructions."""
from decimal import Decimal

import pytest

from src.exceptions import InvalidOperationError
from src.models import Currency
from src.transaction import Transaction, TransactionType


def make_transaction(**changes):
    values = dict(
        transaction_type=TransactionType.TRANSFER,
        client_id="client-1",
        amount=Decimal("5000.00"),
        currency=Currency.RUB,
        sender_id="account-1",
        recipient_id="account-2",
    )
    values.update(changes)
    return Transaction(**values)


@pytest.mark.parametrize("amount", [
    Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"),
])
def test_transaction_requires_positive_finite_amount(amount):
    with pytest.raises(InvalidOperationError, match="Amount must be a positive finite Decimal"):
        make_transaction(amount=amount)


@pytest.mark.parametrize("changes,reason", [
    ({"sender_id": None}, "Transfer requires two different accounts"),
    ({"recipient_id": None}, "Transfer requires two different accounts"),
    ({"recipient_id": "account-1"}, "Transfer requires two different accounts"),
    ({"transaction_type": TransactionType.DEPOSIT}, "Deposit requires a recipient and no sender"),
    ({"transaction_type": TransactionType.DEPOSIT, "sender_id": None, "recipient_id": None},
     "Deposit requires a recipient and no sender"),
    ({"transaction_type": TransactionType.WITHDRAWAL}, "Withdrawal requires a sender and no recipient"),
    ({"transaction_type": TransactionType.WITHDRAWAL, "sender_id": None, "recipient_id": None},
     "Withdrawal requires a sender and no recipient"),
])
def test_operation_requires_correct_sender_and_recipient(changes, reason):
    with pytest.raises(InvalidOperationError, match=reason):
        make_transaction(**changes)


@pytest.mark.parametrize("operation,sender,recipient", [
    (TransactionType.DEPOSIT, None, "account-2"),
    (TransactionType.WITHDRAWAL, "account-1", None),
])
def test_external_fee_flag_is_only_available_for_transfers(operation, sender, recipient):
    with pytest.raises(InvalidOperationError, match="Only transfers can be external"):
        make_transaction(
            transaction_type=operation, sender_id=sender, recipient_id=recipient, is_external=True,
        )
