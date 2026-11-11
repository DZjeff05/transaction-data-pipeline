"""Démonstration du retry lors de la récupération d'un objet depuis RustFS."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from botocore.exceptions import EndpointConnectionError

from transaction_pipeline.s3_storage import create_s3_client, download_with_retry, ensure_bucket


@pytest.mark.skipif(not os.environ.get("S3_ENDPOINT_URL"), reason="S3_ENDPOINT_URL requis pour RustFS")
def test_reprise_apres_une_erreur_temporaire_de_telechargement(tmp_path, monkeypatch):
    client = create_s3_client()
    bucket = os.environ.get("S3_BUCKET", "transactions")
    ensure_bucket(client, bucket)
    key = f"preuve-retry-{uuid4()}.csv"
    body = b"transaction_id,amount\nS3-RETRY,42.00\n"
    client.put_object(Bucket=bucket, Key=key, Body=body)
    vrai_telechargement = client.download_file
    appels = 0

    def telechargement_avec_panne_simulee(bucket_name, object_key, filename, *args, **kwargs):
        nonlocal appels
        appels += 1
        if appels == 1:
            print("Panne simulée : échec temporaire de récupération depuis RustFS.")
            raise EndpointConnectionError(endpoint_url=os.environ["S3_ENDPOINT_URL"])
        return vrai_telechargement(bucket_name, object_key, filename, *args, **kwargs)

    monkeypatch.setattr(client, "download_file", telechargement_avec_panne_simulee)
    destination = download_with_retry(client, bucket, key, tmp_path / Path(key), retries=3)
    assert appels == 2
    assert destination.read_bytes() == body
    client.delete_object(Bucket=bucket, Key=key)
    print("Retry S3 réussi : objet récupéré au deuxième essai.")
