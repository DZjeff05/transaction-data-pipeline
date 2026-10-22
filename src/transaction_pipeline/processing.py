"""Pure transformations for transaction records."""

from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Mapping

THRESHOLD = Decimal("5000.00")


def process_transactions(rows: Iterable[Mapping[str, str]]) -> dict:
    """Return normalized transactions and grouped totals without side effects."""
    transactions = []
    sent_by_iban: dict[str, Decimal] = defaultdict(Decimal)
    sent_by_bank: dict[str, Decimal] = defaultdict(Decimal)
    received_by_iban: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        amount = Decimal(row["amount"]).quantize(Decimal("0.01"))
        transaction = {**row, "amount": amount, "flagged": amount > THRESHOLD}
        transactions.append(transaction)
        sent_by_iban[row["iban_origin"]] += amount
        sent_by_bank[row["bank_source"]] += amount
        received_by_iban[row["iban_recipient"]] += amount
    return {
        "transactions": transactions,
        "sent_by_iban": dict(sent_by_iban),
        "sent_by_bank": dict(sent_by_bank),
        "received_by_iban": dict(received_by_iban),
    }
