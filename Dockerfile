# Posterboard: one image with the app, Caddy, tinyauth and rclone.
FROM caddy:2.11 AS caddy
FROM rclone/rclone:1.74 AS rclone
FROM ghcr.io/tinyauthapp/tinyauth:v5.2.0 AS tinyauth
FROM ghcr.io/astral-sh/uv:0.11 AS uv

FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    POSTERBOARD_DATA_DIR=/data \
    PORT=8080
# Backups go to the bunny.net storage zone "posterboard-linkedin" through its
# S3-compatible API. Set RCLONE_CONFIG_BUNNY_ENDPOINT (the zone's region) and
# RCLONE_CONFIG_BUNNY_SECRET_ACCESS_KEY (the zone password) when deploying.
ENV POSTERBOARD_BACKUP_REMOTE=bunny:posterboard-linkedin \
    RCLONE_CONFIG_BUNNY_TYPE=s3 \
    RCLONE_CONFIG_BUNNY_PROVIDER=Other \
    RCLONE_CONFIG_BUNNY_ACCESS_KEY_ID=posterboard-linkedin \
    RCLONE_CONFIG_BUNNY_FORCE_PATH_STYLE=true \
    RCLONE_CONFIG_BUNNY_NO_CHECK_BUCKET=true

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY --from=caddy /usr/bin/caddy /usr/local/bin/caddy
COPY --from=rclone /usr/local/bin/rclone /usr/local/bin/rclone
COPY --from=tinyauth /tinyauth/tinyauth /usr/local/bin/tinyauth
COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
