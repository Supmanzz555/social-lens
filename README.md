# social-lens

A local data engineering pipeline that pulls real data from Hacker News, GitHub, and YouTube, streams it through Kafka, processes it with Spark, and stores it in a cloud data lake — all orchestrated by Airflow.

Built as a portfolio project learning how to integrate real ETL tools together.

## What It Does

```
Hacker News API ──┐
GitHub API     ───┼──► Producers ──► Kafka ──► Spark Streaming ──► R2 (bronze)
YouTube API    ──┘                                                         │
                                                                          ▼
Airflow DAGs ──► Spark Batch (bronze→silver→gold) ──► PostgreSQL ◄────────┘
                                                      │
                              ┌───────────────────────┴───────────────────┐
                              ▼                                           ▼
                          dbt models                              ML Pipeline (MLflow)
                              │                                           │
                              ▼                                           ▼
                         Metabase dashboards                    Predictions → Postgres
```

## Progress

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Cloud + Docker | ✅ Complete | Kafka, Postgres, Airflow, Metabase running |
| 2. Kafka Producers | ✅ Complete | 3 producers poll APIs → push to Kafka |
| 3. Spark Streaming | ✅ Complete | Kafka → R2 bronze (partitioned Parquet) |
| 4. Spark Batch | ✅ Complete | bronze→silver→gold→PostgreSQL |
| 5. Airflow DAGs | ✅ Complete | `SparkSubmitOperator` orchestrates everything |
| 6. Data Quality | ⏸️ Planned | Great Expectations validation |
| 7. dbt Models | ⏸️ Planned | SQL transforms staging→marts |
| 8. Metabase | ⏸️ Planned | 5 BI dashboards |
| 9. ML Pipeline | ⏸️ Planned | Train → MLflow → Predict |

## Tech Stack

| What | Tool | Where |
|------|------|-------|
| Streaming | Apache Kafka (KRaft) | Local Docker |
| Processing | PySpark 3.5.1 | Inside Airflow containers (local mode) |
| Orchestration | Airflow 2.9.0 | Local Docker (SparkSubmitOperator) |
| Data Lake | Cloudflare R2 | Cloud (10GB free) |
| Warehouse | PostgreSQL 16 | Local Docker |
| Dashboards | Metabase | Local Docker |
| ML Tracking | MLflow | Local Python process |

**5 containers. ~2.5-3GB RAM total.** No paid services.

## Quick Start

```bash
# 1. Set up credentials
cp .env.example .env
# Edit .env — you need R2 keys, GitHub token, YouTube API key

# 2. Build and start everything (first time only)
docker compose build
docker compose up -d

# 3. Run producers (pushes real data to Kafka)
source .venv/bin/activate
uv run python producers/hackernews_producer.py --limit 10
uv run python producers/github_producer.py --limit 10
uv run python producers/youtube_producer.py --limit 5

# 4. Stream to R2
uv run python spark/streaming/kafka_to_r2.py --duration 30

# 5. Trigger batch pipeline from Airflow
# Open http://localhost:8080 → batch_pipeline → Trigger DAG
```

## Airflow DAGs

| DAG | Schedule | Tasks |
|-----|----------|-------|
| `ingest_streaming` | Every 30 min | 3 producers → Spark streaming |
| `batch_pipeline` | Daily at 2 AM | bronze→silver → silver→gold → gold→Postgres |
| `data_quality` | Manual (triggered) | Validate silver, validate gold |
| `ml_pipeline` | Weekly | Feature gen → train → register → predict |

Spark jobs use `SparkSubmitOperator` with `--master local[*]`. JARs (hadoop-aws, aws-java-sdk, postgres JDBC) are baked into the custom Airflow image (`Dockerfile.airflow`).

## Service URLs

| Service | URL | Login |
|---------|-----|-------|
| Airflow | http://localhost:8080 | admin / admin |
| Metabase | http://localhost:3000 | Set up on first visit |
| MLflow | http://localhost:5000 | Open |
| Kafka | localhost:9092 | No auth |
| PostgreSQL | localhost:5432 | airflow / airflow |

## Project Layout

```
producers/        # Python scripts → Kafka (HN, GitHub, YouTube)
spark/            # PySpark streaming + batch jobs
configs/          # Shared Spark + R2 configuration
airflow/          # DAGs, plugins, logs
  dags/           # batch_pipeline, ingest_streaming, data_quality, ml_pipeline
  plugins/        # Custom operators (legacy, replaced by SparkSubmitOperator)
dbt/              # SQL models (Phase 7)
data_quality/     # Great Expectations configs (Phase 6)
ml/               # MLflow training + prediction (Phase 9)
dashboards/       # Metabase exports (Phase 8)
scripts/          # Verification scripts, MLflow starter
journey_log/      # Every problem, fix, and lesson learned
Dockerfile.airflow# Custom Airflow image with pyspark + JARs pre-baked
```

## Architecture Note

Spark runs in local mode inside the Airflow containers (not on the host). This resolves the orchestration gap where Airflow (Docker) can't trigger host processes. The actual Spark scripts are unchanged — `SparkSubmitOperator` submits them via `spark-submit --master local[*]`. This pattern matches real production setups where Airflow orchestrates and Spark computes separately.

## Why Local Over Cloud?

Most tutorials spin up expensive cloud clusters. This project runs everything on a single machine — same concepts, same code, zero cost. The only thing in the cloud is the data lake (R2), which is free. You can swap in a cloud warehouse later without changing any code.

## Contributing

Yes and feels free to do so.
