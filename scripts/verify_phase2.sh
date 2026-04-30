#!/bin/bash
# Phase 2 Verification Script
# Usage: ./scripts/verify_phase2.sh

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
echo "  Phase 2 Verification"
echo "========================================"
echo ""

# 1. Run Hacker News producer
echo "--- Hacker News Producer ---"
HN_OUTPUT=$(uv run python producers/hackernews_producer.py --limit 10 2>&1)
if echo "$HN_OUTPUT" | grep -q "Published.*messages"; then
    echo -e "${GREEN}✓${NC} Hacker News producer ran successfully"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗${NC} Hacker News producer failed"
    echo "$HN_OUTPUT" | tail -5
    FAIL=$((FAIL + 1))
fi
echo ""

# 2. Run GitHub producer
echo "--- GitHub Producer ---"
GH_OUTPUT=$(uv run python producers/github_producer.py --limit 10 2>&1)
if echo "$GH_OUTPUT" | grep -q "Published.*messages"; then
    echo -e "${GREEN}✓${NC} GitHub producer ran successfully"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗${NC} GitHub producer failed"
    echo "$GH_OUTPUT" | tail -5
    FAIL=$((FAIL + 1))
fi
echo ""

# 3. Run YouTube producer
echo "--- YouTube Producer ---"
YT_OUTPUT=$(uv run python producers/youtube_producer.py --limit 5 2>&1)
if echo "$YT_OUTPUT" | grep -q "Published.*messages"; then
    echo -e "${GREEN}✓${NC} YouTube producer ran successfully"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗${NC} YouTube producer failed"
    echo "$YT_OUTPUT" | tail -5
    FAIL=$((FAIL + 1))
fi
echo ""

# 4. Verify messages in Kafka
echo "--- Kafka Message Counts ---"
KAFKA_TOPICS="hackernews-posts github-events youtube-videos"
for topic in $KAFKA_TOPICS; do
    COUNT=$(docker exec kafka /opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic "$topic" 2>/dev/null | awk -F: '{sum+=$3} END {print sum}')
    if [ -n "$COUNT" ] && [ "$COUNT" -gt 0 ]; then
        echo -e "${GREEN}✓${NC} Topic '$topic' has $COUNT messages"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} Topic '$topic' has 0 or unreadable messages"
        FAIL=$((FAIL + 1))
    fi
done
echo ""

# 5. Verify producer scripts exist and are non-empty
echo "--- Script Integrity ---"
for script in hackernews_producer.py github_producer.py youtube_producer.py; do
    if [ -s "producers/$script" ]; then
        LINES=$(wc -l < "producers/$script")
        echo -e "${GREEN}✓${NC} $script exists ($LINES lines)"
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
    echo -e "${RED}Phase 2 NOT complete. Fix failures before proceeding.${NC}"
    exit 1
else
    echo -e "${GREEN}Phase 2 complete! Ready for Phase 3.${NC}"
    exit 0
fi
