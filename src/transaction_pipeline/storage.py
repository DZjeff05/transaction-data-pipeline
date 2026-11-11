"""Schéma PostgreSQL et persistance transactionnelle idempotente."""

import hashlib
import logging
import time
from pathlib import Path

import psycopg

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_files (
    file_hash TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS transactions (
    file_hash TEXT NOT NULL REFERENCES processed_files(file_hash),
    transaction_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    iban_origin TEXT NOT NULL,
    country_source TEXT NOT NULL,
    bank_source TEXT NOT NULL,
    iban_recipient TEXT NOT NULL,
    country_recipient TEXT NOT NULL,
    flagged BOOLEAN NOT NULL,
    PRIMARY KEY(file_hash, transaction_id)
);
CREATE TABLE IF NOT EXISTS sent_by_iban (
    file_hash TEXT NOT NULL REFERENCES processed_files(file_hash), iban TEXT NOT NULL,
    total NUMERIC(16,2) NOT NULL, PRIMARY KEY(file_hash, iban)
);
CREATE TABLE IF NOT EXISTS sent_by_bank (
    file_hash TEXT NOT NULL REFERENCES processed_files(file_hash), bank TEXT NOT NULL,
    total NUMERIC(16,2) NOT NULL, PRIMARY KEY(file_hash, bank)
);
CREATE TABLE IF NOT EXISTS received_by_iban (
    file_hash TEXT NOT NULL REFERENCES processed_files(file_hash), iban TEXT NOT NULL,
    total NUMERIC(16,2) NOT NULL, PRIMARY KEY(file_hash, iban)
);
"""


def initialize_database(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(SCHEMA)


def persist_file(database_url: str, path: str | Path, result: dict, retries: int = 3) -> bool:
    """Enregistre un fichier atomiquement ; retourne False si son contenu est déjà traité."""
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for attempt in range(retries):
        try:
            with psycopg.connect(database_url) as connection:
                inserted = connection.execute(
                    "INSERT INTO processed_files(file_hash,file_name) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING file_hash",
                    (digest, path.name),
                ).fetchone()
                if inserted is None:
                    return False
                for row in result["transactions"]:
                    connection.execute(
                        "INSERT INTO transactions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (digest, row["transaction_id"], row["datetime"], row["amount"], row["iban_origin"],
                         row["country_source"], row["bank_source"], row["iban_recipient"],
                         row["country_recipient"], row["flagged"]),
                    )
                for table, key, values in (
                    ("sent_by_iban", "iban", result["sent_by_iban"]),
                    ("sent_by_bank", "bank", result["sent_by_bank"]),
                    ("received_by_iban", "iban", result["received_by_iban"]),
                ):
                    with connection.cursor() as cursor:
                        cursor.executemany(
                            f"INSERT INTO {table}(file_hash,{key},total) VALUES (%s,%s,%s)",
                            [(digest, group, total) for group, total in values.items()],
                        )
            return True
        except (psycopg.OperationalError, psycopg.InterfaceError):
            logger.warning(
                "Échec temporaire de connexion lors de l'insertion de %s (tentative %s/%s).",
                path.name,
                attempt + 1,
                retries,
            )
            if attempt + 1 == retries:
                raise
            time.sleep(0.25 * (2 ** attempt))
    return False
