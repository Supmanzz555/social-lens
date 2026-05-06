"""Polls Hacker News Firebase API and publishes posts to Kafka topic 'hackernews-posts'."""

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

HN_API = "https://hacker-news.firebaseio.com/v0"
TOPIC = os.getenv("KAFKA_TOPIC_HACKERNEWS", "hackernews-posts")
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS_LOCAL", "localhost:9092")
LAST_ID_FILE = os.path.join(os.path.dirname(__file__), ".hn_last_id")


def get_last_id():
    """Return last successfully published item ID."""
    if os.path.exists(LAST_ID_FILE):
        with open(LAST_ID_FILE) as f:
            return int(f.read().strip())
    return 0


def save_last_id(item_id):
    """Persist last published item ID."""
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(item_id))


def fetch_item(item_id):
    """Fetch a single HN item by ID."""
    resp = requests.get(f"{HN_API}/item/{item_id}.json", timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_story_ids(sort="top"):
    """Fetch list of story IDs (top / new / best)."""
    resp = requests.get(f"{HN_API}/{sort}stories.json", timeout=10)
    resp.raise_for_status()
    return resp.json()


def create_producer():
    """Create and return a Kafka producer."""
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
    """Poll HN API and publish new items to Kafka."""
    logger.info("Connecting to Kafka at %s", BOOTSTRAP)
    producer = create_producer()
    logger.info("Connected to Kafka. Topic: %s", TOPIC)

    last_id = get_last_id()
    count = 0
    seen_ids = set()

    for sort in ("top", "new"):
        story_ids = fetch_story_ids(sort)
        for item_id in story_ids:
            if item_id <= last_id:
                continue
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            try:
                item = fetch_item(item_id)
            except requests.RequestException as e:
                logger.warning("Failed to fetch item %s: %s", item_id, e)
                continue

            if item and item.get("type") == "story":
                message = {
                    "id": item["id"],
                    "title": item.get("title", ""),
                    "type": item.get("type"),
                    "by": item.get("by", ""),
                    "score": item.get("score", 0),
                    "descendants": item.get("descendants", 0),
                    "time": item.get("time", 0),
                    "url": item.get("url", ""),
                    "text": item.get("text", "")[:500] if item.get("text") else "",
                }

                try:
                    producer.send(TOPIC, key=str(item["id"]), value=message)
                    count += 1
                    save_last_id(item["id"])
                    logger.info("Published item %s: %s", item["id"], item.get("title", "")[:60])
                except KafkaError as e:
                    logger.error("Failed to publish item %s: %s", item["id"], e)

            if limit and count >= limit:
                break

        if limit and count >= limit:
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
