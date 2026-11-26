import json
import logging

import pytest

from service import web
from service.web import app, text_stats


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(web, "DATABASE_URL", None)
    monkeypatch.setattr(web, "FAULT_RATE", 0.0)
    monkeypatch.setattr(web, "FAULT_LATENCY_MS", 0.0)
    return app.test_client()


def test_healthz_reports_healthy(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json["healthy"] is True


def test_readyz_without_database_is_ready(client):
    assert client.get("/readyz").json == {"ready": True, "release": web.RELEASE}


def test_home_reports_release(client):
    body = client.get("/").json
    assert body["service"] == "text-stats"
    assert body["release"] == web.RELEASE


def test_text_stats_counts_unique_words_case_insensitively():
    assert text_stats("Build test build") == {"characters": 16, "words": 3, "unique_words": 2, "sentences": 1}


@pytest.mark.parametrize("text, sentences", [
    ("", 0), ("one", 1), ("One. Two!", 2), ("Is it? Yes. And more", 3), ("Wait... what?!", 2), ("v1.1.0 ships.", 1),
])
def test_text_stats_counts_sentences(text, sentences):
    assert text_stats(text)["sentences"] == sentences


def test_stats_endpoint_returns_counts(client):
    response = client.post("/stats", json={"text": "ship it"})
    assert response.status_code == 200
    assert response.json == {"characters": 7, "words": 2, "unique_words": 2, "sentences": 1}


@pytest.mark.parametrize("body", [{}, {"text": 42}])
def test_stats_endpoint_rejects_invalid_text(client, body):
    assert client.post("/stats", json=body).status_code == 400


def test_analyses_needs_a_database(client):
    assert client.get("/analyses").status_code == 404


def test_fault_rate_fails_requests(client, monkeypatch):
    monkeypatch.setattr(web, "FAULT_RATE", 1.0)
    assert client.post("/stats", json={"text": "x"}).status_code == 500


def test_fault_latency_slows_requests(client, monkeypatch):
    monkeypatch.setattr(web, "FAULT_LATENCY_MS", 30.0)
    client.post("/stats", json={"text": "slow"})
    body = client.get("/metrics").get_data(as_text=True)
    # the 30 ms request lands above the 25 ms bucket
    assert 'textstats_http_request_duration_seconds_bucket{le="0.05",route="/stats"}' in body


def test_metrics_expose_requests_and_release(client):
    client.get("/")
    body = client.get("/metrics").get_data(as_text=True)
    assert 'textstats_http_requests_total{method="GET",route="/",status="200"}' in body
    assert f'textstats_build_info{{release="{web.RELEASE}"}} 1.0' in body


def test_unknown_urls_share_one_metric_label(client):
    client.get("/no-such-page")
    body = client.get("/metrics").get_data(as_text=True)
    assert 'route="unmatched"' in body
    assert "no-such-page" not in body


def test_request_id_is_echoed(client):
    assert client.get("/", headers={"X-Request-ID": "abc123"}).headers["X-Request-ID"] == "abc123"
    assert len(client.get("/").headers["X-Request-ID"]) == 16


def test_requests_are_logged_as_json(client, caplog):
    handler = web.log.handlers[0]
    with caplog.at_level(logging.INFO, logger="textstats"):
        web.log.addHandler(caplog.handler)
        client.post("/stats", json={"text": "log me"}, headers={"X-Request-ID": "req-1"})
        web.log.removeHandler(caplog.handler)
    entry = json.loads(handler.format(caplog.records[-1]))
    assert entry["msg"] == "request"
    assert entry["level"] == "info"
    assert entry["request_id"] == "req-1"
    assert entry["route"] == "/stats"
    assert entry["status"] == 200
    assert entry["release"] == web.RELEASE


def test_probes_are_not_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger="textstats"):
        web.log.addHandler(caplog.handler)
        client.get("/healthz")
        web.log.removeHandler(caplog.handler)
    assert caplog.records == []


def test_bodies_over_100_kb_are_rejected(client):
    assert client.post("/stats", json={"text": "x" * 200_000}).status_code == 413
    assert client.post("/stats", json={"text": "x" * 50_000}).status_code == 200
