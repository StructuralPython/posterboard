# Posterboard

A private portal for writing and scheduling LinkedIn posts without being on LinkedIn.
Write in Markdown, see a live preview of how the post will look in the feed, attach an
image, a video or a carousel (PDF), and let Posterboard publish it at the time you
choose.

It will live at `posterboard.structuralpython.com`, on a bunny.net Magic Container.

## What it does

- **Markdown to LinkedIn text.** `**bold**`, `*italic*`, `***both***` and `` `code` ``
  become Unicode bold, italic and monospace letters, which LinkedIn shows as styled
  text (`posts/unicode_text.py`, a wenmode renderer). Lists, `#hashtags` and links are
  typed as they will appear. Hashtags stay clickable, and the characters LinkedIn
  treats as markup are escaped (`posts/little_text.py`).
- **Live preview.** A feed card updates as you type. It has an *In the feed* view (cut
  after three lines with "…more", wrapped at LinkedIn's desktop or phone width) and an
  *Expanded* view, plus the media: an image, a video player, or the carousel's pages.
  It also counts characters against LinkedIn's 3000.
- **Its own scheduler.** LinkedIn's scheduling isn't used. Posterboard publishes through
  the immediate-post API when a post comes due (`posts/publishing.py`, checked every 30
  seconds).
  - *Scheduled* posts (and drafts) can be edited or deleted until they go out.
  - *Previous* posts keep the exact text that was published and can't be changed.
  - A failed post shows LinkedIn's reason and can be fixed and rescheduled.
  - A post is never published twice: it is claimed in one database update, and a publish
    interrupted by a restart is marked failed for you to check, not retried.
- **The LinkedIn connection.** Sign in with LinkedIn once to activate posting.
  LinkedIn's tokens for self-serve apps last 60 days and can't be refreshed
  automatically, so the dashboard counts the days down. It turns amber two weeks before
  expiry, and warns when a scheduled post falls after it. *Renew now* is one more
  LinkedIn sign-in. The token is encrypted at rest.

## How it runs

One container holds everything:

```
bunny.net edge (TLS) ──► Caddy :8080 ──► tinyauth :3000   (login page, and a check on every request)
                                    └──► gunicorn :8000  (Django app)
                         scheduler (manage.py run_scheduler)
                         backups   (manage.py backup --every 300, rclone → bunny.net storage)
                         SQLite    /data/posterboard.sqlite3, media in /data/media
```

- **Caddy** asks tinyauth about every request (`forward_auth`) and passes the signed-in
  user to Django in `Remote-User`. A client's own `Remote-User` header is removed first.
  Gunicorn listens on localhost only, and Django refuses any request without the header.
- **tinyauth** serves the login page on its own hostname,
  `auth.posterboard.structuralpython.com`. Its session cookie is set on
  `posterboard.structuralpython.com`, which covers the app.
- **SQLite** in WAL mode. Every 5 minutes the backup loop takes a consistent snapshot with
  SQLite's backup API. If anything changed, it uploads it with rclone, keeps one copy per
  day under `daily/`, and copies new media. It also backs up once more on shutdown.
- **On a fresh container** (a redeploy, a move), `manage.py restore` downloads the
  latest database and media before the app starts. A container's disk can be thrown
  away; the storage zone is the real copy.

`deploy/entrypoint.sh` starts it all and stops the container if any part exits, so Magic
Containers restarts it cleanly.

## Setting it up

### 1. LinkedIn app

1. At <https://www.linkedin.com/developers/apps>, create an app. LinkedIn requires every
   app to be associated with a company page (StructuralPython), but that doesn't change
   who posts: Posterboard posts as the member who signs in. LinkedIn doesn't allow
   "Linked" or "In" in app names; "Posterboard" is fine.
2. Under **Products**, add **Share on LinkedIn** and **Sign In with LinkedIn using OpenID
   Connect**. Both are self-serve; no review is needed.
3. Under **Auth**, add the redirect URL `https://posterboard.structuralpython.com/linkedin/callback/`
   and copy the client ID and secret.

This gives the scopes `openid profile w_member_social`: posting to your own profile
with text, an image, a video or a document. Reading comments needs LinkedIn's vetted
Community Management API. See `shy-linkedin-plan.md` for that research.

### 2. Storage zone for backups

Create a bunny.net storage zone (e.g. `posterboard`). Its FTP credentials go in rclone
environment variables (see `.env.example`). Obscure the password first:

```bash
rclone obscure 'storage-zone-password'
```

### 3. A tinyauth user

```bash
tinyauth user create --username connor --password '...'
```

It prints `connor:$2a$10$...`; that is `TINYAUTH_AUTH_USERS`. Add `--docker` if a tool
needs the `$` signs doubled.

### 4. Image and Magic Container

GitHub Actions (`.github/workflows/image.yml`) tests every push. On `main` it builds the
image and pushes it to `ghcr.io/structuralpython/posterboard:latest`, plus a `sha-…` tag
and, for `v*` tags, the version. It then starts the image and checks that `/healthz`
answers and that the app refuses requests that tinyauth hasn't signed in. The package is
private, so Magic Containers needs a GitHub token with `read:packages`.

In Magic Containers, create an app from the image and expose container port **8080**.
Set the environment variables from `.env.example`:

| Variable | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | a long random string |
| `POSTERBOARD_URL` | `https://posterboard.structuralpython.com` |
| `POSTERBOARD_TIME_ZONE` | your time zone, e.g. `America/Vancouver` |
| `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | from the LinkedIn app |
| `TINYAUTH_APPURL` | `https://auth.posterboard.structuralpython.com` |
| `TINYAUTH_AUTH_USERS` | from step 3 |
| `POSTERBOARD_BACKUP_REMOTE` | `bunny:posterboard` |
| `RCLONE_CONFIG_BUNNY_*` | the storage zone's FTP settings |

Optional: `POSTERBOARD_ENCRYPTION_KEY` (a Fernet key for the stored token; derived from
the secret key if unset), `LINKEDIN_API_VERSION` (default `202510`; LinkedIn supports
each monthly version for about a year), `LINKEDIN_RENEW_WARNING_DAYS` (default 14).

### 5. DNS

Point both `posterboard.structuralpython.com` and
`auth.posterboard.structuralpython.com` at the Magic Container's endpoint. Caddy sends
each hostname to the right place.

## Development

```bash
uv sync
uv run pytest                       # 59 tests: text, models, publishing, views, OAuth, backups

# The app alone, without Caddy or tinyauth:
DJANGO_DEBUG=1 POSTERBOARD_DEV_USER=connor uv run python manage.py migrate
DJANGO_DEBUG=1 POSTERBOARD_DEV_USER=connor uv run python manage.py runserver
DJANGO_DEBUG=1 uv run python manage.py run_scheduler --once
```

To run the whole stack as the container does (Caddy, tinyauth and rclone installed
locally), set the variables from `.env.example` and run `APP_DIR=$PWD
deploy/entrypoint.sh`. `PORT`, `TINYAUTH_PORT` and `APP_PORT` move it off ports that are
already in use. `POSTERBOARD_BACKUP_REMOTE` can be a local folder.

## Limits and notes

- **Carousels are PDFs.** LinkedIn only supports organic carousels as document posts:
  one slide per page, up to 300 pages and 100 MB. Posterboard renders the pages for the
  preview with pypdfium2.
- **One media item per post:** an image (JPG, PNG, GIF), a video (MP4, up to 500 MB) or
  a PDF. LinkedIn's multi-image posts aren't supported yet.
- **Not tested against LinkedIn yet.** The API calls follow LinkedIn's documentation and
  are tested against recorded responses. The first real post of each kind (text, image,
  video, PDF) is the test that matters.
- **Comments** aren't readable with a self-serve app (see the research notes).
