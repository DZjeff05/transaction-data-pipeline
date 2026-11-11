"""Démonstration locale du retry après une panne temporaire de PostgreSQL."""

import os
from uuid import uuid4

import psycopg
import pytest

from transaction_pipeline import storage
from transaction_pipeline.generator import generate_csv
from transaction_pipeline.pipeline import load_csv
from transaction_pipeline.processing import process_transactions


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL requis pour le test d'intégration")
def test_reprise_apres_une_erreur_temporaire_de_connexion(tmp_path, monkeypatch):
    database_url = os.environ["DATABASE_URL"]
    storage.initialize_database(database_url)
    path = generate_csv(tmp_path, files=1)[0]
    unique_id = f"TX-{uuid4()}"
    path.write_text(path.read_text(encoding="utf-8").replace("TX-001", unique_id), encoding="utf-8")
    result = process_transactions(load_csv(path))

    connexion_reelle = psycopg.connect
    appels = 0

    def connexion_avec_panne_simulee(*args, **kwargs):
        nonlocal appels
        appels += 1
        if appels == 1:
            print("Panne simulée : PostgreSQL refuse temporairement la première connexion.")
            raise psycopg.OperationalError("Panne temporaire simulée")
        return connexion_reelle(*args, **kwargs)

    monkeypatch.setattr(storage.psycopg, "connect", connexion_avec_panne_simulee)
    assert storage.persist_file(database_url, path, result, retries=3) is True
    assert appels == 2
    monkeypatch.setattr(storage.psycopg, "connect", connexion_reelle)

    with psycopg.connect(database_url) as connection:
        file_hash = connection.execute(
            "SELECT file_hash FROM transactions WHERE transaction_id=%s", (unique_id,)
        ).fetchone()[0]
        count = connection.execute(
            "SELECT count(*) FROM transactions WHERE file_hash=%s", (file_hash,)
        ).fetchone()[0]
    assert count == 7
    print("Retry réussi : 7 transactions insérées une seule fois après 2 tentatives.")
