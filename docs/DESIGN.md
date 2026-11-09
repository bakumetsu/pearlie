# Pearlie: design

Status: draft, agreed in chat on 2026-11-08 (DocuTeach planner session). Nothing is built yet.

## 1. What it is

Pearlie is a self-hosted media hub. From one mobile-first web app you:

- browse your **own library**: Stash images, Stash videos, Komga series and books (with a reader);
- browse **external sites**: Danbooru, Gelbooru, Rule34, nhentai;
- **save** from those sites into Stash (images) or Komga (galleries as CBZ), already tagged, with no duplicates;
- **filter** what you see and what you save with your own tag rules.

The web app comes first (self-hosted, then PWA). A native iOS client (SwiftUI) follows later on the same API.

## 2. Product rules (every change is checked against these)

1. **Stash and Komga are the library.** Pearlie stores only its own data: jobs, rules, the index of saved items (source, post id, MD5), trash records. It never keeps a second copy of the media. 
2. **Never exposed directly.** Access only through Tailscale/WireGuard or a reverse proxy with login. Outbound calls go only to the configured sites, Stash and Komga.
3. **Secrets stay local.** API keys and site cookies live in `.env` or the local config, are never logged and never reach the browser. Clients never get Stash or Komga keys.
4. **No delete without undo.** Library deletes go to a Pearlie trash folder with an Undo toast; real deletion happens after a retention period the user sets.
5. **Polite to sites.** Every source has a throttle; one download at a time per site by default.
6. **Thin clients.** All logic lives in the backend. The web UI and the iOS app only call the JSON API.
7. **UI:** no clutter, icons over text in tight bars, touch targets at least 44 px.

## 3. Stack

| Part | Choice | Why |
|---|---|---|
| Backend | Python 3.12+, FastAPI, httpx, SQLite | gallery-dl is a Python library we can call in-process |
| Downloads | gallery-dl (moved to Codeberg) plus httpx | gallery-dl covers nhentai; boorus use their JSON APIs directly |
| Frontend | Svelte + Vite single-page app, built to static files and served by FastAPI | small and fast on a phone; an SPA keeps the video player alive between screens |
| Deploy | One Docker container on Proxmox (LXC or VM), OMV share mounted over NFS | same UID/GID as Stash and Komga |
| iOS (later) | SwiftUI, AVKit for video and PiP | same JSON API, token login |

## 4. Architecture

```
phone / browser ──► Pearlie (FastAPI + static Svelte UI)
                     ├── sources/   Danbooru, Gelbooru/Rule34, nhentai  ──► the sites
                     ├── targets/   Stash (GraphQL), Komga (REST)        ──► your servers
                     ├── filters/   base list + user rules
                     ├── jobs/      SQLite queue + one worker, per-site throttle
                     └── proxy/     thumbnails, images, video (HTTP Range), book pages
NFS share (OMV): .../stash-library/stash-incoming   .../komga-library/komga-incoming   .../pearlie-trash
```

Pearlie triggers Stash and Komga scans itself after each save, because file watching over NFS is unreliable.

## 5. Project layout

```
Pearlie/
  backend/app/
    main.py  config.py  db.py  models.py
    sources/   base.py  danbooru.py  gelbooru.py (also rule34)  nhentai.py
    targets/   stash.py  komga.py  comicinfo.py
    library/   stash_browse.py  komga_browse.py  trash.py
    filters/   rules.py  aliases.py  baselist.py
    jobs/      worker.py
    api/       search.py  library.py  save.py  jobs.py  rules.py  media.py  health.py
  backend/tests/          mocked sites, Stash and Komga
  frontend/               Svelte + Vite
  deploy/                 Dockerfile, docker-compose.yml, .env.example
  docs/DESIGN.md          this file
```

### Sample media for the stub

The stub generates placeholder media by default. For realistic photos, clips and comics run `python backend/scripts/fetch_samples.py` (optional `--only photos|videos|comics`). It downloads the pinned public-domain/CC list in `backend/scripts/sample_sources.json` from Wikimedia Commons into the git-ignored `backend/fixtures/media`, throttled with backoff on HTTP 429, and resumes where it stopped. Needs ffmpeg for the videos.

## 6. Sources

| Source | Auth | Notes |
|---|---|---|
| Danbooru | none needed | first source; caps how many tags one search can hold, so Pearlie also filters results itself |
| Gelbooru | `api_key` + `user_id` | from the account options page |
| Rule34 | `api_key` + `user_id` | same dapi format as Gelbooru, one module |
| nhentai | logged-in session cookies | see below |

**nhentai.** The site's own CBZ link is signed by the server (`sig`), tied to the account (`u`) and expires (`exp`), so Pearlie cannot build it.
- **Route A (default):** metadata from `/api/gallery/{id}`, pages through gallery-dl, packed into a CBZ (gallery-dl `zip` post-processor with `"extension": "cbz"`), then `ComicInfo.xml` added.
- **Route B (fallback):** replay the request the Download button sends (with session cookies, and `cf_clearance` plus the same User-Agent if Cloudflare is in front), take the signed URL, fetch the file at once. FlareSolverr only if needed; a captcha puts the job in a "needs click" state.
- Still to check: that gallery-dl's nhentai extractor works today (`gallery-dl --simulate https://nhentai.net/g/<id>/`), and which request the button sends (for route B).

