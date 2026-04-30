# Social Media Data Platform — Hybrid SaaS (All Free)

## Project Overview

An end-to-end data engineering pipeline using **free cloud services** with minimal local resource usage.
Data flows from Hacker News, GitHub, and YouTube APIs through Local Kafka, processed by local
PySpark into Cloudflare R2 (data lake), loaded into Neon PostgreSQL (warehouse), orchestrated by
Apache Airflow (local Docker), validated with Great Expectations, transformed with dbt, and
visualized with Metabase (local).

**One local Docker container for Airflow only. All other services are cloud-hosted and free.**

---

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Hacker News API   │    │ GitHub API   │    │ YouTube API  │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────┐
│              Python Producers (local, lightweight)        │
│  Push API data → Local Kafka                   │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│         Local Kafka (free tier)                │
│  hackernews-posts | github-events | youtube-videos           │
└───────────────────────────┬─────────────────────────────┘
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
┌──────────────────────┐    ┌──────────────────────────┐
│ PySpark Streaming     │    │ PySpark Batch (local)    │
│ (local machine)       │    │ (local machine)          │
│ Kafka → Cloudflare R2 │    │ R2 bronze→silver→gold    │
└──────────┬───────────┘    └──────────┬───────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────────────────────────────────────────┐
│         Cloudflare R2 Data Lake (free, 10GB)             │
│  bronze/  → raw events, partitioned by date              │
│  silver/  → cleaned, deduplicated, typed                 │
│  gold/    → aggregated, business-ready                   │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│         Neon PostgreSQL (free, serverless, 500MB)        │
│  Curated analytics tables for reporting                  │
└───────────────────────────┬─────────────────────────────┘
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
┌──────────────────────┐    ┌──────────────────────┐
│ dbt Core (local CLI)  │    │ Metabase (local) (free)│
│ SQL transforms        │    │ BI & visualization   │
│ inside PostgreSQL     │    │                      │
└──────────────────────┘    └──────────────────────┘

┌─────────────────────────────────────────────────────────┐
│         Apache Airflow (local Docker, 2 containers)      │
│  Schedules producers, Spark jobs, dbt, data quality      │
│  Web UI: http://localhost:8080                           │
└─────────────────────────────────────────────────────────┘
```

**Apache Airflow** orchestrates all pipeline stages. **Great Expectations** validates data at layer transitions.

---

## Services — Cloud vs Local

| Component | Service | Location | Free Tier |
|-----------|---------|----------|-----------|
| **Streaming** | Local Kafka | **Local Docker** | Unlimited |
| **Data Lake** | Cloudflare R2 | Cloud | 10GB, free forever |
| **Warehouse** | Neon PostgreSQL | Cloud | 500MB, free forever |
| **Processing** | PySpark | Local | Open source |
| **Orchestration** | Apache Airflow | **Local Docker** | Open source, fully free |
| **BI** | Metabase | **Local Docker** | Open source, fully free |
| **Quality** | Great Expectations | Local | Open source |
| **Transform** | dbt Core | Local | Open source |
| **ML Tracking** | MLflow | Local | Open source |

**Total local resource usage**: ~3GB (Kafka + Airflow webserver + scheduler + Metabase in Docker + Python processes + MLflow)

---

## Components & What They Do

### 1. Local Kafka — Event Streaming (Docker, KRaft Mode)
- **Purpose**: Kafka running in Docker. Producers send API data here, Spark consumes it.
- **What you learn**: Topics, partitions, producers, consumers, consumer groups, offsets, KRaft mode
- **Resource usage**: ~512MB RAM, runs in Docker alongside Airflow + Metabase
- **Setup**: `docker-compose up -d` starts Kafka automatically, topics auto-create on first use

### 2. PySpark (local) — Distributed Data Processing
- **Purpose**: Processes data in streaming and batch modes using local PySpark
  - **Streaming**: Reads from Local Kafka, writes Parquet to Cloudflare R2
  - **Batch**: Reads R2 bronze → cleans to silver → aggregates to gold → loads to Neon
- **What you learn**: Structured Streaming, DataFrames, Spark SQL, checkpointing, watermarks, S3 connectors
- **Why local**: No need for a cluster at this scale. Same API, same concepts. Lightweight.
- **Install**: `pip install pyspark`

### 3. Cloudflare R2 — Data Lake Storage
- **Purpose**: S3-compatible object storage for raw and processed Parquet files
- **What you learn**: Data lake architecture (bronze/silver/gold), partitioning, file formats, S3 APIs
- **Free tier**: 10GB storage, **no egress fees**, free forever
- **Setup**: Enable R2 → create bucket → create API token → use with `boto3` or Spark `s3a://`

### 4. Neon PostgreSQL — Data Warehouse
- **Purpose**: Serverless PostgreSQL for curated analytics tables
- **What you learn**: Schema design, dimensional modeling, indexing, connection pooling
- **Free tier**: 500MB storage, serverless (scales to zero), free forever
- **Setup**: Create account → create project → get connection string

