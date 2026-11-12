# Pipeline de traitement de transactions financières

Projet d’intégration et de déploiement continu : génération de fichiers CSV déterministes, traitement des transactions, stockage relationnel PostgreSQL et stockage objet compatible S3 avec RustFS. La pipeline est conteneurisée et déployée sur une VM EC2 par GitHub Actions.

## Fonctionnalités réalisées

### Niveau 1 — pipeline locale et PostgreSQL

- Génération de plusieurs CSV de transactions reproductibles, avec sept lignes par fichier.
- Séparation du chargement CSV et des transformations métier pures.
- Calcul des sommes envoyées par IBAN d’origine, envoyées par banque et reçues par IBAN.
- Signalement des transactions dont le montant dépasse strictement 5 000.
- Insertion atomique dans PostgreSQL et stockage des agrégats.
- Détection des fichiers déjà traités par empreinte SHA-256, pour éviter les doublons lors d’un rejeu.
- Retry des erreurs transitoires de connexion PostgreSQL.
- Tests unitaires, tests d’intégration et démonstrations locales d’échec et de retry.

### Niveau 2 — stockage S3 local avec RustFS

- RustFS est lancé en conteneur et expose une API compatible S3.
- Les CSV locaux peuvent être envoyés vers un bucket RustFS.
- Le traitement récupère les objets depuis RustFS avant de les lire et de les insérer dans PostgreSQL.
- Les erreurs temporaires de téléchargement sont réessayées avec une attente progressive.
- Le client boto3 utilise une adresse d’API personnalisée et le mode d’adressage par chemin.

### Niveau 3 — déploiement Docker sur EC2

- Une image Docker empaquette l’application Python.
- Docker Compose déploie PostgreSQL, RustFS et un worker sur la VM EC2.
- Le worker recherche périodiquement de nouveaux CSV dans RustFS ; l’intervalle est réglable avec `POLL_SECONDS` (60 secondes par défaut).
- Après le succès de la CI sur `main`, le workflow CD déploie la stack sur la VM via un runner GitHub auto-hébergé.
- PostgreSQL n’a pas de port publié ; les ports hôte RustFS sont liés à `127.0.0.1`.

## Architecture

```text
Générateur CSV ──> RustFS (S3) ──> Worker périodique ──> Traitements Python ──> PostgreSQL
                                      ▲                        │
                                      └──── retry téléchargement┘

Push sur main ──> GitHub Actions CI ──> runner auto-hébergé EC2 ──> Docker Compose
```

En local, les CSV peuvent aussi être traités directement depuis le système de fichiers pour les scénarios du niveau 1.

## Structure du dépôt

```text
.
├── .github/workflows/
│   ├── ci.yml                 # CI : tests PostgreSQL et RustFS
│   └── deploy-ec2.yml         # CD après une CI réussie sur main
├── deploy/
│   └── .env.prod.example      # modèle de configuration, sans secrets
├── docs & Captures/           # preuves des niveaux 1, 2 et 3
├── src/transaction_pipeline/
│   ├── generator.py           # génération des CSV déterministes
│   ├── pipeline.py            # chargement, orchestration et CLI
│   ├── processing.py          # transformations pures
│   ├── s3_storage.py          # accès RustFS/S3 et retry téléchargement
│   └── storage.py             # schéma et persistance PostgreSQL
├── tests/
│   ├── test_processing.py     # tests unitaires de traitement
│   ├── test_integration.py    # vérification des insertions PostgreSQL
│   ├── test_retry.py          # retry PostgreSQL simulé
│   └── test_s3_retry.py       # retry de téléchargement RustFS simulé
├── Dockerfile
├── docker-compose.yml         # environnement local
├── docker-compose.prod.yml    # stack de production EC2
└── pyproject.toml
```

## Exécuter le projet en local

### Prérequis

- Python 3.11 ou supérieur.
- Docker avec Docker Compose.

