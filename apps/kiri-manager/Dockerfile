FROM python:3.12-slim-bookworm@sha256:44cf1793efa7c7a476bb0f2cff81443f4a072c90c1cb127e2924933daa3e8c64 AS runtime
ARG VERSION=0.1.2
LABEL org.opencontainers.image.title="DCC Kiri Manager" \
      org.opencontainers.image.source="https://github.com/hattimon/DCC" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    KIRI_PANEL_DATA=/data KIRI_PANEL_BIND=0.0.0.0 KIRI_PANEL_PORT=8796
WORKDIR /opt/kiri-manager
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: -r requirements.txt \
    && groupadd --gid 10001 panel && useradd --uid 10001 --gid 10001 --no-create-home panel \
    && install -d -m 0700 -o 10001 -g 10001 /data
COPY VERSION setup-kiri-linux.sh ./
COPY backend ./backend
COPY frontend ./frontend
USER 10001:10001
VOLUME ["/data"]
EXPOSE 8796/tcp
HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
  CMD ["python", "-c", "from urllib.request import urlopen; from os import environ; urlopen('http://127.0.0.1:' + environ['KIRI_PANEL_PORT'] + '/healthz', timeout=2).close()"]
STOPSIGNAL SIGTERM
CMD ["python", "-m", "backend"]

FROM runtime AS smoke
COPY tests/image_smoke.py /tmp/image_smoke.py
COPY tests/test_connection.py tests/fixtures.py /tmp/kiri-tests/
ENV PYTHONPATH=/opt/kiri-manager
RUN --network=none python /tmp/image_smoke.py && python -m unittest discover -s /tmp/kiri-tests -v

FROM runtime AS image
