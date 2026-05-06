#!/bin/bash
# Phase 4 Verification Script — bronze → silver → gold → local Postgres
# Usage: ./scripts/verify_phase4.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS=0
FAIL=0

echo "========================================"
echo "  Phase 4 Verification"
echo "========================================"
echo ""

# 1. Bronze → Silver
echo "--- Bronze → Silver ---"
echo "Running bronze_to_silver.py..."
cd "$PROJECT_DIR"
B2S_OUTPUT=$(uv run python spark/batch/bronze_to_silver.py 2>&1)
echo "$B2S_OUTPUT" | tail -3

for source in hackernews github youtube; do
    if echo "$B2S_OUTPUT" | grep -q "Wrote silver data for $source"; then
        echo -e "${GREEN}✓${NC} Silver written for $source"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} Silver NOT written for $source"
        FAIL=$((FAIL + 1))
    fi
done
echo ""

# 2. Verify silver data quality
echo "--- Silver Data Quality ---"
SILVER_CHECK=$(uv run python -c "
import boto3, io, os, pyarrow.parquet as pq
from dotenv import load_dotenv
load_dotenv()
s3 = boto3.client('s3',
    endpoint_url=f'https://{os.getenv(\"R2_ACCOUNT_ID\")}.r2.cloudflarestorage.com',
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'))
bucket = os.getenv('R2_BUCKET_NAME', 'datalake')
for source in ['hackernews', 'github', 'youtube']:
    prefix = f'silver/{source}/'
    objs = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    files = [o for o in objs.get('Contents', []) if '.parquet' in o['Key']]
    if files:
        data = s3.get_object(Bucket=bucket, Key=files[0]['Key'])['Body'].read()
        table = pq.read_table(io.BytesIO(data))
        print(f'{source}: rows={table.num_rows}, cols={len(table.column_names)}')
    else:
        print(f'{source}: NO FILES')
" 2>&1)
echo "$SILVER_CHECK"

for source in hackernews github youtube; do
    if echo "$SILVER_CHECK" | grep -q "$source: rows=[1-9]"; then
        echo -e "${GREEN}✓${NC} Silver $source has data"
        PASS=$((PASS + 1))
    else
        echo -e "${YELLOW}⚠${NC} Silver $source has no/empty files"
    fi
done
echo ""

# 3. Silver → Gold
echo "--- Silver → Gold ---"
echo "Running silver_to_gold.py..."
S2G_OUTPUT=$(uv run python spark/batch/silver_to_gold.py 2>&1)
echo "$S2G_OUTPUT" | tail -3

for table in content_engagement creator_metrics trending_topics; do
    if echo "$S2G_OUTPUT" | grep -q "Wrote gold/$table"; then
        echo -e "${GREEN}✓${NC} Gold $table written"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} Gold $table NOT written"
        FAIL=$((FAIL + 1))
    fi
done
echo ""

# 4. Gold → PostgreSQL
echo "--- Gold → PostgreSQL ---"
echo "Running gold_to_postgres.py..."
G2PG_OUTPUT=$(uv run python spark/batch/gold_to_postgres.py 2>&1)
echo "$G2PG_OUTPUT" | tail -5

for pg_table in gold_content_engagement gold_creator_metrics gold_trending_topics; do
    if echo "$G2PG_OUTPUT" | grep -qi "$pg_table\|loaded.*$pg_table\|wrote.*$pg_table"; then
        echo -e "${GREEN}✓${NC} Loaded into $pg_table"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} NOT loaded into $pg_table"
        FAIL=$((FAIL + 1))
    fi
done
echo ""

# 5. Verify data in PostgreSQL
echo "--- PostgreSQL Tables ---"
PG_CHECK=$(uv run python -c "
import psycopg2
conn = psycopg2.connect('postgresql://airflow:airflow@localhost:5432/analytics_db')
cur = conn.cursor()
for table in ['gold_content_engagement', 'gold_creator_metrics', 'gold_trending_topics']:
    cur.execute(f\"SELECT count(*) FROM information_schema.tables WHERE table_name = '{table}'\")
    exists = cur.fetchone()[0]
    if exists:
        cur.execute(f'SELECT count(*) FROM {table}')
        count = cur.fetchone()[0]
        print(f'{table}: {count} rows')
    else:
        print(f'{table}: TABLE NOT FOUND')
conn.close()
" 2>&1)
echo "$PG_CHECK"

for table in gold_content_engagement gold_creator_metrics gold_trending_topics; do
    if echo "$PG_CHECK" | grep -q "$table: [1-9]"; then
        echo -e "${GREEN}✓${NC} $table has data in PostgreSQL"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} $table is empty or missing"
        FAIL=$((FAIL + 1))
    fi
done
echo ""

# 6. Script integrity
echo "--- Script Integrity ---"
for script in bronze_to_silver.py silver_to_gold.py gold_to_postgres.py; do
    if [ -s "spark/batch/$script" ]; then
        lines=$(wc -l < "spark/batch/$script")
        echo -e "${GREEN}✓${NC} $script exists ($lines lines)"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} $script missing or empty"
        FAIL=$((FAIL + 1))
    fi
done
echo ""

# Summary
echo "========================================"
echo "  Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}"
echo "========================================"

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}Phase 4 NOT complete. Fix failures before proceeding.${NC}"
    exit 1
else
    echo -e "${GREEN}Phase 4 complete! Ready for Phase 5.${NC}"
    exit 0
fi
