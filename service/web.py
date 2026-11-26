"""Text statistics API for the ENSP461 capstone: Flask + PostgreSQL, Prometheus metrics, JSON logs."""
import json
import logging
import os
import random
import re
import time
import uuid

import psycopg
from flask import Flask, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

RELEASE = os.environ.get("RELEASE", "dev")
DATABASE_URL = os.environ.get("DATABASE_URL")
# Fault injection used to prove that canary analysis and alerts catch a bad release:
# FAULT_RATE is the share of /stats requests that fail, FAULT_LATENCY_MS is added to every /stats request.
FAULT_RATE = float(os.environ.get("FAULT_RATE", "0"))
FAULT_LATENCY_MS = float(os.environ.get("FAULT_LATENCY_MS", "0"))

app = Flask(__name__)

REQUESTS = Counter(
    "textstats_http_requests_total", "HTTP requests served", ["method", "route", "status"]
)
LATENCY = Histogram(
    "textstats_http_request_duration_seconds",
    "Request latency",
    ["route"],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
BUILD_INFO = Gauge("textstats_build_info", "Running release", ["release"])
BUILD_INFO.labels(RELEASE).set(1)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so the log pipeline can filter on fields instead of parsing text."""

    def format(self, record):
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "release": RELEASE,
        }
        entry.update(getattr(record, "fields", {}))
        return json.dumps(entry)


log = logging.getLogger("textstats")
log.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
_handler.formatter.converter = time.gmtime
log.addHandler(_handler)
log.propagate = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id bigserial PRIMARY KEY,
    characters integer NOT NULL,
    words integer NOT NULL,
    release text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""


def db():
    # ponytail: one connection per request; psycopg_pool if connection setup shows up in latency
    return psycopg.connect(DATABASE_URL, connect_timeout=3)


_schema_ready = False


def ensure_schema():
    """Create the table once per process; an advisory lock stops pods that start together from racing."""
    global _schema_ready
    if not _schema_ready:
        with db() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(461)")
            conn.execute(SCHEMA)
        _schema_ready = True


SENTENCE_END = re.compile(r"[.!?]+(?:\s|$)")


def text_stats(text):
    words = text.split()
    return {
        "characters": len(text),
        "words": len(words),
        "unique_words": len({w.lower() for w in words}),
        # a trailing fragment without punctuation still counts as a sentence
        "sentences": len(SENTENCE_END.findall(text)) + (1 if text.strip() and not SENTENCE_END.search(text.rstrip() + " ") else 0),
    }


@app.before_request
def start_timer():
    g.started = time.perf_counter()
    g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]


@app.after_request
def observe(response):
    response.headers["X-Request-ID"] = g.request_id
    if request.path == "/metrics":
        return response
    # url_rule, not path, so unknown URLs cannot create unbounded label values
    route = request.url_rule.rule if request.url_rule else "unmatched"
    elapsed = time.perf_counter() - g.started
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    LATENCY.labels(route).observe(elapsed)
    if route in ("/healthz", "/readyz"):
        return response  # probes every 2 s would drown the useful lines
    level = logging.ERROR if response.status_code >= 500 else (
        logging.WARNING if response.status_code >= 400 else logging.INFO)
    log.log(level, "request", extra={"fields": {
        "request_id": g.request_id, "method": request.method, "route": route,
        "status": response.status_code, "duration_ms": round(elapsed * 1000, 2),
        "pod": os.environ.get("HOSTNAME", ""),
    }})
    return response


@app.get("/")
def home():
    return jsonify(service="text-stats", release=RELEASE, pod=os.environ.get("HOSTNAME", ""))


@app.get("/healthz")
def healthz():
    """Liveness: the process answers. Never touches the database, so a DB outage does not restart pods."""
    return jsonify(healthy=True, release=RELEASE)


@app.get("/readyz")
def readyz():
    """Readiness: the pod can do real work, including writing to its database."""
    if DATABASE_URL:
        try:
            ensure_schema()
            with db() as conn:
                conn.execute("SELECT 1")
        except psycopg.Error as exc:
            return jsonify(ready=False, error=type(exc).__name__), 503
    return jsonify(ready=True, release=RELEASE)


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.post("/stats")
def stats():
    if FAULT_LATENCY_MS:
        time.sleep(FAULT_LATENCY_MS / 1000)
    if FAULT_RATE and random.random() < FAULT_RATE:  # nosec B311 - fault injection, not security
        log.error("injected fault", extra={"fields": {"request_id": g.request_id, "fault": "FAULT_RATE"}})
        return jsonify(error="injected fault"), 500
    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    if not isinstance(text, str):
        return jsonify(error="JSON field 'text' must be a string"), 400
    result = text_stats(text)
    if DATABASE_URL:
        try:
            ensure_schema()
            with db() as conn:
                row = conn.execute(
                    "INSERT INTO analyses (characters, words, release) VALUES (%s, %s, %s) RETURNING id",
                    (result["characters"], result["words"], RELEASE),
                ).fetchone()
            result["id"] = row[0]
        except psycopg.Error as exc:
            log.error("database write failed", extra={"fields": {
                "request_id": g.request_id, "error": type(exc).__name__}})
            return jsonify(error="database unavailable"), 503
    return jsonify(result)


@app.get("/analyses")
def analyses():
    if not DATABASE_URL:
        return jsonify(error="no database configured"), 404
    try:
        ensure_schema()
        with db() as conn:
            count, last_id = conn.execute("SELECT count(*), coalesce(max(id), 0) FROM analyses").fetchone()
    except psycopg.Error:
        return jsonify(error="database unavailable"), 503
    return jsonify(count=count, last_id=last_id)
