# Social Media Data Platform

End-to-end data engineering project using **free cloud services** with **Airflow** for orchestration.

## Stack

| Component | Service | Location | Cost |
|-----------|---------|----------|------|
| Streaming | Apache Kafka | **Local Docker** | Open source |
| Processing | PySpark | Local | Open source |
| Data Lake | Cloudflare R2 | Cloud | 10GB free |
| Warehouse | Neon PostgreSQL | Cloud | 500MB free |
| Orchestration | Apache Airflow | **Local Docker** | Open source |
| BI | Metabase | **Local Docker** | Open source |
| Quality | Great Expectations | Local | Open source |
| Transform | dbt Core | Local | Open source |

**Local resource usage: ~3GB RAM, 4 Docker containers (Kafka, Airflow x2, Metabase).**

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Fill in cloud credentials (see MASTER_PLAN.md for setup)

# 2. Start Docker (Kafka + Airflow + Metabase)
docker-compose up -d

# 3. Install Python dependencies
pip install -r producers/requirements.txt
pip install -r spark/requirements.txt
pip install -r ml/requirements.txt

# 4. Create Kafka topics
docker exec kafka kafka-topics.sh --create --topic hackernews-posts --bootstrap-server localhost:9092
docker exec kafka kafka-topics.sh --create --topic github-events --bootstrap-server localhost:9092
docker exec kafka kafka-topics.sh --create --topic youtube-videos --bootstrap-server localhost:9092

# 5. Run producers
python producers/hackernews_producer.py

# 6. Run Spark streaming
python spark/streaming/kafka_to_r2.py

# 7. Run batch pipeline
python spark/batch/bronze_to_silver.py
python spark/batch/silver_to_gold.py
python spark/batch/gold_to_neon.py

# 8. Run dbt transforms
cd dbt && dbt run
```

## Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Kafka | Docker container | N/A (localhost:9092) |
| Cloudflare R2 | https://dash.cloudflare.com | Your account |
| Neon PostgreSQL | https://console.neon.tech | Your account |
| Airflow UI | http://localhost:8080 | admin / admin |
| Metabase | http://localhost:3000 | Setup on first visit |
| MLflow UI | http://localhost:5000 | No auth needed |

## Documentation

See `MASTER_PLAN.md` for full architecture, every component, data flow, setup checklist, all 9 build phases with verification steps, and troubleshooting.

## API Keys

- **Hacker News**: https://hacker-news.firebaseio.com/v0/ (no auth needed)
- **GitHub**: https://github.com/settings/tokens
- **YouTube**: https://console.cloud.google.com/apis
