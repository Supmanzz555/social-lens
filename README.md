# data-pipeline-lab

A local data engineering pipeline that pulls real data from Hacker News, GitHub, and YouTube, streams it through Kafka, processes it with Spark, and stores it in a cloud data lake — all running on a laptop with under 3GB of RAM.

Built as a portfolio project and learning how to integrating ETL tools together 

## What It Does

```
Hacker News API ──┐
GitHub API     ───┼──► Python Producers ──► Kafka ──► Spark Streaming ──► R2 (bronze)
YouTube API    ──┘
```

1. **Producers** poll 3 APIs and push JSON messages to Kafka topics
2. **Spark Streaming** reads those topics and writes partitioned Parquet to Cloudflare R2
3. **Airflow** orchestrates the whole pipeline on a schedule
4. **Metabase** connects to the warehouse and builds dashboards

## Tech Stack

| What | Tool | Where |
|------|------|-------|
| Streaming | Apache Kafka (KRaft) | Local Docker |
| Processing | PySpark | Local (your terminal) |
| Orchestration | Airflow | Local Docker |
| Data Lake | Cloudflare R2 | Cloud (10GB free) |
| Warehouse | PostgreSQL | Local Docker |
| Dashboards | Metabase | Local Docker |
| ML Tracking | MLflow | Local Python process |

**5 containers. ~2.5GB RAM total.** No paid services.

## Quick Start

```bash
# 1. Set up credentials
cp .env.example .env
# Edit .env — you need R2 keys, GitHub token, YouTube API key
# Hacker News needs nothing.

# 2. Start everything
docker compose up -d
uv venv
uv pip install pyspark==3.5.1 kafka-python requests pyarrow python-dotenv
bash scripts/start_mlflow.sh

# 3. Run producers (pushes real data to Kafka)
uv run python producers/hackernews_producer.py --limit 10
uv run python producers/github_producer.py --limit 10
uv run python producers/youtube_producer.py --limit 5

# 4. Stream to R2 (runs for 30 seconds, writes Parquet)
uv run python spark/streaming/kafka_to_r2.py --duration 30

# 5. Verify everything
bash scripts/verify_phase1.sh
bash scripts/verify_phase2.sh
bash scripts/verify_phase3.sh
```

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
airflow/          # DAGs and plugins (empty — Phase 5)
scripts/          # Start MLflow, verify each phase
postgres/         # DB init script (creates warehouse)
```

## Why Local Over Cloud?

Most tutorials spin up expensive cloud clusters. This project runs everything on a single machine by design — same concepts, same code, zero cost. The only thing in the cloud is the data lake (R2), which is free. You can swap in a cloud warehouse later without changing any code.

## Learn More

The `journey_log/` folder (local only) records every problem we hit and how we fixed it — from Kafka topic persistence to Spark memory tuning. It's the honest part of the project.
