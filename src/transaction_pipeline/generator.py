"""Generate stable CSV inputs for repeatable local runs and CI."""

import csv
from pathlib import Path

FIELDS = [
    "transaction_id",
    "datetime",
    "amount",
    "iban_origin",
    "country_source",
    "bank_source",
    "iban_recipient",
    "country_recipient",
]

ROWS = [
    ("TX-001", "2025-01-10T09:00:00Z", "1200.00", "FR761234", "FR", "BanqueA", "DE893704", "DE"),
    ("TX-002", "2025-01-10T10:15:00Z", "5200.00", "FR761234", "FR", "BanqueA", "ES912100", "ES"),
    ("TX-003", "2025-01-11T12:30:00Z", "800.00", "GB29NWBK", "GB", "BankB", "FR142004", "FR"),
    ("TX-004", "2025-01-11T13:45:00Z", "7500.00", "FR761234", "FR", "BanqueA", "DE893704", "DE"),
    ("TX-005", "2025-01-12T08:20:00Z", "250.00", "DE445001", "DE", "BankC", "FR142004", "FR"),
    ("TX-006", "2025-01-12T16:05:00Z", "3100.00", "GB29NWBK", "GB", "BankB", "ES912100", "ES"),
    ("TX-007", "2025-01-13T11:00:00Z", "5000.00", "DE445001", "DE", "BankC", "FR761234", "FR"),
]


def generate_csv(output_dir: str | Path, files: int = 2) -> list[Path]:
    """Write deterministic files, each containing 5–10 transactions."""
    if files < 1:
        raise ValueError("files must be at least 1")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for number in range(1, files + 1):
        path = directory / f"transactions_{number:03d}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for index in range(7):
                writer.writerow(dict(zip(FIELDS, ROWS[(index + number - 1) % len(ROWS)])))
        paths.append(path)
    return paths
