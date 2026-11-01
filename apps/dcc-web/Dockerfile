FROM docker:29-cli AS cli
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/dcc DCC_WEB_DATA=/data DCC_WEB_CONTAINER_NAME=dcc-web
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client ca-certificates && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 dcc && mkdir /data && chown dcc:dcc /data
COPY --from=cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=cli /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins
WORKDIR /opt/dcc
COPY apps/dcc-web/requirements.txt /tmp/dcc-web-requirements.txt
RUN pip install --no-cache-dir -r /tmp/dcc-web-requirements.txt
COPY dcc_catalog.py dcc-catalog.json ./
COPY catalog/media ./catalog/media
COPY apps/container-updater/updater.py ./apps/container-updater/updater.py
COPY apps/dcc-web ./apps/dcc-web
WORKDIR /opt/dcc/apps/dcc-web
USER dcc
EXPOSE 8789
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8789/api/health',timeout=3)"
ENTRYPOINT ["python","web.py"]
CMD ["--host","0.0.0.0","--allow-lan","--data","/data"]
