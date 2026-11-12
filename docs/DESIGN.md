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
2. **Never exposed directly.** Access only through Tailscale/WireGuard or a reverse proxy with login. Outbound calls go only to the configured sites, Stash and Komga, and to GitHub (`api.github.com` for the update check, `codeload.github.com` for the update download; no tokens; can be turned off).
3. **Secrets stay local.** API keys and site cookies live in `.env` or the local config, are never logged and never reach the browser. Clients never get Stash or Komga keys. Secrets may be typed into the Options page (write-only, stored encrypted); they are never shown, logged or sent to the browser.
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
| Deploy | Debian LXC on Proxmox (community-scripts installer), Pearlie in a venv under systemd, OMV share bind-mounted from the host | files owned by the Stash/Komga UID/GID (OMV all_squash) |
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
  ct/ install/ json/       Proxmox installer (community-scripts format)
  deploy/                 update script, systemd unit, requirements lock (.env.example is in the repo root)
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

Browsing: `findImages` (`paths { thumbnail image }`), `findScenes` (`paths { screenshot }`, plus `date` and `studio { name }`, names to confirm in the Stash playground), `sceneStreams(id)` for playback. Editing: `imageUpdate` / `sceneUpdate` for rating, favorite and tags.

Video card: video tiles show the poster with a resolution badge (bottom left) and duration (bottom right), then title and a muted "studio - date" line. On mouse hover or a 500 ms touch long-press a muted looping preview plays from `/api/media/stash/scene/{id}/preview`, a proxy of Stash's REST `/scene/{id}/preview` that passes `Range` through (206 with `Content-Range`) and maps an upstream 404 to 404. One preview plays at a time; it stops on leave, release, scroll, unmount or a video error (the poster stays). No preview with reduced motion; with SFW on it plays only on a card the user already revealed.

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
- Reader chrome (toolbar, title pill, page progress) shows on open and on a real mouse move (not on touch, zero-delta or post-click synthetic moves), on keys that open UI on purpose (books, settings, help, thumbs) and when keyboard focus enters it; page turns by click, key or wheel leave it hidden; touch tap toggles it.
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
- Engine (shipped, `backend/app/filters/rules.py`): `evaluate()` runs base list, reject, require, warn; the first match decides. `require` is global: when any require rule exists, a post must match at least one of them, else verdict `require_missing`. Rules live in the SQLite `rules` table (`list` = reject, warn, require or mapping; `enabled`; mapping rows carry `target`) with a version in `settings` key `rules.version`.
- API: `GET /api/rules`, `PUT /api/rules` (full replace; a stale `version` returns 409 `stale_version`; entries 1-64 chars else 422 `invalid`; a `base_list` key in the body is ignored, the base list is read-only), `POST /api/rules/test` (tags, optionally `scope:name` -> decision, layer, rule, tag, alias).
- Search: each result post is evaluated; reject, base and require_missing posts are dropped and counted in the section `hidden`; warn posts are kept with `blur: {tag}`. A page can come back short (hidden posts are not refilled); `total` and `pages` come from the site. In real mode the Stash images, Stash videos and Komga books sections query the configured Stash/Komga with the raw search text (same clients and item mapping as the library routes, media through `/api/media/...`); an unconfigured service answers `not_configured`, an unreachable one a per-section `upstream_error`.
- Save: `POST /api/save` evaluates the post's full tag metadata; reject, base and require_missing refuse with 422 `rejected_by_rule` plus `layer` (`base`, `reject` or `require`), `rule`, `tag`, `alias`; warn saves. The base list is `filters/base_list.txt` (one tag per line, optional `tag: alias1, alias2`), shipped in the package, never writable through the API, fail closed at startup. Every tag scope is checked, bare and as `scope:name` (a bare rule matches any scope, `scope:name` only that scope). Normalization is `filters/aliases.fold`.
- Not yet: tag mapping is stored and edited through the API but not applied at save (no ComicInfo writer for web saves; Stash tags are saved as returned by the site); `-tag` injection into site queries.

