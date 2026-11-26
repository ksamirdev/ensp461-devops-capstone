# Stage 1: install dependencies into a virtualenv with the full toolchain available
FROM mirror.gcr.io/library/python:3.13-slim AS build
RUN python -m venv /venv
COPY requirements.txt .
RUN /venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 2: runtime image with only the virtualenv and the code; no pip, no compilers, no build cache
FROM mirror.gcr.io/library/python:3.13-slim
# Base image packages are patched at build time so fixed OS CVEs never reach production
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/* \
 && pip uninstall -y pip setuptools wheel 2>/dev/null; useradd --system --uid 10001 textstats
COPY --from=build /venv /venv
WORKDIR /srv/text-stats
COPY service service
USER 10001
ARG RELEASE=dev
ENV RELEASE=${RELEASE} PATH=/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 5000
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=2)"]
# ponytail: one worker because prometheus_client counters are per process; scale with pods instead
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--no-control-socket", "service.web:app"]
