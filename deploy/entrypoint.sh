#!/usr/bin/env bash
# Starts everything Posterboard needs in one container:
#   tinyauth (login), gunicorn (the app), the scheduler, the 5-minute backup
#   loop, and Caddy in front. If any of them exits, the container stops, and
#   Magic Containers restarts it (the database is restored from backup first).
set -euo pipefail
APP_DIR="${APP_DIR:-/app}"
cd "$APP_DIR"

: "${POSTERBOARD_DATA_DIR:=/data}"
export POSTERBOARD_DATA_DIR
mkdir -p "$POSTERBOARD_DATA_DIR/media" "$POSTERBOARD_DATA_DIR/tinyauth"

# A fresh container has no database: fetch the latest backup before anything opens it.
python manage.py restore
python manage.py migrate --noinput

export TINYAUTH_SERVER_ADDRESS=127.0.0.1
export TINYAUTH_SERVER_PORT=3000
export TINYAUTH_DATABASE_PATH="$POSTERBOARD_DATA_DIR/tinyauth/tinyauth.db"
export TINYAUTH_RESOURCES_ENABLED=false
export TINYAUTH_ANALYTICS_ENABLED="${TINYAUTH_ANALYTICS_ENABLED:-false}"
export TINYAUTH_AUTH_SECURECOOKIE="${TINYAUTH_AUTH_SECURECOOKIE:-true}"
export TINYAUTH_AUTH_TRUSTEDPROXIES="${TINYAUTH_AUTH_TRUSTEDPROXIES:-127.0.0.1}"
export TINYAUTH_UI_TITLE="${TINYAUTH_UI_TITLE:-Posterboard}"
# The login hostname, for Caddy, from TINYAUTH_APPURL.
TINYAUTH_HOST="${TINYAUTH_APPURL#*://}"
export TINYAUTH_HOST="${TINYAUTH_HOST%%/*}"

pids=()
start() { "$@" & pids+=("$!"); }

start tinyauth
start gunicorn config.wsgi:application \
  --bind 127.0.0.1:8000 --workers 2 --threads 4 --timeout 900 \
  --access-logfile - --forwarded-allow-ips 127.0.0.1
start python manage.py run_scheduler
start python manage.py backup --every 300
start caddy run --config "$APP_DIR/deploy/Caddyfile" --adapter caddyfile

stop() {
  kill -TERM "${pids[@]}" 2>/dev/null || true
  wait || true
}
trap stop TERM INT

# Exit as soon as any process does (the trap handles a normal stop).
set +e
wait -n
status=$?
echo "A process exited ($status); stopping the container." >&2
stop
exit "$status"
