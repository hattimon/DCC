FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DCC_UPDATER_DATA=/data \
    DCC_UPDATER_AUTO_UPDATE_ON_START=1 \
    DCC_UPDATER_SELF_UPDATE_ON_START=1

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

ARG TARGETARCH
ARG COMPOSE_VERSION=5.6.1
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && set -eu; \
    case "$TARGETARCH" in \
      amd64) compose_arch=x86_64; compose_sha=47737f4236e6d3ccea7291995203f8f018058783b4c3a9469119811a0b5db8c0 ;; \
      arm64) compose_arch=aarch64; compose_sha=42cfa75f51ad0ccf290bad37899e0038a8c10a0069e85233ecc1d53e3ff1347d ;; \
      *) echo "Unsupported Docker Compose architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl --fail --location --retry 3 --retry-all-errors \
      "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-${compose_arch}" \
      --output /usr/local/bin/docker-compose; \
    echo "${compose_sha}  /usr/local/bin/docker-compose" | sha256sum --check --status; \
    chmod 0755 /usr/local/bin/docker-compose

COPY VERSION updater.py web.py self_update.py i18n.py scheduler.py reports.py notifications.py registry_access.py compose_config.py compose_manager.py cinema_windows.py ./
COPY windows ./windows
COPY templates ./templates
COPY static ./static
RUN mkdir -p /data

EXPOSE 8788
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/health', timeout=2)"

CMD ["gunicorn", "--workers=1", "--threads=8", "--timeout=0", "--bind=0.0.0.0:8788", "--access-logfile=-", "--error-logfile=-", "web:app"]