## 9. API (first version)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/search?q=&sources=&page=&page_size=` | one search across library and sites; results grouped per section |
| GET | `/api/library/stash/images` · `/videos` · `/api/library/komga/series` · `/books` | the "See all" views |
| GET / PUT | `/api/view-settings`, `/api/view-settings/{source}` | per-source grid view (`mode` grid, wall, masonry or list; `per_page`; `zoom` 1-5), stored as `view.<source>` in the settings table (in memory in fixture mode). GET fills defaults (grid, 60, 3; nhentai 25) and returns `per_page_options` and `per_page_max`; PUT answers 422 `invalid` for an unknown source, mode, zoom, or a `per_page` outside 1 to the source cap |
| GET / PUT | `/api/player-settings` | the player's Autoplay user setting, body and answer `{"autoplay": bool}`, stored as `player.autoplay` ('1' or '0') in the settings table (in memory in fixture mode). GET answers `false` until set; PUT answers 422 for a body that is not a boolean |
| GET | `/api/library/{kind}/{id}` | item details |
| PATCH | `/api/library/{kind}/{id}` | rating (1-5, null clears), favorite, tags (full list replaces); answers the updated item |
| DELETE | `/api/library/{kind}/{id}` | move to trash; returns an undo token |
| POST | `/api/trash/{token}/restore` | undo |
| GET | `/api/trash` | list trashed items with token, expires_at, retention_days; expired entries are left out but not dropped by the GET (they are dropped on restore, on empty, or when retention purges them) |
| DELETE | `/api/trash` | Empty: permanently delete everything in the trash, returns `{removed}` (the real deletion rule 4 allows; the UI asks to confirm first). Fixture mode only for now; in real mode the route is absent (404), never an empty list |
| GET | `/api/media/...` | proxy for thumbnails, images, video (Range), book pages |
| POST | `/api/save` `{source, post_id}` | rules, dedupe (409), queue; returns job id |
| GET / POST / DELETE | `/api/jobs`, `/api/jobs/{id}`, `/retry` | queue (newest first; `?state=` CSV; jobs carry `notices`). Worker: one job per site, 2 s gap (`PEARLIE_DOWNLOAD_INTERVAL_S`), running jobs requeued at startup |
| GET / PUT | `/api/rules`; POST `/api/rules/test` | filters (base list returned read-only) |
| POST | `/api/library/komga/books/{id}/progress` | reading progress |
| GET | `/api/health` | Stash, Komga, mounts, sites, and `version` (the installed Pearlie version) |
| GET | `/api/update/status?refresh=&manual=` | installed and latest version, `available`, `checked_at`, `check_enabled`, `channel` (main or dev), runner `state` (idle, running, done, rolled_back, failed, failed_rollback), `step`, `error`, `retry_after`, `can_apply`. `refresh=1` asks GitHub (ETag, 5-minute floor per channel, rate limit honoured); it is skipped while the check is switched off unless `manual=1` (the "Check now" button) |
| PUT | `/api/update/settings` `{channel?, check_enabled?}` | channel `main` or `dev`, check on or off; 422 for an unknown value or an empty body; answers the status. Stored in the settings table (`update.channel`, `update.check`) and mirrored to `/opt/pearlie/update.conf` when that install layout exists |
| POST | `/api/update/apply` | start the update as a transient `systemd-run` unit that outlives `pearlie.service`; 202 `{state: "running"}`, 503 `unsupported` (fixture mode or no `/opt/pearlie/current`), 409 `already_running` or `up_to_date`, 500 `start_failed` |

Every mutating `/api` route (POST, PUT, PATCH, DELETE) is refused with 403 `forbidden` unless its `Origin` (or `Referer`) matches the request host (an app-wide dependency, so later routers are covered). Connections routes and `PUT /api/update/settings` also require `Content-Type: application/json` (415); `POST /api/update/apply` has no body and relies on the Origin check alone. `PEARLIE_TRUSTED_NETWORK=1` allows a non-loopback bind (Tailscale/WireGuard or a reverse proxy with login in front); without it the app refuses to start on a non-loopback host.

