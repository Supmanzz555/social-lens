# Social Media Data Platform — Master Plan

> **Single source of truth** for the entire project. Every component, every decision, every data flow.

---

## Project Goal

Build a production-grade end-to-end data engineering pipeline that ingests data from Hacker News, GitHub, and YouTube APIs, processes it through streaming and batch layers, stores it in a cloud data lake, transforms it into analytics-ready tables, orchestrates the entire pipeline, validates data quality, builds SQL models, visualizes dashboards, and trains an ML model — all using **free cloud services** with **minimal local resources** (~3GB RAM, 6 Docker containers).

---

## Key Decisions Made

| Decision | What We Chose | What We Rejected | Why |
|----------|---------------|------------------|-----|
| **Architecture** | All-in-one Docker (services + Spark in Airflow) | Host scripts, separate Spark cluster | Saves RAM, Airflow has full access to Spark jobs and producers |
| **Kafka** | Local Kafka (Docker, KRaft) | Upstash, Confluent Cloud | Unlimited, no quotas, full control |
| **Data Lake** | Cloudflare R2 | MinIO, AWS S3 | Free forever (10GB), S3-compatible, no egress fees |
| **Warehouse** | Local PostgreSQL (Docker) | Neon, Snowflake | Zero latency, works offline, 200MB RAM |
| **Orchestration** | Apache Airflow (local Docker) | Prefect, Mage | Industry standard, DAG concepts |
| **ML Tracking** | MLflow (Docker, pre-baked image) | MLflow on host, `host.docker.internal` | Pre-baked image avoids slow pip install; Docker network avoids DNS issues |
| **BI** | Metabase (local Docker) | Grafana, Superset | Simple setup, connects to local Postgres |
| **Streaming → Batch** | Staging → commit pattern | Shared bronze path | Spark streaming writes `_spark_metadata/` that breaks batch reads |
| **MLflow Artifacts** | `file:///opt/ml/artifacts` with shared volume | S3 artifact storage | Both Airflow and MLflow mount `./ml:/opt/ml` |
| **Metabase Cards** | Native SQL queries | MBQL queries | MBQL field IDs go stale after table sync; SQL is stable |

---

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Hacker News  │    │ GitHub API   │    │ YouTube API  │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────┐
│         Python Producers (inside Airflow)            │
│  Poll APIs, handle pagination/rate limits → Kafka   │
└───────────────────────────┬─────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────┐
│         Local Kafka (Docker, KRaft)                  │
│  Topics: hackernews-posts | github-events | youtube  │
└───────────────────────────┬─────────────────────────┘
               ┌────────────┴────────────┐
               ▼                         ▼
┌──────────────────────┐    ┌──────────────────────┐
│ PySpark Streaming     │    │ PySpark Batch         │
│ (inside Airflow)      │    │ (inside Airflow)      │
│ Kafka → R2 bronze     │    │ bronze→silver→gold    │
└──────────┬───────────┘    └──────────┬───────────┘
           │                           │
           ▼                           ▼
┌─────────────────────────────────────────────────────┐
│         Cloudflare R2 Data Lake                      │
│  bronze/ → silver/ → gold/ (partitioned Parquet)     │
└───────────────────────────┬─────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────┐
│         Local PostgreSQL (analytics_db)              │
└──────────┬──────────────────────┬───────────────────┘
           │                      │
           ▼                      ▼
┌──────────────────┐    ┌────────────────────────────┐
│ dbt Core          │    │ MLflow (Docker)            │
│ staging→marts     │    │ Train → Register → Predict │
└──────────────────┘    └──────────┬─────────────────┘
           │                       │
           ▼                       ▼
