# shy-linkedin: plan

A private portal, for one user, for drafting and scheduling LinkedIn posts and
for answering comments on them without opening LinkedIn. It would run on
bunny.net Magic Containers.

Research date: 2026-11-16. The sources are at the end; the claims marked
**(official)** come from LinkedIn's developer documentation on Microsoft Learn.

## Short answer

LinkedIn allows **half** of this through its self-serve API, and the other half
only through a vetted programme.

| Feature | Possible? | How |
|---|---|---|
| Write, store and schedule drafts in the portal | Yes | Our own app; LinkedIn isn't involved |
| Publish posts (text, link, image, video) to your profile | **Yes, self-serve** | "Share on LinkedIn" product, `w_member_social` scope |
| Reply to a comment, when the comment's ID is known | Yes, self-serve | `w_member_social` covers commenting as yourself |
| **Read** the comments on your posts | **Not self-serve** | `r_member_social` is closed; the alternative is the vetted Community Management API |
| Read your own post history and statistics | Not self-serve | Same restriction |

Scraping LinkedIn or driving it with a headless browser is not an option:
LinkedIn's User Agreement forbids automated access, and accounts get
restricted for it. Everything below uses the official API only.

## What the self-serve tier gives you (no review needed)

- **Share on LinkedIn**, scope `w_member_social` **(official)**: "Required to
  create a LinkedIn post on behalf of the authenticated member". This is
  `POST /v2/ugcPosts` (or the newer `/rest/posts`), with text, article links,
  images and video (uploaded first through the assets/images API). Rate limits:
  150 requests per member per day, plenty for one person.
- **Sign In with LinkedIn (OpenID Connect)**: gives your person URN, which is
  needed as the post `author`.
- **Commenting** `POST /rest/socialActions/{postUrn}/comments`: creating a
  comment as yourself works with member write access. A reply sets
  `parentComment` to the comment's URN, so to reply you must already **know**
  that URN.
- **Tokens:** access tokens last **60 days**, and self-serve apps get **no
  refresh token** (programmatic refresh is for approved Marketing partners
  only). The portal will need a "Reconnect LinkedIn" button every ~2 months,
  which is one OAuth click.

## Why reading comments is hard

