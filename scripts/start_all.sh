#!/usr/bin/env bash
# Start all services and verify they're healthy.
# Usage: bash scripts/start_all.sh [--reset] [--setup-metabase]
#
# --reset: Stop containers, remove volumes, start fresh
# --setup-metabase: Run Metabase setup after containers are healthy

set -e

cd "$(dirname "$0")/.."

RESET=false
SETUP_METABASE=false
EMAIL="maenratm@gmail.com"
PASSWORD="manrat123"

for arg in "$@"; do
    case $arg in
        --reset) RESET=true ;;
        --setup-metabase) SETUP_METABASE=true ;;
        --email=*) EMAIL="${arg#*=}" ;;
        --password=*) PASSWORD="${arg#*=}" ;;
    esac
done

# ─── Step 1: Stop/Reset ────────────────────────────────────────
if $RESET; then
    echo "=== Stopping all containers ==="
    docker compose down
    echo "=== Removing volumes ==="
    docker compose down -v
    echo "=== Starting fresh ==="
fi

# ─── Step 2: Start containers ─────────────────────────────────
echo "=== Starting containers ==="
docker compose up -d

# ─── Step 3: Wait for health checks ───────────────────────────
echo "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U airflow -q 2>/dev/null; then
        echo "PostgreSQL ready"
        break
    fi
    echo "  Waiting... ($i/30)"
    sleep 2
done

echo "Waiting for Kafka..."
for i in $(seq 1 30); do
    if docker compose exec -T kafka bash -c 'echo > /dev/tcp/localhost/9092' 2>/dev/null; then
        echo "Kafka ready"
        break
    fi
    echo "  Waiting... ($i/30)"
    sleep 2
done

echo "Waiting for Airflow..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8080/health | grep -q '"status": "healthy"'; then
        echo "Airflow ready"
        break
    fi
    echo "  Waiting... ($i/60)"
    sleep 2
done

echo "Waiting for Metabase..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:3000/api/health | grep -q '"status":"ok"'; then
        echo "Metabase ready"
        break
    fi
    echo "  Waiting... ($i/60)"
    sleep 2
done

# ─── Step 4: Verify Metabase can resolve postgres ─────────────
echo "Verifying Metabase → PostgreSQL connectivity..."
METABASE_NET=$(docker inspect metabase --format='{{json .NetworkSettings.Networks}}' 2>/dev/null | python3 -c "
import json, sys
nets = json.load(sys.stdin)
if 'social-media-data-platform_data-platform' in nets:
    print('ok')
else:
    print('missing')
" 2>/dev/null || echo "error")

if [ "$METABASE_NET" = "missing" ]; then
    echo "  Connecting Metabase to data-platform network..."
    docker network connect social-media-data-platform_data-platform metabase 2>/dev/null || true
elif [ "$METABASE_NET" = "error" ]; then
    echo "  WARNING: Could not inspect Metabase container"
else
    echo "  Metabase already on data-platform network"
fi

# ─── Step 5: Setup Metabase ────────────────────────────────────
if $SETUP_METABASE; then
    echo ""
    echo "=== Setting up Metabase ==="
    
    # Get setup token if needed
    TOKEN=$(curl -sf http://localhost:3000/api/session/properties | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('setup-token', ''))
" 2>/dev/null)

    if [ -n "$TOKEN" ]; then
        echo "  Creating admin account..."
        SETUP_RESP=$(curl -sf -X POST http://localhost:3000/api/setup \
            -H "Content-Type: application/json" \
            -d "{
                \"token\": \"$TOKEN\",
                \"user\": {\"email\": \"$EMAIL\", \"first_name\": \"Admin\", \"last_name\": \"Admin\", \"password\": \"$PASSWORD\"},
                \"prefs\": {\"site_name\": \"Social Media Data Platform\", \"site_locale\": \"en\"},
                \"database\": null,
                \"invite\": null
            }" 2>/dev/null || echo "{}")
        
        if echo "$SETUP_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if 'id' in d else 1)" 2>/dev/null; then
            echo "  Admin account created"
            sleep 5
        fi
    fi

    # Run setup script
    uv run python scripts/setup_metabase.py --email "$EMAIL" --password "$PASSWORD"
fi

# ─── Step 6: Summary ───────────────────────────────────────────
echo ""
echo "=== Services ==="
echo "  Kafka:     :9092"
echo "  PostgreSQL: :5432 (airflow/airflow)"
echo "  Airflow:    http://localhost:8080 (admin/admin)"
echo "  Metabase:   http://localhost:3000 ($EMAIL/$PASSWORD)"
echo ""
docker compose ps
