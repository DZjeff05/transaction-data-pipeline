# Pipeline de transactions — niveau 1

Pipeline Python déterministe : génération CSV, transformations pures, PostgreSQL, insertion atomique et CI GitHub Actions.

## Lancer en local

Prérequis : Python 3.11+ et Docker avec Compose.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
docker compose up -d postgres
transaction-pipeline --generate
```

La configuration locale par défaut est `postgresql://pipeline:pipeline@localhost:5433/transactions`. Elle peut être remplacée avec `DATABASE_URL`.

Les mêmes fichiers peuvent être rejoués sans doublonner : leur SHA-256 est enregistré dans `processed_files` et les données, agrégats compris, sont insérés dans une transaction PostgreSQL. Les erreurs de connexion sont réessayées jusqu'à trois fois avec attente progressive.

## Données et schéma

Chaque CSV contient sept transactions stables, dont des montants au-dessus et exactement égaux au seuil de 5 000. Les fonctions de lecture et de traitement sont séparées. Les montants utilisent `Decimal`.

Le schéma stocke les transactions et les agrégats « envoyés par IBAN », « envoyés par banque » et « reçus par IBAN ». L'intégration vérifie les valeurs en base et le rejeu sans doublon.

## CI

GitHub Actions démarre PostgreSQL comme service, installe le projet et exécute les tests unitaires et d'intégration à chaque push et pull request.
