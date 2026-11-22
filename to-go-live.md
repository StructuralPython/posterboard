# Going live

Check each item off as you go. More detail is in README.md.

## 1. LinkedIn app

- [ ] Create an app at <https://www.linkedin.com/developers/apps>, linked to the StructuralPython page, named "Posterboard". LinkedIn doesn't allow "Linked" or "In" in app names.
- [ ] In **Products**, add **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**.
- [ ] In **Auth**, add the redirect URL `https://posterboard.structuralpython.com/linkedin/callback/`.
- [ ] Copy the **Client ID** and **Client Secret**.

## 2. Secrets

- [ ] Django secret: `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- [ ] Token encryption key (optional, but then rotating the Django secret won't lock out the stored token): `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- [ ] tinyauth user: `tinyauth user create --username connor --password '…'`, then keep the `connor:$2a$…` line.

## 3. bunny.net storage (backups)

- [ ] Create a storage zone named `posterboard`.
- [ ] Note its FTP username (the zone name) and password, and run `rclone obscure '<password>'`.

## 4. Image

- [ ] Build and push from a machine with Docker. There's none here.
  ```bash
  docker build -t ghcr.io/structuralpython/posterboard:latest .
  docker push ghcr.io/structuralpython/posterboard:latest
  ```
  If the package is private, give Magic Containers registry credentials.

## 5. Magic Container

- [ ] Create an app from the image, with container port **8080**.
- [ ] Set **min = max = 1 instance**. A second instance would run a second scheduler against its own copy of the database.
- [ ] Set the environment variables:

  | Variable | Value |
  | --- | --- |
  | `DJANGO_SECRET_KEY` | from step 2 |
  | `POSTERBOARD_ENCRYPTION_KEY` | from step 2 |
  | `POSTERBOARD_URL` | `https://posterboard.structuralpython.com` |
  | `POSTERBOARD_TIME_ZONE` | `America/Vancouver`, or your zone |
  | `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` | from step 1 |
  | `TINYAUTH_APPURL` | `https://auth.posterboard.structuralpython.com` |
  | `TINYAUTH_AUTH_USERS` | from step 2 |
  | `POSTERBOARD_BACKUP_REMOTE` | `bunny:posterboard` |
  | `RCLONE_CONFIG_BUNNY_TYPE` | `ftp` |
  | `RCLONE_CONFIG_BUNNY_HOST` | `storage.bunnycdn.com` (or your region's host) |
  | `RCLONE_CONFIG_BUNNY_USER` | the zone name |
  | `RCLONE_CONFIG_BUNNY_PASS` | the obscured password |
  | `RCLONE_CONFIG_BUNNY_EXPLICIT_TLS` | `true` |

## 6. Hostnames

- [ ] Add both `posterboard.structuralpython.com` and `auth.posterboard.structuralpython.com` to the container's endpoint, with DNS (CNAME) and TLS for each.

## 7. First run

- [ ] Open `https://posterboard.structuralpython.com`. You should land on the tinyauth login page; sign in.
- [ ] Open `/healthz` while signed out. It should return `ok`, and the rest of the site should redirect you to login.
- [ ] Click **Connect LinkedIn**. The dashboard should show your name and "59 days left".
- [ ] Post one of each kind with **Post now**, then check each on LinkedIn:
  - [ ] text with **bold**, *italic*, `code`, a #hashtag and (parentheses)
  - [ ] an image
  - [ ] a PDF carousel. This is the least certain kind: if it fails, note the error. The fallback is multi-image posts.
  - [ ] a short MP4
  Delete the test posts on LinkedIn afterwards if you like. Posterboard keeps its own record.
- [ ] Wait 5 minutes, then check that `posterboard.sqlite3`, `daily/` and `media/` appear in the storage zone.
- [ ] Redeploy or restart the container. Your posts should still be there, restored from the backup.

## 8. Then

- [ ] Put a reminder in your calendar about 50 days out to renew the LinkedIn connection. The dashboard turns amber 14 days before expiry.
- [ ] Optionally, apply for LinkedIn's Community Management API to read comments (see `shy-linkedin-plan.md`).