Depuis PowerShell, à la racine du dépôt :

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
docker compose up -d postgres rustfs
```

Compose lance PostgreSQL sur `localhost:5433`, l’API S3 RustFS sur `localhost:9000` et sa console sur `localhost:9001`. Les identifiants Compose sont réservés à l’environnement local.

Configure les variables de connexion pour le terminal courant :

```powershell
$env:DATABASE_URL = "postgresql://pipeline:pipeline@127.0.0.1:5433/transactions"
$env:S3_ENDPOINT_URL = "http://localhost:9000"
$env:S3_ACCESS_KEY = "pipeline-access"
$env:S3_SECRET_KEY = "pipeline-secret-local"
$env:S3_BUCKET = "transactions"
```

### Générer des CSV et les traiter localement

Génération seule :

```powershell
transaction-pipeline --generate-only --input-dir data/demo-local
Get-ChildItem data/demo-local
Get-Content data/demo-local/transactions_001.csv
```

Traitement local et insertion PostgreSQL :

```powershell
transaction-pipeline --input-dir data/demo-local
```

Relancer cette dernière commande doit indiquer qu’aucun nouveau fichier n’a été inséré, car les mêmes contenus ont déjà été traités.

### Envoyer et traiter les CSV depuis RustFS

```powershell
transaction-pipeline --generate --storage s3 --input-dir data/demo-s3 --files 2
```

La commande génère les CSV dans le dossier indiqué comme zone de préparation, les envoie dans `s3://transactions`, liste les objets et les récupère depuis RustFS avant traitement. Le code ne lit donc pas les fichiers de préparation pour le traitement métier : il télécharge les objets depuis S3.

La console RustFS locale est accessible à `http://localhost:9001`. Le service accepte également les commandes boto3 via `S3_ENDPOINT_URL`.

### Tests locaux

Avec PostgreSQL et RustFS démarrés et les variables ci-dessus définies :

```powershell
pytest -q
```

Pour voir séparément les simulations de retry :

```powershell
pytest -s -o log_cli=true --log-cli-level=WARNING tests/test_retry.py
pytest -s -o log_cli=true --log-cli-level=WARNING tests/test_s3_retry.py
```

Les tests d’intégration nécessitent les services correspondants. `test_integration.py` est ignoré si `DATABASE_URL` n’est pas défini ; `test_s3_retry.py` est ignoré si `S3_ENDPOINT_URL` n’est pas défini.

### Reproduire un échec du traitement

Ce scénario corrompt volontairement un CSV d’exemple :

```powershell
transaction-pipeline --generate-only --input-dir data/demo-echec
$p = "data/demo-echec/transactions_001.csv"
$csv = (Get-Content $p -Raw).Replace("1200.00", "montant-invalide")
[IO.File]::WriteAllText((Resolve-Path $p), $csv, [Text.UTF8Encoding]::new($false))
transaction-pipeline --input-dir data/demo-echec
```

Le traitement échoue lors de la conversion du montant en `Decimal`. Le fichier est volontairement modifié ; générer un nouveau CSV pour revenir à des données valides.

## Schéma PostgreSQL et idempotence

Les tables créées par l’application sont :

| Table | Contenu |
| --- | --- |
| `processed_files` | Empreinte SHA-256 et nom de chaque contenu traité |
| `transactions` | Transactions et indicateur de montant supérieur à 5 000 |
| `sent_by_iban` | Totaux envoyés par IBAN d’origine et par fichier |
| `sent_by_bank` | Totaux envoyés par banque source et par fichier |
| `received_by_iban` | Totaux reçus par IBAN et par fichier |

L’enregistrement du fichier, des transactions et des agrégats est effectué dans une transaction PostgreSQL. La contrainte unique sur l’empreinte évite de retraiter le même contenu, même si le fichier est renommé ou si le traitement est relancé.

Les montants sont manipulés avec `Decimal`. Le flag est activé si le montant est **strictement supérieur** à `5000.00`.

## CI et artefacts GitHub Actions

Le workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) se déclenche sur `push` et `pull_request`. Il démarre PostgreSQL, lance RustFS avec Docker Compose, génère et traite des CSV via S3, puis exécute la suite `pytest`.

Les CSV de l’exécution sont conservés dans un artefact nommé `transaction-csv-<run_id>`. Pour le récupérer, ouvrir l’exécution sous **Actions**, puis télécharger l’artefact.

## Déploiement EC2

Le déploiement de production utilise [`docker-compose.prod.yml`](docker-compose.prod.yml), [`Dockerfile`](Dockerfile) et le workflow [`.github/workflows/deploy-ec2.yml`](.github/workflows/deploy-ec2.yml).

