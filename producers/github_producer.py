"""Polls GitHub Events API and publishes events to Kafka topic 'github-events'."""

import json
import os
import sys
import time
import logging
import requests
from kafka import KafkaProducer
from kafka.errors import KafkaError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
TOPIC = os.getenv("KAFKA_TOPIC_GITHUB", "github-events")
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS_LOCAL", "localhost:9092")
TOKEN = os.getenv("GITHUB_TOKEN", "")
LAST_ID_FILE = os.path.join(os.path.dirname(__file__), ".gh_last_id")

VALID_TYPES = {
    "PushEvent", "PullRequestEvent", "IssuesEvent",
    "WatchEvent", "ForkEvent", "IssueCommentEvent",
    "PullRequestReviewEvent", "ReleaseEvent",
}


def get_last_id():
    if os.path.exists(LAST_ID_FILE):
        with open(LAST_ID_FILE) as f:
            return f.read().strip()
    return ""


def save_last_id(event_id):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(event_id))


def fetch_public_events(page=1):
    """Fetch public events from GitHub API with pagination."""
    headers = {}
    if TOKEN:
        headers["Authorization"] = f"token {TOKEN}"
        headers["Accept"] = "application/vnd.github.v3+json"

    resp = requests.get(
        f"{GITHUB_API}/events",
        headers=headers,
        params={"page": page, "per_page": 100},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def create_producer():
    return KafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda v: v.encode("utf-8") if v else None,
        retries=5,
        acks="all",
        linger_ms=50,
        batch_size=16384,
    )


def run(limit=None):
    """Poll GitHub API and publish events to Kafka."""
    if not TOKEN:
        logger.warning("No GITHUB_TOKEN set. Rate limit: 60 req/hr (unauthenticated)")

    logger.info("Connecting to Kafka at %s", BOOTSTRAP)
    producer = create_producer()
    logger.info("Connected to Kafka. Topic: %s", TOPIC)

    last_id = get_last_id()
    count = 0
    seen_ids = set()
    page = 1

    while True:
        try:
            events = fetch_public_events(page=page)
        except requests.RequestException as e:
            logger.warning("Failed to fetch GitHub events page %d: %s", page, e)
            break

        if not events:
            break

        for event in events:
            event_id = event.get("id", "")
            if event_id == last_id or event_id in seen_ids:
                continue
            seen_ids.add(event_id)

            if event.get("type") not in VALID_TYPES:
                continue

            message = {
                "id": event["id"],
                "type": event["type"],
                "actor": {
                    "id": event["actor"].get("id"),
                    "login": event["actor"].get("display_login", ""),
                },
                "repo": event["repo"].get("name", ""),
                "created_at": event.get("created_at", ""),
                "payload": event.get("payload", {}),
                "public": event.get("public", True),
            }

            try:
                producer.send(TOPIC, key=event_id, value=message)
                count += 1
                save_last_id(event_id)
                logger.info("Published event %s: %s on %s", event_id, event["type"], message["repo"])
            except KafkaError as e:
                logger.error("Failed to publish event %s: %s", event_id, e)

            if limit and count >= limit:
                break

        if limit and count >= limit:
            break

        page += 1
        if page > 10:
            break

    producer.flush()
    producer.close()
    logger.info("Done. Published %d messages to %s", count, TOPIC)
    return count


if __name__ == "__main__":
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])
    run(limit=limit)
