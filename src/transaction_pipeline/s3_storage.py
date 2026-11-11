"""Accès à RustFS par son API compatible S3."""

import logging
import os
import time
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


def create_s3_client():
    """Crée un client S3 configuré pour l'instance RustFS locale."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "pipeline-access"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "pipeline-secret-local"),
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        config=Config(s3={"addressing_style": "path"}),
    )


def ensure_bucket(client, bucket: str, retries: int = 20) -> None:
    """Attend RustFS au démarrage et crée le compartiment s'il manque."""
    for attempt in range(retries):
        try:
            client.head_bucket(Bucket=bucket)
            return
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchBucket", "NotFound"}:
                client.create_bucket(Bucket=bucket)
                return
            if code not in {"500", "503", "SlowDown", "ServiceUnavailable"}:
                raise
        except BotoCoreError:
            pass
        logger.warning("RustFS n'est pas encore prêt (tentative %s/%s).", attempt + 1, retries)
        if attempt + 1 == retries:
            raise RuntimeError("RustFS n'est pas joignable après plusieurs tentatives.")
        time.sleep(min(0.25 * (2 ** attempt), 2))


def upload_files(client, bucket: str, paths: list[str | Path]) -> int:
    """Envoie les fichiers CSV dans le compartiment et retourne leur nombre."""
    ensure_bucket(client, bucket)
    for item in paths:
        path = Path(item)
        client.upload_file(str(path), bucket, path.name)
        print(f"CSV envoyé vers S3 : s3://{bucket}/{path.name}")
    return len(paths)


def list_csv_objects(client, bucket: str) -> list[str]:
    """Retourne les clés CSV présentes dans le compartiment."""
    ensure_bucket(client, bucket)
    response = client.list_objects_v2(Bucket=bucket)
    keys = [item["Key"] for item in response.get("Contents", []) if item["Key"].lower().endswith(".csv")]
    while response.get("IsTruncated"):
        response = client.list_objects_v2(Bucket=bucket, ContinuationToken=response["NextContinuationToken"])
        keys.extend(item["Key"] for item in response.get("Contents", []) if item["Key"].lower().endswith(".csv"))
    return sorted(keys)


def download_with_retry(client, bucket: str, key: str, destination: str | Path, retries: int = 3) -> Path:
    """Télécharge un objet CSV avec reprises en cas d'erreur transitoire."""
    destination = Path(destination)
    for attempt in range(retries):
        try:
            client.download_file(bucket, key, str(destination))
            return destination
        except (BotoCoreError, ClientError, OSError):
            logger.warning(
                "Échec temporaire du téléchargement de %s (tentative %s/%s).",
                key,
                attempt + 1,
                retries,
            )
            if attempt + 1 == retries:
                raise
            time.sleep(0.25 * (2 ** attempt))
    return destination