┌─────────────────────────────────────────────────────┐
│         Metabase — Single Dashboard (30 cards)       │
│  Pipeline overview, engagement, platforms, trends,   │
│  creators, ML predictions                            │
└─────────────────────────────────────────────────────┘
```

**6 Docker containers:** Kafka, PostgreSQL, Airflow (webserver + scheduler), MLflow, Metabase.

---

## Data Sources

| Source | Auth | Rate Limit | Polling | Key Fields |
|--------|------|------------|---------|------------|
| **Hacker News** | None | None | Every minute | id, title, by, score, descendants, time, url |
| **GitHub** | PAT | 5,000/hr | Every 15 min | id, type, actor, repo, created_at, payload |
| **YouTube** | API Key | 10,000 units/day | Once/day | videoId, title, channelTitle, viewCount, tags |

---

## Directory Structure (As of 2026-05-06)

```
social-media-data-platform/
├── .env                              # Cloud credentials (gitignored)
├── .env.example                      # Template
├── .gitignore
├── AGENT.md                          # Agent rules
├── MASTER_PLAN.md                    # This file
├── PROJECT_PLAN.md                   # Architecture overview
├── README.md                         # Quick start
│
├── docker-compose.yml                # 6 containers
├── Dockerfile.airflow                # Pre-baked Airflow image (pyspark + JARs)
├── Dockerfile.mlflow                 # Pre-baked MLflow image (mlflow + sklearn + xgboost)
│
├── journey_log/                      # Problem tracking
│   ├── README.md
│   ├── 2026-04-30.md                 # Phase 1-3 issues
│   ├── 2026-05-02.md                 # Phase 4-5 issues
│   ├── 2026-05-03.md                 # E2E test log + issues #1-10
│   ├── 2026-05-03-phase7.md          # dbt implementation
│   ├── 2026-05-03-phase8.md          # Metabase implementation
│   └── 2026-05-06.md                 # MLflow Dockerization + dashboard consolidation
│
├── configs/
│   ├── kafka_topics.json             # Topic definitions
│   ├── r2_config.py                  # R2 S3 connection
│   └── spark_config.py               # Spark session config
│
├── producers/
│   ├── .gh_last_id                   # GH dedup state
│   ├── .hn_last_id                   # HN dedup state
│   ├── .yt_last_video                # YT dedup state
│   ├── hackernews_producer.py        # HN API → Kafka
│   ├── github_producer.py            # GH API → Kafka
│   ├── youtube_producer.py           # YT API → Kafka
│   └── requirements.txt
│
├── spark/
│   ├── streaming/
│   │   ├── kafka_to_r2.py            # Kafka → R2 bronze/staging
│   │   └── checkpoints/              # Spark streaming state
│   ├── batch/
│   │   ├── bronze_to_silver.py       # Clean, dedup, type-cast → R2 silver
│   │   ├── silver_to_gold.py         # Aggregate, join → R2 gold
│   │   └── gold_to_postgres.py       # Load gold → Postgres
│   └── requirements.txt
│
├── airflow/
│   ├── dags/
│   │   ├── ingest_streaming.py       # Producers → Kafka → streaming
│   │   ├── batch_pipeline.py         # bronze→silver→gold→postgres
│   │   ├── data_quality.py           # GE validation (manual trigger)
│   │   └── ml_pipeline.py            # Generate → train → predict
│   ├── plugins/operators/            # (empty — DAGs use BashOperator)
│   ├── data/                         # (unused — Postgres replaced SQLite)
│   └── logs/
│
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/
│   │   ├── schema.yml                # Source definitions + tests
│   │   ├── staging/                  # stg_hackernews, stg_github, stg_youtube
│   │   ├── intermediate/             # int_daily_metrics
│   │   └── marts/                    # fct_daily_engagement, dim_creators, dim_platforms
│   ├── tests/                        # test_positive_scores, test_valid_dates
│   ├── macros/
│   └── target/                       # Compiled SQL + docs
│
├── data_quality/
│   ├── expectations/                 # hackernews, github, youtube expectations
│   └── checkpoints/                  # bronze_to_silver checkpoint
│
├── ml/
│   ├── generate_synthetic.py         # 1000 rows with known patterns
│   ├── train_model.py                # LR, RF, XGBoost → MLflow → register
│   ├── predict.py                    # Score posts → ml_predictions table
│   └── requirements.txt
│
├── scripts/
│   ├── setup_metabase.py             # Auto-create dashboard via API
│   ├── run_data_quality.py           # GE validation on R2 silver data
│   ├── verify_phase1.sh
│   ├── verify_phase2.sh
│   ├── verify_phase3.sh
│   ├── verify_phase4.sh
│   └── mlflow.db                     # MLflow backend store
│
├── postgres/
│   └── init.sql                      # Creates analytics_db
│
├── dashboards/                       # Metabase exports
│   └── .gitkeep
│
└── mlflow.db                         # MLflow backend (root copy)
```

---

## Build Phases

### Phase 1: Cloud Setup + Docker ✅
Kafka, PostgreSQL, Airflow, MLflow, Metabase running. All connection tests pass.

### Phase 2: Kafka Producers ✅
3 Python scripts poll APIs and push messages to Kafka topics. Deduplication, pagination, rate limiting handled.

### Phase 3: PySpark Streaming ✅
Structured Streaming consumes 3 Kafka topics, writes partitioned Parquet to R2 bronze/staging.

### Phase 4: PySpark Batch ✅
bronze→silver (clean, dedup, type-cast) → gold (aggregate, join) → PostgreSQL (load).

### Phase 5: Airflow DAGs ✅
4 DAGs orchestrate the entire pipeline using `SparkSubmitOperator` with `--master local[*]`.

### Phase 6: Data Quality ✅
Great Expectations expectations defined for all 3 sources. Validation embedded in batch_pipeline DAG.

### Phase 7: dbt Models ✅
7 SQL models (3 staging, 1 intermediate, 3 marts). 2 custom tests. All passing.

### Phase 8: Metabase Dashboard ✅
Single comprehensive dashboard with 30 cards across 6 sections. All cards use native SQL queries for reliability.

### Phase 9: ML Pipeline ✅
MLflow Docker container with pre-baked image. XGBoost model trained, registered, predictions written to Postgres.

**ALL PHASES COMPLETE.**

---

## Complete Data Flow — One Hacker News Story

```
1. Producer polls HN API → GET /topstories.json → /item/{id}.json
2. Producer pushes JSON to Kafka topic: hackernews-posts
3. PySpark Streaming reads Kafka → writes Parquet to R2 bronze/source=hackernews/date=2026-05-06/
4. Airflow triggers bronze_to_silver.py → clean, dedup, type-cast → R2 silver/
5. Airflow triggers silver_to_gold.py → aggregate, join with GH/YT → R2 gold/
6. Airflow triggers gold_to_postgres.py → load to local PostgreSQL
7. dbt transforms → staging → intermediate → marts
8. ML Pipeline scores new stories → writes predictions to Postgres
9. Metabase queries Postgres → dashboard shows engagement metrics
```

---

## Resource Requirements

| Resource | Required | Notes |
|----------|----------|-------|
| **RAM** | 3-3.5GB | Kafka 512MB + Postgres 200MB + Airflow 1.5GB + MLflow 256MB + Metabase 512MB |
| **Disk** | ~6GB | Docker images 4.5GB + project files 1.5GB |
| **CPU** | 2 cores | Spark local mode |
| **Docker** | Required | 6 containers |
| **Python** | 3.10+ | All scripts |

---

## Quick Start

```bash
# 1. Configure credentials
cp .env.example .env
# Edit .env — R2 keys, GitHub token, YouTube API key

