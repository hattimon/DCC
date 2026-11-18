#!/usr/bin/env bash
set -euo pipefail

platform="$1"
reports="$2"
mkdir -p "$reports"
prefix="dcc-candidate-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}"
health_probe='import sys,urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2).close()'

docker build --pull --platform "$platform" -f apps/dcc-web/Dockerfile -t dcc-candidate-web .
docker build --pull --platform "$platform" -t dcc-candidate-updater apps/container-updater

smoke() (
  kind="$1"; previous="$2"; endpoint="$3"; state_file="$4"
  candidate="dcc-candidate-$kind"
  container="$prefix-$kind"
  volume="$container-data"
  docker volume create "$volume" >/dev/null
  trap 'docker rm -f "$container" >/dev/null 2>&1 || true; docker volume rm "$volume" >/dev/null' EXIT

  docker pull --platform "$platform" "$previous" >/dev/null
  for image in "$previous" "$candidate"; do
    [[ "$(docker image inspect --format '{{.Architecture}}' "$image")" == "${platform#linux/}" ]]
  done
  package_format='${binary:Package}\t${Version}\t${source:Package}\n'
  docker run --rm --network none --entrypoint dpkg-query "$previous" -W -f="$package_format" > "$reports/$kind-published-packages.txt"
  docker run --rm --network none --entrypoint dpkg-query "$candidate" -W -f="$package_format" > "$reports/$kind-candidate-packages.txt"
  docker image inspect --format '{{.Architecture}} {{.Size}}' "$candidate" > "$reports/$kind-image.txt"

  start() {
    docker run --platform "$platform" -d --name "$container" --network none \
      --mount "type=volume,source=$volume,target=/data" \
      -e DCC_UPDATER_AUTO_UPDATE_ON_START=0 -e DCC_UPDATER_SELF_UPDATE_ON_START=0 "$1" >/dev/null
    for _ in {1..25}; do
      if docker exec "$container" python -c "$health_probe" "$endpoint" >/dev/null 2>&1; then return; fi
      sleep 2
    done
    docker inspect --format='state={{.State.Status}} exit={{.State.ExitCode}}' "$container"
    docker logs "$container" 2>&1 | sed -E 's/(password=)[^[:space:]]+/\1[REDACTED]/g'
    return 1
  }

  start "$previous"
  before="$(docker exec "$container" sha256sum "/data/$state_file")"
  docker exec "$container" sh -ec 'printf "fixture-state\n" > /data/ci-sentinel'
  docker stop "$container" >/dev/null
  docker rm "$container" >/dev/null
  start "$candidate"
  [[ "$(docker exec "$container" sha256sum "/data/$state_file")" == "$before" ]]
  docker exec "$container" sh -ec 'test "$(cat /data/ci-sentinel)" = fixture-state'
  case "$kind" in
    web) docker exec "$container" docker compose version ;;
    updater)
      docker exec "$container" sh -ec 'docker-compose version && python -m pip check && ! command -v curl' ;;
  esac
  docker stop "$container" >/dev/null
  docker rm "$container" >/dev/null
  start "$previous"
  [[ "$(docker exec "$container" sha256sum "/data/$state_file")" == "$before" ]]
  docker exec "$container" sh -ec 'test "$(cat /data/ci-sentinel)" = fixture-state'
  printf '%s %s: start, upgrade, data retention and rollback passed\n' "$kind" "$platform"
)

smoke web ghcr.io/hattimon/dcc-web:0.3.4 http://127.0.0.1:8789/api/health master-key
smoke updater ghcr.io/hattimon/dcc-container-updater:1.1.9 http://127.0.0.1:8788/health admin_password_hash
docker run --rm --network none --entrypoint python \
  --mount "type=bind,source=$PWD/apps/container-updater/tests,target=/test,readonly" \
  -e DCC_UPDATER_DATA=/tmp/dcc-test-data -e DCC_UPDATER_AUTO_UPDATE_ON_START=0 \
  -e DCC_UPDATER_SELF_UPDATE_ON_START=0 dcc-candidate-updater \
  -m unittest discover -s /test -p test_compose_manager.py -k RealComposeNormalizationTests -q \
  2>&1 | sed -E 's/(password=)[^[:space:]]+/\1[REDACTED]/g'