PATCH per side (real mode): Stash images and videos take `rating` (stored as rating100 = rating x 20) and `tags` (names are matched case-insensitively against Stash tags, missing ones are created, then rating and tags go in ONE sceneUpdate or imageUpdate mutation, so an edit is never half applied; a tag created before a failed update stays in Stash). Komga series and books take `tags` only, written to the metadata endpoint with `tagsLock: true` so a library scan does not undo the edit; a series shows the union of its own and its books' tags, so removing a tag that a book also carries leaves it in the list. A field the side cannot store answers 422 `unsupported_field` with `field` set, checked before any upstream call (Stash: any non-null `favorite`; Komga: any non-null `favorite` or `rating`); `null` or omitted is ignored. An empty tag or one over 64 characters answers 422 `invalid_tag`; an unknown or non-numeric id 404 `not_found`; Stash or Komga failing 502 `upstream_error`. Fixture mode still accepts favorite and rating on every kind until the UI hides those controls on the sides that cannot store them. DELETE stays 501 in real mode (trash design pending).

Paging fields: list and search answers carry `page` (the page actually served), `page_size`, `total`, `pages` (null where the source gives no count, such as Danbooru) and, for Stash, `stats {megapixels, size_bytes}`. `page_size` is clamped to the source cap (200 Stash, Komga, Danbooru; 100 Gelbooru, Rule34; 25 nhentai; search `page_size` above 200 is a 422). A `page` past the last one is served as the last page, never an error. With several sources in one search `page_size` is ignored (each section keeps its short preview) and the section `page_size` is null.

Auth: a login that returns a token (cookie for the web UI, bearer token for iOS).

## 10. UI