# 2. Start all containers
docker compose up -d --build

# 3. Run producers (from host)
source .venv/bin/activate
uv run python producers/hackernews_producer.py --limit 10
uv run python producers/github_producer.py --limit 10
uv run python producers/youtube_producer.py --limit 5

# 4. Trigger pipeline in Airflow UI
# http://localhost:8080 (admin/admin) → batch_pipeline → Trigger DAG

# 5. Run dbt
cd dbt && dbt run && dbt test

# 6. Run ML pipeline
cd .. && uv run python ml/generate_synthetic.py
uv run python ml/train_model.py
uv run python ml/predict.py --n 100

# 7. Setup dashboard
python scripts/setup_metabase.py --email YOUR_EMAIL --password YOUR_PASSWORD
```

## Service URLs

| Service | URL | Login |
|---------|-----|-------|
| Airflow | http://localhost:8080 | admin / admin |
| Metabase | http://localhost:3000 | Set up on first visit |
| MLflow | http://localhost:5000 | Open |
| Kafka | localhost:9092 | No auth |
| PostgreSQL | localhost:5432 | airflow / airflow |

## Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| `_spark_metadata/` breaks batch reads | Delete `_spark_metadata/` dirs from R2 bronze after cleaning |
| MBQL cards fail with 403/400 | Use native SQL queries instead — field IDs go stale after sync |
| `pip install` in container command | Pre-bake at build time with Dockerfile — output is buffered, hangs silently |
| `file://` artifacts permission denied | Mount shared volume (`./ml:/opt/ml`) in both client and server containers |
| Airflow DAG not showing | Must be in `airflow/dags/`, have `DAG` object at top level |

---

## What the Finished Project Looks Like

- **Airflow** — 4 DAGs on schedule, green task runs
- **MLflow** — Experiment runs with metrics, best model registered
- **Metabase** — Single dashboard with 30 cards covering the full pipeline
- **R2** — Parquet files in bronze/silver/gold, partitioned by source and date
- **PostgreSQL** — 12 analytics tables, dbt models materialized
- **Kafka** — 3 topics with messages flowing

## Future Enhancements (Optional)

Delta Lake on R2, Grafana + Prometheus monitoring, CI/CD with GitHub Actions, Slack alerting on pipeline failure, model drift monitoring, Spark cluster on EMR/Databricks.
