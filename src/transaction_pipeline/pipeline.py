"""Chargement des CSV et orchestration en ligne de commande."""

import argparse
import csv
import os
import tempfile
from pathlib import Path

from .generator import generate_csv
from .processing import process_transactions
from .s3_storage import create_s3_client, download_with_retry, list_csv_objects, upload_files
from .storage import initialize_database, persist_file


def load_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run(input_dir: str | Path, database_url: str, storage_mode: str = "local") -> int:
    initialize_database(database_url)
    handled = 0
    if storage_mode == "local":
        for path in sorted(Path(input_dir).glob("*.csv")):
            processed = process_transactions(load_csv(path))
            handled += persist_file(database_url, path, processed)
        return handled

    client = create_s3_client()
    bucket = os.environ.get("S3_BUCKET", "transactions")
    local_paths = sorted(Path(input_dir).glob("*.csv"))
    upload_files(client, bucket, local_paths)
    keys = list_csv_objects(client, bucket)
    with tempfile.TemporaryDirectory(prefix="transaction-pipeline-") as temporary_dir:
        for key in keys:
            downloaded = download_with_retry(client, bucket, key, Path(temporary_dir) / Path(key).name)
            print(f"CSV récupéré depuis S3 : s3://{bucket}/{key}")
            processed = process_transactions(load_csv(downloaded))
            handled += persist_file(database_url, downloaded, processed)
    return handled


def main() -> None:
    parser = argparse.ArgumentParser(description="Générer et traiter des fichiers CSV de transactions")
    parser.add_argument("--input-dir", default="data/incoming")
    parser.add_argument("--generate", action="store_true", help="générer d'abord des CSV d'exemple déterministes")
    parser.add_argument("--generate-only", action="store_true", help="générer les CSV sans lancer leur traitement")
    parser.add_argument("--storage", choices=("local", "s3"), default="local", help="source de stockage des CSV")
    parser.add_argument("--files", type=int, default=2)
    args = parser.parse_args()
    if args.generate_only:
        args.generate = True
    if args.generate:
        generated = generate_csv(args.input_dir, args.files)
        for path in generated:
            print(f"CSV généré : {path}")
    if args.generate_only:
        return
    database_url = os.environ.get("DATABASE_URL", "postgresql://pipeline:pipeline@localhost:5433/transactions")
    count = run(args.input_dir, database_url, args.storage)
    print(f"{count} nouveau(x) fichier(s) CSV inséré(s).")


if __name__ == "__main__":
    main()
