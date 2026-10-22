"""Chargement des CSV et orchestration en ligne de commande."""

import argparse
import csv
import os
from pathlib import Path

from .generator import generate_csv
from .processing import process_transactions
from .storage import initialize_database, persist_file


def load_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run(input_dir: str | Path, database_url: str) -> int:
    initialize_database(database_url)
    handled = 0
    for path in sorted(Path(input_dir).glob("*.csv")):
        processed = process_transactions(load_csv(path))
        handled += persist_file(database_url, path, processed)
    return handled


def main() -> None:
    parser = argparse.ArgumentParser(description="Générer et traiter des fichiers CSV de transactions")
    parser.add_argument("--input-dir", default="data/incoming")
    parser.add_argument("--generate", action="store_true", help="générer d'abord des CSV d'exemple déterministes")
    parser.add_argument("--files", type=int, default=2)
    args = parser.parse_args()
    if args.generate:
        generate_csv(args.input_dir, args.files)
    database_url = os.environ.get("DATABASE_URL", "postgresql://pipeline:pipeline@localhost:5432/transactions")
    count = run(args.input_dir, database_url)
    print(f"{count} nouveau(x) fichier(s) CSV inséré(s).")


if __name__ == "__main__":
    main()