### 5. Apache Airflow — Workflow Orchestration (Local Docker)
- **Purpose**: Schedules and monitors all pipeline stages — producers, Spark jobs, data quality checks, dbt runs
- **What you learn**: DAG design, operators, sensors, XComs, retries, backfilling, connections management
- **Components**: Webserver + Scheduler (LocalExecutor) — runs in 2 Docker containers
- **Why Airflow**: Industry standard, massive ecosystem, what employers expect
- **How it works locally**: Docker Compose with 2 lightweight containers, uses Neon for metadata DB
- **Install**: `docker-compose up -d` (only Airflow, nothing else)
- **Port**: `8080`
- **Credentials**: admin / admin

### 6. dbt Core — Data Transformations
- **Purpose**: SQL-based transformations inside Neon PostgreSQL
- **What you learn**: Modeling (staging/intermediate/marts), tests, macros, documentation, snapshots
- **Run mode**: CLI on your machine, connects to Neon
- **Install**: `pip install dbt-postgres`

### 7. Great Expectations — Data Quality
- **Purpose**: Validates data at bronze→silver transitions
- **What you learn**: Expectation suites, checkpoints, validation reports, data contracts
- **Run mode**: Python library, triggered via Airflow DAGs
- **Install**: `pip install great-expectations`

### 8. Metabase (local) — Business Intelligence
- **Purpose**: Visualizes final analytics tables as dashboards
- **What you learn**: BI setup, dashboard design, SQL questions, chart types
- **Free tier**: Up to 5 users
- **Setup**: Connect to Neon → build questions → create dashboard

### 9. MLflow — Machine Learning Tracking (Local)
- **Purpose**: Track ML experiments, log model metrics, register production models
- **What you learn**: Experiments, runs, parameters, metrics, artifacts, model registry
- **ML task**: Predict story engagement (score) from features like time, type, title length
- **Training data**: First uses synthetic data for testing, then real pipeline data from `silver/`
- **Run mode**: Local tracking server (`mlflow server`), triggered via Airflow DAG
- **Install**: `pip install mlflow scikit-learn xgboost`

---

## Directory Structure

```
social-media-data-platform/
│
├── .env.example                      # Template for all cloud credentials
├── .gitignore
├── PROJECT_PLAN.md                   # This file
├── README.md                         # Quick start guide
├── docker-compose.yml                # Airflow + Metabase (3 containers)
│
├── producers/                        # Kafka producers (Python, lightweight)
│   ├── hackernews_producer.py            #   Fetch Hacker News posts → Local Kafka
│   ├── github_producer.py            #   Fetch GitHub events → Local Kafka
│   ├── youtube_producer.py           #   Fetch YouTube stats → Local Kafka
│   └── requirements.txt              #   kafka-python, requests
│
├── spark/                            # PySpark jobs (run locally)
│   ├── streaming/
│   │   └── kafka_to_r2.py            #   Kafka → Cloudflare R2 bronze
│   ├── batch/
│   │   ├── bronze_to_silver.py       #   Clean, dedupe → R2 silver
│   │   ├── silver_to_gold.py         #   Aggregate, model → R2 gold
│   │   └── gold_to_neon.py           #   Load gold → Neon PostgreSQL
│   └── requirements.txt              #   pyspark, boto3
│
├── airflow/                          # Airflow DAGs (orchestrates everything)
│   ├── dags/
│   │   ├── ingest_streaming.py       #   Producer + streaming DAG
│   │   ├── batch_pipeline.py         #   Batch Spark jobs DAG
│   │   ├── data_quality.py           #   Great Expectations DAG
│   │   └── ml_pipeline.py            #   Train + predict ML model DAG
│   └── plugins/                      #   Custom operators/hooks
│
├── dbt/                              # dbt transformations
│   ├── dbt_project.yml
│   ├── profiles.yml                  #   Connects to Neon
│   ├── models/
│   │   ├── staging/                  #   Raw → cleaned source models
│   │   ├── intermediate/             #   Business logic joins
│   │   └── marts/                    #   Final analytics tables
│   ├── tests/
│   └── macros/
│
├── data_quality/                     # Great Expectations
│   ├── expectations/
│   │   ├── hackernews_expectations.json
│   │   ├── github_expectations.json
│   │   └── youtube_expectations.json
│   └── checkpoints/
│       └── bronze_to_silver.json
│
├── configs/                          # Shared configuration
│   ├── spark_config.py               #   Spark session + S3 config
│   └── r2_config.py                  #   Cloudflare R2 connection
│
├── ml/                               # ML model training & inference
│   ├── generate_synthetic.py         #   Generate fake Hacker News data for testing ML
│   ├── train_model.py                #   Train models, log to MLflow
│   ├── predict.py                    #   Score new posts with registered model
│   └── requirements.txt              #   mlflow, scikit-learn, xgboost
│
├── dashboards/                       # Metabase exports
    └── engagement_dashboard.json
```

---

## Data Flow

### Streaming Path (Real-Time)
```
APIs → Python Producers (local) → Local Kafka (cloud) → PySpark Streaming (local) → Cloudflare R2 bronze/
```