## 7. Targets

### Stash (POST `/graphql`, header `ApiKey: <key>`)

Save flow for one image:
1. Dedupe: Pearlie's own `saved_items` table, then `findImages(image_filter: { checksum: { value: $md5, modifier: EQUALS } })`.
2. Write the file into `stash-incoming`.
3. `metadataScan(input: { paths: [$path] })` returns a job id; poll `findJob(input: { id })` until done.
4. `findImages(image_filter: { path: { value: $path, modifier: EQUALS } })` gives the new image id.
5. Per tag: `findTags(tag_filter: { name: { value, modifier: EQUALS } })`, else `tagCreate(input: { name })`.
6. `imageUpdate(input: { id, tag_ids, urls: [sourceUrl] })`.

Browsing: `findImages` (`paths { thumbnail image }`), `findScenes` (`paths { screenshot preview }`), `sceneStreams(id)` for playback. Editing: `imageUpdate` / `sceneUpdate` for rating, favorite and tags.

Library browsing (read-only, `backend/app/targets/stash_client.py`). Check these exact queries in `http://<stash>/playground` before a live test:
- Images: `query($f: FindFilterType) { findImages(filter: $f) { count images { id title rating100 created_at urls tags { name } visual_files { ... on ImageFile { basename width height size } } } } }`, detail `findImage(id: $id)` with the same fields.
- Scenes: `query($f: FindFilterType) { findScenes(filter: $f) { count scenes { id title rating100 created_at urls tags { name } files { basename width height duration video_codec size } } } }`, detail `findScene(id: $id)` plus `sceneStreams { url mime_type label }`.
- `$f` carries `page`, `per_page`, `q`, `sort` (`created_at`, `rating`, `random_<seed>`) and `direction`.
- Media is not fetched from the `paths` fields: the backend proxies `/image/{id}/thumbnail`, `/image/{id}/image`, `/scene/{id}/screenshot`, `/scene/{id}/stream` and `/scene/{id}/{stream.m3u8|stream.mp4|stream.webm|N.ts}` with the key in the `ApiKey` header only. Only a valid `resolution` query value is forwarded, and HLS playlists are rewritten so no Stash URL or key reaches the browser.
- Fallback streams in the item detail come from `sceneStreams`, mapped to proxy URLs; `stash_link` is `<stash_public_url or stash_url>/scenes/{id}` or `/images/{id}`, never with a key.

Notes:
- Stash v0.32.0 (Oct 2026) returns 403 to public IPs when no credentials are set. Give Stash an API key.
- The schema shifts between releases: check every field above in `http://<stash>/playground` before coding, especially whether the image `checksum` filter is MD5.

### Komga (header `X-API-Key: <key>`)

- `GET /api/v1/libraries` at startup: map library to folder path and id.
- After the CBZ lands in `komga-incoming`: `POST /api/v1/libraries/{id}/scan`.
- `ComicInfo.xml` fields: `Series` (parody), `Title`, `Tags`, `Genre` (category), `Writer`/`Penciller` (artist), `LanguageISO`, `Web` (source URL). Komga imports them only if the library's metadata import settings allow ComicInfo.
- Browsing and reader: `/api/v1/series`, `/api/v1/books`, `/thumbnail`, `/api/v1/books/{id}/pages/{n}`; progress `PATCH /api/v1/books/{id}/read-progress`.
- Reader page thumbnails: `GET /api/media/komga/books/{id}/pages/{n}/thumb`, proxied from Komga's page thumbnail; the book detail carries `page_thumb_url` as a template.
- Komga 1.30.0 (Nov 2026) replaced deprecated endpoints: check each one in `/swagger-ui.html` first.

## 8. Filters

| Layer | Content | Editable |
|---|---|---|
| Base list | minor-content tags plus site aliases | no |
| Reject | tags never shown or saved | yes |
| Warn | tags shown blurred with a label | yes |
| Require (optional) | save only if one of these is present | yes |
| Tag mapping | which tags go to Stash, which into ComicInfo fields | yes |

- Order: base list, reject, require, warn. The first match decides.
- Runs in three places: added to the site query where supported (`-tag`), on returned results (hidden posts never reach the UI, the thumbnail proxy refuses them), and at save time against the full metadata.
- Library view: matching items are hidden or blurred; a one-time report lists them. Pearlie never deletes on its own.
- Matching: lowercase, space = underscore = hyphen, optional type scope (`artist:x`), alias table across sites.
- UI: chips per list, tap a tag on any post to reject it, JSON import/export, `POST /api/rules/test` shows which rule decides.