Layout A, chosen 2026-11-08 (mockups: https://claude.ai/artifact/FXZchWLeynCcAmEbJfKjbH):
- One search box with tag chips (excluded tags in red), type pills (All, Images, Videos, Books, Web).
- Results in sections: Stash images, Stash videos, Komga books (progress bar), web results ("In library" badge or save button). "See all" opens a full grid for that one source.
- Bottom bar: Search, Library, Queue, Rules.
- **Mini player:** a playing video docks above the bottom bar and keeps playing while you browse (play/pause, progress, PiP, close).
- **Bar order and widths:** the stage bar runs left to right: previous video, back 10 s, play/pause, forward 10 s, next video, seek, time, mute, volume slider, Picture-in-picture, gear, fullscreen. The 10 s buttons call `skip(-10)` / `skip(10)` and are disabled while the duration is 0 or the player failed; the mini player has none. The bar sits in a container (`container-type: inline-size`) and anchors by its bottom edge to the video. Width ladder: 680 px and wider shows everything; 600-679 px hides the volume slider (container query, mute stays); below 600 px a two-row phone layout is parked and not built.
- **Autoplay:** a gear-menu setting stored on the server (`/api/player-settings`). When on, a video starts playing as soon as it is opened and the next video in the current list starts when one ends; Loop wins (a looping video never ends), and with no next video the mini player closes at the end as before. It supersedes the 15 s chain window of `kit/designs/design-gear-menu.md`: because opening always plays while Autoplay is on, no timed window is needed. The browser's own autoplay policy can still block a start without a user tap.
- **Gear menu:** one popover opened from the gear (placed after Picture-in-picture and before Fullscreen), YouTube-style. The main list has an Autoplay switch, a Loop switch, a Speed row (value "Normal" or e.g. "1.5x") and a Quality row (hidden when the item has no alternatives); Speed and Quality open a sub-page with a "Back to settings" row, and a pick applies and returns to the list. Switches toggle on tap, Space/Enter or a drag past half the track, and never close the menu. Keyboard: arrows, Home/End, Arrow Right/Left or Backspace to enter and leave a page, Escape steps back then closes; the menu is `role="menu"` and blocks the player keys while open. Page and thumb motion are disabled under `prefers-reduced-motion`.
- **System PiP:** the browser's PiP window (Chrome/Edge, Safari macOS and iPhone; Firefox only through its own toggle; iPhone PWA mode to be tested). Native PiP in the iOS app.
- **See-all grid (paged):** one page at a time, no "Load more". The page lives in the URL (`?page=N`; pager buttons push, sort, favorites, search and per-page replace). Pager top and bottom: first, previous, "N of M" select (a number field above 200 pages), next, last, range text (with megapixels and size for Stash images). Sources with no known total (Danbooru) get a reduced pager: previous, next, "Page N". Left/Right arrow keys change page. The backend clamps a past-end page and returns the served page; the client only replaces the URL with it. Item view prev/next crosses page edges.
- **View bar:** per-page select (presets, "Custom..." up to the source's cap), four modes (Grid, Wall, Masonry, List) and a zoom slider (1-5). Stored per source in the backend (`/api/view-settings`). On phones (under 720 px) one sliders button opens a bottom sheet with the same controls. Design: `kit/designs/design-browse-grid.md`.
- **Wall overlay (core):** in Wall and Masonry mode on the Images list a plain click on a tile opens the picture in a dark viewer layer over the grid. State is the `open=image:<id>` URL param (open pushes, prev/next and page jump replace, Close goes back when the overlay was opened on the current page). Prev/next cross page edges, keys: arrows, j, l, Escape; the grid behind is inert and scroll-locked. Touch: a horizontal swipe on the picture steps prev/next (not while zoomed); on phones the layout stacks the bottom bar and keeps 44 px targets. The layer fades in over 150 ms, shows a loading state and an error box with Retry, and a picture that is gone is removed from the grid and skipped. Close after the page changed while open pops the opening entry and then replaces it with the current page without `open`, so Back does not reopen the viewer. A Fullscreen button between Zoom and Details fullscreens the viewer layer itself (state follows `fullscreenchange`, Esc leaves fullscreen first, closing the viewer exits it); it is hidden where the browser has no element fullscreen (iOS Safari). Zoom (D-13): a click or tap on the picture toggles fit and 100% (real pixels) at the spot; a plain wheel zooms between 25% and 200%; two fingers pinch with midpoint pan; a bar (minus, percent, plus) shows while zoomed; Shift+arrows pan, plain arrows navigate; zoom resets on every picture and is off while the picture is loading. Design: `kit/designs/design-wall-overlay.md`, `kit/designs/design-image-zoom.md`.
- **Options > connections (Stash, Komga):** saving a Stash or Komga address or key rebuilds that client at once (no restart); jobs already running keep the client they hold, the next job uses the new one. A restart is still flagged only when that route group was not mounted at startup because the connection was unconfigured. Each row ends with the Test button directly before the settings icon.
- **Options > System > Update card:** shows installed and latest version, the channel (main or dev) and the auto-check switch, with Check now and an icon-only update button (aria-label and title "Update to X" or "Switch to X"; no "older" label, the backend has no such flag). Update asks to confirm in a sheet, calls `POST /api/update/apply`, then polls `/api/health` every 2 s while the service restarts; it gives up after 3 min of failed polls or 10 min in total. After the page reloads, a toast reports the result (notice kept in `sessionStorage` key `pearlie.update.notice`). Logs stays LATER.
- Item view (to mock up next): full viewer, rating, favorite, tag edit, delete with Undo.

## 11. Phases

Reordered 2026-11-08: the UI comes first, as the groundwork for the backend.

1. **UI prototype:** the real Svelte frontend for every screen (search, library and item view, mini player, PiP and reader, queue and rules) on a FastAPI stub that serves fixture JSON and generated placeholder media on the section 9 paths.
2. **Backend behind the UI:** Danbooru → Stash save, save queue, base list; library browsing (Stash, Komga); filters and library editing. Each step replaces fixtures with real logic.
3. **Proxmox installer and updates** in the community-scripts style (one command on the host creates the LXC and installs Pearlie; main/dev update channels), then **Login**. Design: design-proxmox-installer (D-02, local).
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
