from decimal import Decimal

from transaction_pipeline.processing import process_transactions


def test_amounts_flags_and_group_totals():
    rows = [
        {"transaction_id": "a", "datetime": "2025-01-01T00:00:00Z", "amount": "5000.00", "iban_origin": "A", "country_source": "FR", "bank_source": "X", "iban_recipient": "B", "country_recipient": "DE"},
        {"transaction_id": "b", "datetime": "2025-01-01T00:00:00Z", "amount": "5000.01", "iban_origin": "A", "country_source": "FR", "bank_source": "X", "iban_recipient": "C", "country_recipient": "ES"},
    ]
    result = process_transactions(rows)
    assert [row["flagged"] for row in result["transactions"]] == [False, True]
    assert result["sent_by_iban"] == {"A": Decimal("10000.01")}
    assert result["sent_by_bank"] == {"X": Decimal("10000.01")}
    assert result["received_by_iban"] == {"B": Decimal("5000.00"), "C": Decimal("5000.01")}