- `r_member_social` (read a member's posts, comments and reactions) is a
  **closed** permission **(official)**: "We're not accepting access requests at
  this time due to resource constraints."
- The Comments API lists `r_member_social_feed` as **restricted**
  **(official)**: "granted to select developers only".
- Without a read permission, the app can't list the comments on your own
  posts, so it can't show them to you to answer.

## The sanctioned route: Community Management API

The Community Management API covers exactly this. Its **"Executive
Management"** use case **(official)** is: OAuth into a person's profile, post to
the profile, and *display comments by other members on that post* in your app.
Its "Profile Management" use case is: "create and manage posts, comments, and
reactions while monitoring engagement on behalf of individual profiles."

The requirements **(official)**:

- **Only for registered legal organizations, for commercial use cases only.**
  StructuralPython would have to be the applicant, not a personal account.
- A verified business email (connor@structuralpython.com should qualify;
  personal addresses are rejected), the organization's legal name, registered
  address, website and privacy policy.
- A super admin of the **StructuralPython LinkedIn Page** must verify the
  developer app.
- A **new** developer app that has no other API products. The app name can't
  contain "Linked", "In" or LinkedIn/Microsoft logos, so a name like
  "shy-linkedin" must change, e.g. "StructuralPython Social Desk".
- **Development tier** (first approval) allows 500 calls per app and 100 calls
  per member per day. That is enough for one person polling a handful of posts a
  few times a day. It is intended for building, and integration is expected
  within 12 months.
- **Standard tier** (full access) needs a screencast showing every use case, test
  credentials and a privacy policy. A personal tool may not need it if the
  Development tier limits are enough, but LinkedIn may expect an upgrade in the
  end.
- **Timelines aren't published.** Third-party reports range from weeks to a few
  months, and approval is at LinkedIn's discretion. Whether a one-user internal
  tool counts as a "commercial use case" is the main risk, and we only find out
  by applying.

## Fallback for comments if Community Management is refused

LinkedIn emails you when someone comments ("X commented on your post"). The
email has the comment text and a link whose URL contains the post and comment
URNs.

- The portal could read those emails from a dedicated mailbox (IMAP, or a
  forwarding rule into an inbound-email webhook), parse out the comment and its
  URN, show it in the inbox, and post your reply with the self-serve
  `w_member_social` comment call (`parentComment` = that URN).
- This reads only your own mail and writes only through the official API.
- It is **fragile**: email formats change, LinkedIn batches or skips
  notifications, and it doesn't see edits or deletes. It works as a stopgap, not
  a foundation.
- Prototype it before relying on it, to confirm that the URNs in the links are
  usable by the comments API.

## Recommended approach

1. **Phase 1, self-serve:** drafts, scheduling and publishing.
   - Create a LinkedIn developer app, add "Share on LinkedIn" and "Sign In with
     LinkedIn using OpenID Connect", and do OAuth once.
   - In the portal, write drafts (Markdown), attach images, preview, approve,
     then schedule or publish.
   - Keep a log of the published post URNs and links.
2. **Phase 2, in parallel:** apply for Community Management Development tier as
   StructuralPython, for the Executive Management (or Profile Management) use
   case.
   - Once approved, add a comments inbox: poll your recent posts' comments, show
     them threaded, draft replies (optionally with Claude-suggested drafts that
     you approve), and post the replies.
3. **Phase 2b, only if refused:** try the email fallback above.

## Architecture

- **Framework: Django**, recommended over FastAPI for this app. It's one user and
  a mostly CRUD UI: drafts, a schedule, an inbox and a token store.
  - Django's auth, admin, ORM, migrations and forms give most of it for free.
  - HTMX keeps the UI light without a JS build step.
  - FastAPI would mean assembling auth, an ORM, migrations and an admin by hand,
    for no benefit at this scale.
- **Background work:** a scheduler for timed posts, comment polling, and token
  expiry reminders. Options are django-q2 or APScheduler in the same container,
  or a small second container. Scheduled jobs must survive restarts, so the job
  state lives in the database.
- **Database:** SQLite on a persistent volume is enough for one user; Postgres
  only if Magic Containers storage makes SQLite awkward.
- **Hosting: bunny.net Magic Containers**, one container plus a volume.
  - **Private:** Django login with a strong password and TOTP (django-otp), or
    passkeys. Optionally an IP allow-list or Bunny Shield in front.
  - The OAuth redirect URI (`https://<host>/linkedin/callback`) must be HTTPS and
    registered on the LinkedIn app. Since the redirect goes through your browser,
    the portal only has to be reachable by you.
- **Secrets:** keep the LinkedIn client secret and Django secret in Magic
  Containers environment variables, and the access token encrypted at rest in
  the database.
- **Data rules:** follow the LinkedIn API Terms, which limit storing members'
  data. Keep only what the inbox needs (comment text, author name, URNs) and
  delete it after a set period.
- **Optional Claude drafting:** a "suggest a post or reply" button that calls the
  Claude API with context such as release notes, changelogs and the comment
  thread. A human always approves before anything is published.
  - For the "mad-posts about the ecosystem" use case, the portal could pull
    recent GitHub releases from beamz9000, ymprint, papermodels, loadtracer,
    pycba-tools and pynite-tools as draft seeds.

## Open questions for you

1. Is StructuralPython a registered legal organization with a LinkedIn Page you
   (or a super admin) control? That decides whether Phase 2 is possible.
2. Is posting enough to start (Phase 1), with comments to come later?
3. Should Claude-drafted posts and replies be part of the first version?
4. Any preference between SQLite on a volume and a managed Postgres?

## Sources

- [Community Management, overview (official)](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/community-management-overview?view=li-lms-2026-09): use cases, tiers, "`r_member_social` is a closed permission"
- [Comments API (official)](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/comments-api): permissions table (`w_member_social_feed`, restricted `r_member_social_feed`), create and reply endpoints
- [Community Management App Review (official)](https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review): "registered legal organizations for commercial use cases only", business email, Page verification, Executive Management screencast requirements
- [Share on LinkedIn (official)](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin): `w_member_social`, `ugcPosts`, media upload, rate limits
- [Programmatic refresh tokens (official)](https://learn.microsoft.com/en-us/linkedin/shared/authentication/programmatic-refresh-tokens): refresh tokens only for approved Marketing Developer Platform partners
- [network update social actions (official, older 2025-04 version)](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/network-update-social-actions?view=li-lms-2025-04)
- Third-party summaries, which agree that `r_member_social` is closed: [flaghand: what w_member_social lets you post](https://flaghand.com/docs/guides/linkedin-api-personal-profile), [Does LinkedIn Have an API? (social-api.ai)](https://social-api.ai/blog/does-linkedin-have-an-api), [LinkedIn API Guide 2026 (upload-post)](https://www.upload-post.com/linkedin-api/), [LinkedIn API restrictions (outstand)](https://www.outstand.so/blog/linkedin-api-restrictions), [LinkedIn access token 60 days (adaptlypost)](https://adaptlypost.com/blog/linkedin-access-token-60-days-expires)
