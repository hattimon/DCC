FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DCC_UPDATER_DATA=/data \
    DCC_UPDATER_AUTO_UPDATE_ON_START=1

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY updater.py web.py ./
COPY templates ./templates
RUN mkdir -p /data

EXPOSE 8788
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/health', timeout=2)"

CMD ["gunicorn", "--workers=1", "--threads=8", "--timeout=0", "--bind=0.0.0.0:8788", "--access-logfile=-", "--error-logfile=-", "web:app"]
