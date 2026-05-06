# social-lens

End-to-end data engineering pipeline: Hacker News, GitHub, and YouTube APIs → Kafka → Spark → Cloudflare R2 → PostgreSQL → dbt → MLflow → Metabase.

Built as a portfolio project. All phases complete.

## Architecture

```
APIs (HN, GH, YT) → Producers → Kafka → Spark Streaming → R2 (bronze)
                                                         → Spark Batch (silver → gold) → PostgreSQL
                                                                                          ├── dbt models
                                                                                          ├── MLflow (train + predict)
                                                                                          └── Metabase dashboard (30 cards)
```

All services run in Docker. $0 cost using free-tier cloud services.

## How It Works

Data flows through 4 layers:

1. **Ingest** — Python producers poll real APIs (Hacker News, GitHub, YouTube), handle rate limits and deduplication, then push JSON messages to Kafka topics.
2. **Process** — Spark Streaming consumes Kafka and writes raw Parquet to Cloudflare R2 (bronze layer). Spark Batch then cleans, deduplicates, and aggregates the data through silver and gold layers.
3. **Store** — Gold tables are loaded into PostgreSQL. dbt transforms them into analytics-ready models (staging → intermediate → marts). The ML pipeline trains XGBoost via MLflow and writes predictions back to Postgres.
4. **Visualize** — Metabase queries Postgres and renders a single dashboard with 30 cards covering pipeline health, engagement metrics, trending topics, creator leaderboards, and ML prediction accuracy.

Every layer has its own quality gate — Great Expectations validates data at the bronze-to-silver transition.

## Tech Stack

| Component | Tool | Where |
|-----------|------|-------|
| Streaming | Kafka (KRaft) | Local Docker |
| Processing | PySpark 3.5.1 | Airflow container (local mode) |
| Orchestration | Airflow 2.9.0 | Local Docker |
| Data Lake | Cloudflare R2 | Cloud (10GB free) |
| Warehouse | PostgreSQL 16 | Local Docker |
| Transforms | dbt Core | CLI |
| ML Tracking | MLflow 2.15.0 | Docker (pre-baked image) |
| BI | Metabase v0.60 | Local Docker |

## Quick Start

```bash
# 1. Configure credentials
cp .env.example .env
# Fill in: R2 keys, GitHub token, YouTube API key

# 2. Start everything
docker compose up -d --build
# Wait ~60s for all services

# 3. Ingest data (host machine)
source .venv/bin/activate
python producers/hackernews_producer.py --limit 25
python producers/github_producer.py --limit 25
python producers/youtube_producer.py --limit 10

# 4. Run batch pipeline
# Airflow UI → http://localhost:8080 (admin/admin) → batch_pipeline → Trigger

# 5. Transform + ML
cd dbt && dbt run && dbt test
cd .. && python ml/generate_synthetic.py && python ml/train_model.py && python ml/predict.py --n 100

# 6. Dashboard
python scripts/setup_metabase.py --email YOUR_EMAIL --password YOUR_PASSWORD
```

## Status

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Cloud + Docker | ✅ | Kafka, Postgres, Airflow, MLflow, Metabase running |
| 2. Kafka Producers | ✅ | 3 producers with dedup, pagination, rate limiting |
| 3. Spark Streaming | ✅ | Kafka → R2 bronze (partitioned Parquet) |
| 4. Spark Batch | ✅ | bronze→silver→gold→PostgreSQL |
| 5. Airflow DAGs | ✅ | 4 DAGs via SparkSubmitOperator |
| 6. Data Quality | ✅ | Great Expectations validation |
| 7. dbt Models | ✅ | 7 models, 2 tests, all passing |
| 8. Metabase | ✅ | Single dashboard, 30 cards, all verified |
| 9. ML Pipeline | ✅ | XGBoost trained, registered, predictions in Postgres |

## Dashboards

Single comprehensive dashboard at `http://localhost:3000` with 30 cards across 6 sections:

- **Pipeline Overview** — Total items, source breakdown, data freshness, layer counts
- **Engagement** — Daily trend, avg score by platform, top items
- **Platform Deep Dive** — HN/GH/YT stats, content breakdown
- **Trending Topics** — Top words, tags, cross-source analysis
- **Creator Leaderboard** — Top creators by score and views
- **ML Predictions** — Predicted vs actual, error metrics, score distribution

## Service URLs

| Service | URL | Login |
|---------|-----|-------|
| Airflow | http://localhost:8080 | admin / admin |
| Metabase | http://localhost:3000 | Setup on first visit |
| MLflow | http://localhost:5000 | Open |
| PostgreSQL | localhost:5432 | airflow / airflow |

## Project Structure

```
producers/          API → Kafka (HN, GH, YT)
spark/              Streaming + batch PySpark jobs
airflow/dags/       4 DAGs orchestrate everything
dbt/                SQL models (staging → marts)
ml/                 ML training + prediction
data_quality/       Great Expectations configs
configs/            Shared R2 + Spark config
scripts/            Setup + verification utilities
journey_log/        Every problem and fix documented
```

See `MASTER_PLAN.md` for full architecture details.

## Restart Guide

```bash
docker compose down -v
docker compose up -d --build
# Wait ~60s
# Then: producers → batch_pipeline (Airflow) → dbt → ML → setup_metabase.py
```

Check `journey_log/` before troubleshooting — most issues are already documented.

## Contributing

Feel free to fork, improve, or use this as a reference for your own projects. Pull requests, issue reports, and suggestions are welcome.