### Batch Path (Scheduled)
```
R2 bronze/ → PySpark Batch (local) → R2 silver/ → PySpark Batch (local) → R2 gold/ → Neon PostgreSQL
```

### Orchestration (Airflow)
```
DAG: ingest_streaming  → Start producers, run Spark streaming
DAG: batch_pipeline    → bronze→silver→gold→neon (with dependencies)
DAG: data_quality      → Validate at each layer transition
DAG: ml_pipeline       → Train model → MLflow register → Predict → Neon
```

### Transformation (dbt)
```
Neon staging → Neon intermediate → Neon marts
```

### Visualization (Metabase (local))
```
Neon marts → Metabase Questions → Dashboards
```

### Machine Learning (MLflow)
```
R2 silver/ → Feature engineering → MLflow tracking (experiments, runs, metrics)
    → Best model registered → Predict new posts → Scores → Neon → Metabase "predicted vs actual"
```

---

## Data Lake Structure (Cloudflare R2)

```
s3://data-lake/
│
├── bronze/                         # Raw data, as-is from APIs
│   ├── source=hackernews/
│   │   └── date=YYYY-MM-DD/
│   │       └── part-XXXXX.parquet
│   ├── source=github/
│   │   └── date=YYYY-MM-DD/
│   │       └── part-XXXXX.parquet
│   └── source=youtube/
│       └── date=YYYY-MM-DD/
│           └── part-XXXXX.parquet
│
├── silver/                         # Cleaned, typed, deduplicated
│   ├── hackernews/
│   │   └── date=YYYY-MM-DD/
│   ├── github/
│   │   └── date=YYYY-MM-DD/
│   └── youtube/
│       └── date=YYYY-MM-DD/
│
└── gold/                           # Aggregated, business-ready
    ├── content_engagement/
    ├── creator_metrics/
    └── trending_topics/
```

---

## Setup Checklist

### Step 1: Create Cloud Accounts (5 min each)
- [ ] **Local Kafka**: https://N/A (runs locally) → Create Kafka cluster → Note REST URL + Token
- [ ] **Cloudflare R2**: https://dash.cloudflare.com → Enable R2 → Create bucket → Create API token
- [ ] **Neon**: https://neon.tech → Create project → Note connection string
- [ ] **Metabase**: Runs locally in Docker, no account needed

### Step 2: Start Airflow (Local Docker)
```bash
# Only Airflow runs in Docker — just 2 containers
docker-compose up -d

# Access UI at http://localhost:8080 (admin / admin)
```

### Step 3: Install Local Dependencies
```bash
pip install kafka-python pyspark boto3 apache-airflow great-expectations dbt-postgres
```

### Step 4: Configure Credentials
```bash
cp .env.example .env
# Fill in all cloud credentials
```

### Step 5: Verify Connections
```bash
# Test Kafka
python -c "from kafka import KafkaProducer; print('Kafka OK')"

# Test R2
python -c "import boto3; print('R2 OK')"

# Test Neon
python -c "import psycopg2; print('Neon OK')"

# Test Airflow
docker-compose ps
```

---

## What You'll Learn

| Skill Area              | Concepts & Tools                                      |
|------------------------|-------------------------------------------------------|
| **API Integration**    | Pagination, rate limiting, auth, error handling        |
| **Managed Kafka**      | Local Kafka, topics, producers, consumers, ACLs    |
| **Spark**              | Structured Streaming, DataFrames, S3 connectors, checkpointing |
| **Cloud Storage**      | Cloudflare R2, S3 API, Parquet, partitioning strategies |
| **Serverless DB**      | Neon PostgreSQL, connection strings, branching          |
| **Orchestration**      | Apache Airflow, DAGs, operators, sensors, XComs, retries |
| **Data Quality**       | Great Expectations suites, checkpoints, validation     |
| **SQL Modeling**       | dbt models, tests, macros, documentation               |
| **Cloud BI**           | Metabase (local), dashboards, SQL questions              |
| **ML Engineering**     | MLflow, scikit-learn, feature engineering, model registry |

---

## Resource Comparison

| Approach | RAM | Disk | Docker | Cloud Costs |
|----------|-----|------|--------|-------------|
| Local Docker (all services) | 6-8GB | 20GB | 8 containers | $0 |
| **Hybrid SaaS + Airflow** | **~1.5GB** | **~3GB** | **2 containers** | **$0** |
| Oracle VM | 24GB on VM | 200GB on VM | Optional | $0 |

---

## Build Phases

- **Phase 1**: Cloud account setup + Airflow Docker setup
- **Phase 2**: Kafka Producers (Python → Local Kafka)
- **Phase 3**: PySpark Streaming (Kafka → Cloudflare R2)
- **Phase 4**: PySpark Batch (R2 bronze → silver → gold → Neon)
- **Phase 5**: Airflow DAGs (orchestrate the full pipeline)
- **Phase 6**: Data Quality (Great Expectations via Airflow)
- **Phase 7**: dbt Models (SQL transforms on Neon)
- **Phase 8**: Metabase Dashboards (cloud BI)
- **Phase 9**: ML Pipeline (MLflow — synthetic data first, then real pipeline data)
