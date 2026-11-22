# Going live

Check each item off as you go. More detail is in README.md.

## 1. LinkedIn app

- [ ] Create an app at <https://www.linkedin.com/developers/apps>, named "Posterboard". LinkedIn requires every app to be associated with a company page, so pick StructuralPython; this doesn't affect who posts. Posts go out from the personal profile you sign in with. LinkedIn doesn't allow "Linked" or "In" in app names.
- [ ] In **Products**, add **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**.
- [ ] In **Auth**, add the redirect URL `https://posterboard.structuralpython.com/linkedin/callback/`.
- [ ] In **Settings**, set the privacy policy URL to `https://posterboard.structuralpython.com/privacy/` (public, no sign-in).
- [ ] Copy the **Client ID** and **Client Secret**.

## 2. Secrets

- [ ] Django secret: `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- [ ] Token encryption key (optional, but then rotating the Django secret won't lock out the stored token): `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- [ ] tinyauth user: `tinyauth user create --username connor --password '…'`, then keep the `connor:$2a$…` line.

## 3. bunny.net storage (backups)

- [ ] The storage zone is `posterboard-linkedin`, with **S3 compatibility** turned on. (S3 can only be turned on when a zone is created.)
- [ ] Note its password from the **Access** tab. The image already uses the main region's S3 endpoint, Frankfurt (`https://de-s3.storage.bunnycdn.com`); LA is a replica.

## 4. Image

GitHub Actions builds the image on every push to `main` and pushes it to `ghcr.io/structuralpython/posterboard` (`.github/workflows/image.yml`). It runs the tests first, then a smoke test of the built image.

- [ ] Check that the latest **Test and build image** run is green: <https://github.com/StructuralPython/posterboard/actions>
- [ ] Make the package public, so Magic Containers needs no token: <https://github.com/orgs/StructuralPython/packages/container/posterboard/settings>, **Change visibility** → **Public**. The repo stays private; the image holds no secrets (they all come from environment variables), but anyone can read the code in it.
- [ ] To release a fixed version instead of `latest`, push a tag (`git tag v0.1.0 && git push --tags`) and deploy `:0.1.0`.

## 5. Magic Container

- [ ] Create an app from `ghcr.io/structuralpython/posterboard:latest` (public registry `ghcr.io`, no login), with container port **8080**.
- [ ] Set **min = max = 1 instance**. A second instance would run a second scheduler against its own copy of the database.
- [ ] Set the environment variables:

  | Variable | Value |
  | --- | --- |
  | `DJANGO_SECRET_KEY` | from step 2 |
  | `POSTERBOARD_ENCRYPTION_KEY` | from step 2 |
  | `POSTERBOARD_URL` | `https://posterboard.structuralpython.com` |
  | `POSTERBOARD_TIME_ZONE` | `America/Vancouver`, or your zone |
  | `POSTERBOARD_CONTACT_EMAIL` | the address the privacy policy gives for questions (optional) |
  | `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` | from step 1 |
  | `TINYAUTH_APPURL` | `https://auth.posterboard.structuralpython.com` |
  | `TINYAUTH_AUTH_USERS` | from step 2 |
  | `RCLONE_CONFIG_BUNNY_SECRET_ACCESS_KEY` | the storage zone password, as is |

  The image already sets the rest of the backup settings (zone `posterboard-linkedin`, S3, Frankfurt).

## 6. Hostnames

- [ ] Add both `posterboard.structuralpython.com` and `auth.posterboard.structuralpython.com` to the container's endpoint, with DNS (CNAME) and TLS for each.

## 7. First run

- [ ] Open `https://posterboard.structuralpython.com`. You should land on the tinyauth login page; sign in.
- [ ] Open `/healthz` and `/privacy/` while signed out. They should load, and the rest of the site should redirect you to login.
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
