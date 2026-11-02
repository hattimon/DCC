#!/bin/sh
set -eu

# Docker socket GIDs vary by host. Read the mounted socket's group as root,
# then run the web process as the unprivileged DCC account with that one group.
if [ "$#" -gt 0 ] && [ "${1#-}" != "$1" ]; then
  set -- python web.py "$@"
fi

if [ "$(id -u)" -ne 0 ]; then
  exec "$@"
fi

if [ -S /var/run/docker.sock ]; then
  socket_gid="$(stat -c '%g' /var/run/docker.sock)"
  if [ -n "${SSH_AUTH_SOCK:-}" ] && [ -S "$SSH_AUTH_SOCK" ]; then
    agent_gid="$(stat -c '%g' "$SSH_AUTH_SOCK")"
    if [ "$agent_gid" != "$socket_gid" ]; then socket_gid="$socket_gid,$agent_gid"; fi
  fi
  exec setpriv --reuid=10001 --regid=10001 --groups="$socket_gid" -- "$@"
fi

exec setpriv --reuid=10001 --regid=10001 --init-groups -- "$@"