Le workflow CD attend une CI réussie sur la branche `main`, puis s’exécute sur un runner auto-hébergé portant le label `ec2-deploy`. Il construit l’image et exécute :

```bash
sudo docker compose --env-file /opt/transaction-pipeline/.env.prod -f docker-compose.prod.yml up -d --build
```

### Préparer la VM

La VM EC2 doit disposer de Docker Engine, du plugin Docker Compose, de Git et du runner GitHub auto-hébergé. Dans le dépôt GitHub, ajouter le runner depuis **Settings → Actions → Runners** et lui donner le label `ec2-deploy`.

Sur la VM, créer `/opt/transaction-pipeline/.env.prod` à partir de [`deploy/.env.prod.example`](deploy/.env.prod.example). Générer des secrets uniques pour PostgreSQL et RustFS ; ne pas committer ni partager ce fichier. Restreindre ses permissions :

```bash
sudo chmod 600 /opt/transaction-pipeline/.env.prod
```

La stack de production ne publie pas le port PostgreSQL. L’API S3 RustFS (`9000`) et sa console (`9001`) sont liées à l’interface locale de la VM ; les règles réseau AWS ne doivent pas les exposer publiquement. Le groupe de sécurité conserve SSH limité à l’adresse IP d’administration.

Une fois la stack déployée, vérifier les conteneurs et les journaux :

```bash
sudo docker ps
sudo docker logs --tail 30 transaction-pipeline-worker-1
```

Le worker parcourt le bucket toutes les `POLL_SECONDS` (60 secondes par défaut). Les fichiers déjà traités sont ignorés grâce à leur empreinte SHA-256.

## Preuves et captures

Les captures associées au projet sont conservées dans `docs & Captures/`.

### Niveau 1 — fichiers locaux, PostgreSQL, échecs et retry

**Génération locale :**

![CSV déterministe généré localement](docs%20%26%20Captures/niveau1_01_generation_csv.PNG)

**Échec de traitement provoqué par un montant invalide :**

![Échec du traitement CSV](docs%20%26%20Captures/niveau1_02_echec_traitement.PNG)

**Retry PostgreSQL réussi :**

![Retry insertion PostgreSQL](docs%20%26%20Captures/niveau1_03_retry_insertion.PNG)

**Insertion locale et rejeu idempotent :**

![Pipeline locale et idempotence](docs%20%26%20Captures/niveau1_04_pipeline_locale_et_idempotence.PNG)

**Suite de tests locale et CI GitHub :**

![Tests locaux du niveau 1](docs%20%26%20Captures/niveau1_05_tests_locaux.PNG)

![CI GitHub du niveau 1](docs%20%26%20Captures/niveau1_06_ci_github_actions.png)

### Niveau 2 — RustFS et S3

![RustFS démarré en local](docs%20%26%20Captures/niveau2_01_rustfs_demarre.PNG)

![CSV envoyés et traités depuis S3](docs%20%26%20Captures/niveau2_02_upload_et_traitement_depuis_s3.PNG)

![Objets CSV présents dans RustFS](docs%20%26%20Captures/niveau2_03_objets_dans_rustfs.PNG)

![Retry de téléchargement S3](docs%20%26%20Captures/niveau2_04_retry_telechargement_s3.PNG)

![Rejeu S3 sans doublons](docs%20%26%20Captures/niveau2_05_reexecution_sans_doublons_s3.PNG)

![Tests locaux du niveau 2](docs%20%26%20Captures/niveau2_06_tests_locaux.PNG)

![CI GitHub du niveau 2](docs%20%26%20Captures/niveau2_07_ci_github_actions.PNG)

### Niveau 3 — déploiement EC2 et worker

![Docker installé sur la VM](docs%20%26%20Captures/niveau3_01_docker_installe_vm.PNG)

![Runner GitHub EC2 en ligne](docs%20%26%20Captures/niveau3_02_runner_ec2_online.PNG)

![CI GitHub avant le CD](docs%20%26%20Captures/niveau3_02_ci_github_actions.png)

![Déploiement CD sur EC2 réussi](docs%20%26%20Captures/niveau3_03_cd_ec2_success.png)

![Conteneurs actifs sur EC2](docs%20%26%20Captures/niveau3_04_conteneurs_ec2.PNG)

![Worker exécuté périodiquement](docs%20%26%20Captures/niveau3_05_worker_periodique.PNG)
