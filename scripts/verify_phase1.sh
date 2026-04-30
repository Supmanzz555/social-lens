#!/bin/bash
# Phase 1 Verification Script
# Usage: ./scripts/verify_phase1.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS=0
FAIL=0

check() {
    local description="$1"
    local command="$2"
    local expected="$3"

    if eval "$command" 2>/dev/null | grep -q "$expected"; then
        echo -e "${GREEN}✓${NC} $description"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} $description"
        FAIL=$((FAIL + 1))
    fi
}

echo "========================================"
echo "  Phase 1 Verification"
echo "========================================"
echo ""

# 1. Docker containers
echo "--- Docker Containers ---"
check "Kafka container is running" "docker ps --filter name=kafka --filter status=running --format '{{.Status}}'" "Up"
check "Airflow webserver is running" "docker ps --filter name=airflow-webserver --filter status=running --format '{{.Status}}'" "Up"
check "Airflow scheduler is running" "docker ps --filter name=airflow-scheduler --filter status=running --format '{{.Status}}'" "Up"
check "Postgres is running" "docker ps --filter name=postgres --filter status=running --format '{{.Status}}'" "Up"
check "Metabase is running" "docker ps --filter name=metabase --filter status=running --format '{{.Status}}'" "Up"
echo ""

# 2. Kafka
echo "--- Kafka ---"
check "Kafka topics exist" "docker exec kafka /opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092" "hackernews-posts"
check "Kafka topics exist" "docker exec kafka /opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092" "github-events"
check "Kafka topics exist" "docker exec kafka /opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092" "youtube-videos"
echo ""

# 3. Airflow
echo "--- Airflow ---"
check "Airflow health endpoint responds" "curl -s http://localhost:8080/health" '"healthy"'
check "Airflow scheduler is healthy" "curl -s http://localhost:8080/health" '"scheduler"'
echo ""

# 4. Metabase
echo "--- Metabase ---"
check "Metabase health endpoint responds" "curl -s http://localhost:3000/api/health" '"ok"'
echo ""

# 5. PostgreSQL (local)
echo "--- PostgreSQL (Airflow metadata + Analytics DB) ---"
check "Postgres port is open" "ss -tlnp | grep 5432" "5432"
check "airflow database exists" "docker exec postgres psql -U airflow -c '\l'" "airflow"
check "analytics_db database exists" "docker exec postgres psql -U airflow -c '\l'" "analytics_db"
echo ""

# 6. MLflow
echo "--- MLflow ---"
check "MLflow server responds" "curl -s -o /dev/null -w '%{http_code}' http://localhost:5000/" "200"
echo ""

# 7. Cloudflare R2
echo "--- Cloudflare R2 ---"
if command -v uv &> /dev/null; then
    cd "$PROJECT_DIR"
    if uv run python -c "
import boto3, os
from dotenv import load_dotenv
load_dotenv()
s3 = boto3.client('s3', endpoint_url=f'https://{os.getenv(\"R2_ACCOUNT_ID\")}.r2.cloudflarestorage.com',
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'))
s3.list_objects_v2(Bucket=os.getenv('R2_BUCKET_NAME'), MaxKeys=1)
print('OK')
" 2>/dev/null | grep -q "OK"; then
        echo -e "${GREEN}✓${NC} R2 connection successful"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} R2 connection failed"
        FAIL=$((FAIL + 1))
    fi
else
    echo -e "${YELLOW}⚠${NC} uv not found, skipping R2 check"
fi
echo ""

# 8. Local PostgreSQL (Analytics DB — data warehouse)
echo "--- PostgreSQL (Analytics DB) ---"
if command -v uv &> /dev/null; then
    cd "$PROJECT_DIR"
    if uv run python -c "
import psycopg2
conn = psycopg2.connect('postgresql://airflow:airflow@localhost:5432/analytics_db')
cur = conn.cursor()
cur.execute('SELECT 1')
print('OK')
conn.close()
" 2>/dev/null | grep -q "OK"; then
        echo -e "${GREEN}✓${NC} Analytics DB connection successful (local Postgres)"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} Analytics DB connection failed"
        FAIL=$((FAIL + 1))
    fi
else
    echo -e "${YELLOW}⚠${NC} uv not found, skipping Analytics DB check"
fi
echo ""

# Summary
echo "========================================"
echo "  Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}"
echo "========================================"

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}Phase 1 NOT complete. Fix failures before proceeding.${NC}"
    exit 1
else
    echo -e "${GREEN}Phase 1 complete! Ready for Phase 2.${NC}"
    exit 0
fi
