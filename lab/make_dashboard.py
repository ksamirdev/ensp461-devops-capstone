"""Writes deploy/platform/dashboards/textstats.json, the Grafana dashboard provisioned from Git."""
import json
from pathlib import Path

P = {"type": "prometheus", "uid": "prometheus"}
L = {"type": "loki", "uid": "loki"}


def panel(i, title, kind, x, y, w, h, targets, unit=None, ds=P, **extra):
    p = {"id": i, "title": title, "type": kind, "datasource": ds, "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [dict(refId=chr(65 + n), datasource=ds, **t) for n, t in enumerate(targets)]}
    if unit:
        p["fieldConfig"] = {"defaults": {"unit": unit}, "overrides": []}
    p.update(extra)
    return p


def stat(i, title, x, expr, unit, thresholds, decimals=2):
    return panel(i, title, "stat", x, 0, 4, 5, [{"expr": expr, "instant": True}], unit,
                 fieldConfig={"defaults": {"unit": unit, "decimals": decimals, "thresholds": {
                     "mode": "absolute", "steps": [{"color": c, "value": v} for v, c in thresholds]}}, "overrides": []},
                 options={"colorMode": "background", "graphMode": "area", "reduceOptions": {"calcs": ["lastNotNull"]}})


panels = [
    stat(1, "Requests / s", 0, "textstats:requests:rate5m", "reqps", [(None, "blue")], 1),
    stat(2, "Error ratio", 4, "textstats:error_ratio:rate5m", "percentunit",
         [(None, "green"), (0.01, "orange"), (0.05, "red")]),
    stat(3, "p95 latency", 8, "textstats:latency_p95_seconds:rate5m", "s",
         [(None, "green"), (0.1, "orange"), (0.25, "red")], 3),
    # 99.5% SLO over 30 days: budget = 0.5% of requests may fail
    stat(4, "Error budget", 12,
         "1 - (sum(increase(textstats_http_requests_total{route=\"/stats\",status=~\"5..\"}[30d])) or vector(0)) "
         "/ (0.005 * sum(increase(textstats_http_requests_total{route=\"/stats\"}[30d])))",
         "percentunit", [(None, "red"), (0.25, "orange"), (0.5, "green")], 1),
    stat(5, "Pods up", 16, "count(up{namespace=\"textstats\",app=\"text-stats\"} == 1)", "none", [(None, "red"), (2, "green")], 0),
    stat(6, "Firing alerts", 20, "count(ALERTS{alertstate=\"firing\"}) or vector(0)", "none",
         [(None, "green"), (1, "red")], 0),
    panel(7, "Requests / s by status", "timeseries", 0, 5, 12, 8,
          [{"expr": "sum by (status) (rate(textstats_http_requests_total{route=\"/stats\"}[1m]))", "legendFormat": "{{status}}"}], "reqps"),
    panel(8, "Requests / s by release (canary vs stable)", "timeseries", 12, 5, 12, 8,
          [{"expr": "sum by (rollouts_pod_template_hash) (rate(textstats_http_requests_total{route=\"/stats\"}[1m]))",
            "legendFormat": "pod-template {{rollouts_pod_template_hash}}"}], "reqps"),
    panel(9, "Latency p50 / p95 / p99", "timeseries", 0, 13, 12, 8,
          [{"expr": f"histogram_quantile({q}, sum by (le) (rate(textstats_http_request_duration_seconds_bucket{{route=\"/stats\"}}[1m])))",
            "legendFormat": f"p{int(q * 100)}"} for q in (0.5, 0.95, 0.99)], "s"),
    panel(10, "Replicas: HPA desired vs ready", "timeseries", 12, 13, 12, 8,
          [{"expr": "kube_horizontalpodautoscaler_status_desired_replicas{namespace=\"textstats\"}", "legendFormat": "HPA desired"},
           {"expr": "count(up{namespace=\"textstats\",app=\"text-stats\"} == 1)", "legendFormat": "pods answering"}], "none"),
    panel(11, "CPU per pod (cores)", "timeseries", 0, 21, 12, 8,
          [{"expr": "sum by (pod) (rate(container_cpu_usage_seconds_total{namespace=\"textstats\",container=\"app\"}[1m]))",
            "legendFormat": "{{pod}}"}], "none"),
    panel(12, "Error log lines (Loki)", "logs", 12, 21, 12, 8,
          [{"expr": "{namespace=\"textstats\", app=\"text-stats\", level=~\"error|warning\"}"}], ds=L,
          options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending"}),
]

dashboard = {"uid": "textstats", "title": "text-stats service", "tags": ["capstone"], "timezone": "utc",
             "refresh": "10s", "time": {"from": "now-30m", "to": "now"}, "schemaVersion": 41, "panels": panels}
out = Path(__file__).resolve().parent.parent / "deploy/platform/dashboards/textstats.json"
out.write_text(json.dumps(dashboard, indent=1) + "\n")
print(f"wrote {out} with {len(panels)} panels")