## 9. API (first version)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/search?q=&sources=&page=&page_size=` | one search across library and sites; results grouped per section |
| GET | `/api/library/stash/images` · `/videos` · `/api/library/komga/series` · `/books` | the "See all" views |
| GET / PUT | `/api/view-settings`, `/api/view-settings/{source}` | per-source grid view (`mode` grid, wall, masonry or list; `per_page`; `zoom` 1-5), stored as `view.<source>` in the settings table (in memory in fixture mode). GET fills defaults (grid, 60, 3; nhentai 25) and returns `per_page_options` and `per_page_max`; PUT answers 422 `invalid` for an unknown source, mode, zoom, or a `per_page` outside 1 to the source cap |
| GET | `/api/library/{kind}/{id}` | item details |
| PATCH | `/api/library/{kind}/{id}` | rating, favorite, tags |
| DELETE | `/api/library/{kind}/{id}` | move to trash; returns an undo token |
| POST | `/api/trash/{token}/restore` | undo |
| GET | `/api/trash` | list trashed items with token, expires_at, retention_days; expired entries are left out but not dropped by the GET (they are dropped on restore, on empty, or when retention purges them) |
| DELETE | `/api/trash` | Empty: permanently delete everything in the trash, returns `{removed}` (the real deletion rule 4 allows; the UI asks to confirm first). Fixture mode only for now; in real mode the route is absent (404), never an empty list |
| GET | `/api/media/...` | proxy for thumbnails, images, video (Range), book pages |
| POST | `/api/save` `{source, post_id}` | rules, dedupe (409), queue; returns job id |
| GET / POST / DELETE | `/api/jobs`, `/api/jobs/{id}`, `/retry` | queue (newest first; `?state=` CSV; jobs carry `notices`). Worker: one job per site, 2 s gap (`PEARLIE_DOWNLOAD_INTERVAL_S`), running jobs requeued at startup |
| GET / PUT | `/api/rules`; POST `/api/rules/test` | filters (base list returned read-only) |
| POST | `/api/library/komga/books/{id}/progress` | reading progress |
| GET | `/api/health` | Stash, Komga, mounts, sites |

Paging fields: list and search answers carry `page` (the page actually served), `page_size`, `total`, `pages` (null where the source gives no count, such as Danbooru) and, for Stash, `stats {megapixels, size_bytes}`. `page_size` is clamped to the source cap (200 Stash, Komga, Danbooru; 100 Gelbooru, Rule34; 25 nhentai; search `page_size` above 200 is a 422). A `page` past the last one is served as the last page, never an error. With several sources in one search `page_size` is ignored (each section keeps its short preview) and the section `page_size` is null.

Auth: a login that returns a token (cookie for the web UI, bearer token for iOS).

## 10. UI

Layout A, chosen 2026-11-08 (mockups: https://claude.ai/artifact/FXZchWLeynCcAmEbJfKjbH):
- One search box with tag chips (excluded tags in red), type pills (All, Images, Videos, Books, Web).
- Results in sections: Stash images, Stash videos, Komga books (progress bar), web results ("In library" badge or save button). "See all" opens a full grid for that one source.
- Bottom bar: Search, Library, Queue, Rules.
- **Mini player:** a playing video docks above the bottom bar and keeps playing while you browse (play/pause, progress, PiP, close).
- **System PiP:** the browser's PiP window (Chrome/Edge, Safari macOS and iPhone; Firefox only through its own toggle; iPhone PWA mode to be tested). Native PiP in the iOS app.
- Item view (to mock up next): full viewer, rating, favorite, tag edit, delete with Undo.

## 11. Phases

Reordered 2026-11-08: the UI comes first, as the groundwork for the backend.

1. **UI prototype:** the real Svelte frontend for every screen (search, library and item view, mini player, PiP and reader, queue and rules) on a FastAPI stub that serves fixture JSON and generated placeholder media on the section 9 paths.
2. **Backend behind the UI:** Danbooru → Stash save, save queue, base list; library browsing (Stash, Komga); filters and library editing. Each step replaces fixtures with real logic.
3. **Login**, then a **Proxmox installer** in the community-scripts style (one command on the host creates the LXC and installs Pearlie).
4. **nhentai → Komga** (route A, then B if worth it), Gelbooru and Rule34.
5. **Parked until the user opens it:** PWA polish, then the native iOS client.

Out of scope for now: yt-dlp video sources (the user's Stash-Downloader fork covers that), other sites, multiple users, public exposure.

## 12. Checks before coding

- Stash playground: every field in section 7; image `checksum` = MD5.
- Komga swagger: every endpoint in section 7 on 1.30.
- gallery-dl nhentai extractor: `--simulate` on one gallery.
- Paths: container paths of `stash-incoming`, the Komga library and the trash folder; UID/GID.

## 13. Name

"Pearlie" (pearls brought home). Web search on 2026-11-08 found no app or GitHub project with that name; the closest is "Pearlii", a dental app.

## Sources

- Stash API: https://docs.stashapp.cc/networking/api
- Stash releases: https://github.com/stashapp/stash/releases
- Komga releases: https://github.com/gotson/komga/releases
- Komga API: https://komga.org/docs/openapi/komga-api
- gallery-dl releases: https://releasebot.io/updates/mikf/gallery-dl (development on Codeberg)
- Booru credentials: https://docs.rs/crate/booru-rs/0.3.0/source/src/client/gelbooru.rs , https://www.nuget.org/packages/Imouto.BooruParser/
