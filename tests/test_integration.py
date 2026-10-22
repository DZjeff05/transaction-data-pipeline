import os
from uuid import uuid4

import psycopg
import pytest

from transaction_pipeline.generator import generate_csv
from transaction_pipeline.pipeline import run


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL required for integration test")
def test_pipeline_inserts_expected_data_once(tmp_path):
    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        before_transactions = connection.execute("SELECT count(*) FROM transactions").fetchone()[0] if connection.execute("SELECT to_regclass('public.transactions')").fetchone()[0] else 0
        before_files = connection.execute("SELECT count(*) FROM processed_files").fetchone()[0] if connection.execute("SELECT to_regclass('public.processed_files')").fetchone()[0] else 0
        before_flagged = connection.execute("SELECT count(*) FROM transactions WHERE flagged").fetchone()[0] if connection.execute("SELECT to_regclass('public.transactions')").fetchone()[0] else 0
    generate_csv(tmp_path, files=1)
    generated_file = tmp_path / "transactions_001.csv"
    unique_id = f"TX-{uuid4()}"
    generated_file.write_text(generated_file.read_text(encoding="utf-8").replace("TX-001", unique_id), encoding="utf-8")
    assert run(tmp_path, database_url) == 1
    assert run(tmp_path, database_url) == 0
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM transactions").fetchone()[0] == before_transactions + 7
        assert connection.execute("SELECT count(*) FROM transactions WHERE flagged").fetchone()[0] == before_flagged + 2
        file_hash = connection.execute("SELECT file_hash FROM transactions WHERE transaction_id=%s", (unique_id,)).fetchone()[0]
        assert connection.execute("SELECT total FROM sent_by_iban WHERE file_hash=%s AND iban='FR761234'", (file_hash,)).fetchone()[0] == 13900
        assert connection.execute("SELECT count(*) FROM processed_files").fetchone()[0] == before_files + 1
