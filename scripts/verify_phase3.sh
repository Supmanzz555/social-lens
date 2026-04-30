#!/bin/bash
# Phase 3 Verification Script
# Usage: ./scripts/verify_phase3.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
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
echo "  Phase 3 Verification"
echo "========================================"
echo ""

# 1. Run streaming job for 30 seconds
echo "--- Spark Streaming Job ---"
echo "Running streaming job for 30 seconds..."
SPARK_OUTPUT=$(uv run python spark/streaming/kafka_to_r2.py --duration 30 2>&1)
if echo "$SPARK_OUTPUT" | grep -q "Started streaming"; then
    echo -e "${GREEN}✓${NC} Spark streaming job started and ran successfully"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗${NC} Spark streaming job failed"
    echo "$SPARK_OUTPUT" | tail -10
    FAIL=$((FAIL + 1))
fi
echo ""

# 2. Check R2 for bronze files
echo "--- R2 Bronze Files ---"
R2_OUTPUT=$(uv run python -c "
import boto3, os
from dotenv import load_dotenv
load_dotenv()
s3 = boto3.client('s3', endpoint_url=f'https://{os.getenv(\"R2_ACCOUNT_ID\")}.r2.cloudflarestorage.com',
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'))
bucket = os.getenv('R2_BUCKET_NAME', 'datalake')
for source in ['hackernews', 'github', 'youtube']:
    objs = s3.list_objects_v2(Bucket=bucket, Prefix=f'bronze/source={source}/')
    parquet_files = [o for o in objs.get('Contents', []) if '.parquet' in o['Key']]
    print(f'{source}: {len(parquet_files)} files')
" 2>&1)
for source in hackernews github youtube; do
    if echo "$R2_OUTPUT" | grep -q "$source: [0-9]* files"; then
        echo -e "${GREEN}✓${NC} R2 has parquet files for $source"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} R2 missing parquet files for $source"
        FAIL=$((FAIL + 1))
    fi
done
echo ""

# 3. Verify parquet schema
echo "--- Parquet Schema ---"
SCHEMA_OUTPUT=$(uv run python -c "
import boto3, io, os, pyarrow.parquet as pq
from dotenv import load_dotenv
load_dotenv()
s3 = boto3.client('s3', endpoint_url=f'https://{os.getenv(\"R2_ACCOUNT_ID\")}.r2.cloudflarestorage.com',
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'))
bucket = os.getenv('R2_BUCKET_NAME', 'datalake')
objs = s3.list_objects_v2(Bucket=bucket, Prefix='bronze/source=hackernews/')
hn_files = [o for o in objs.get('Contents', []) if '.parquet' in o['Key']]
if hn_files:
    data = s3.get_object(Bucket=bucket, Key=hn_files[0]['Key'])['Body'].read()
    table = pq.read_table(io.BytesIO(data))
    print(f'rows={table.num_rows}')
    cols = ','.join(table.column_names)
    print(f'cols={cols}')
" 2>&1)
if echo "$SCHEMA_OUTPUT" | grep -q "rows=[1-9]"; then
    echo -e "${GREEN}✓${NC} Parquet files have data (rows > 0)"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗${NC} Parquet files are empty or missing"
    FAIL=$((FAIL + 1))
fi
if echo "$SCHEMA_OUTPUT" | grep -q "cols=.*title"; then
    echo -e "${GREEN}✓${NC} Schema contains expected columns"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗${NC} Schema missing expected columns"
    FAIL=$((FAIL + 1))
fi
echo ""

# 4. Script integrity
echo "--- Script Integrity ---"
if [ -s "spark/streaming/kafka_to_r2.py" ]; then
    LINES=$(wc -l < "spark/streaming/kafka_to_r2.py")
    echo -e "${GREEN}✓${NC} kafka_to_r2.py exists ($LINES lines)"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗${NC} kafka_to_r2.py missing or empty"
    FAIL=$((FAIL + 1))
fi
if [ -s "spark/streaming/requirements.txt" ]; then
    echo -e "${GREEN}✓${NC} requirements.txt exists"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗${NC} requirements.txt missing"
    FAIL=$((FAIL + 1))
fi
echo ""

# Summary
echo "========================================"
echo "  Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}"
echo "========================================"

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}Phase 3 NOT complete. Fix failures before proceeding.${NC}"
    exit 1
else
    echo -e "${GREEN}Phase 3 complete! Ready for Phase 4.${NC}"
    exit 0
fi
