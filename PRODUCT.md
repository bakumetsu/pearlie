# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
Existing codebase: Svelte 5 (runes) + TypeScript + Vite single-page app, served as static files by FastAPI (docs/DESIGN.md section 3). A native iOS client follows later on the same JSON API.

## Users
One person (the owner) running a private, self-hosted media library at home. Single user; multiple users and public exposure are out of scope. They reach the app through Tailscale/WireGuard or a reverse proxy with login, mostly on a desktop browser first, later on a phone. The job: find something in the library or on the booru/nhentai sites with a few tag chips, look at it, and save it into the library already tagged, without duplicates.

## Product Purpose
Pearlie is a self-hosted media hub in front of Stash (images, videos) and Komga (series, books). It lets the owner browse the library and external sites (Danbooru, Gelbooru, Rule34, nhentai) in one place, save from the sites into Stash or Komga with tag rules applied, and keep the library clean. Success: a search-to-saved round trip takes seconds, nothing is saved twice, nothing disappears without an Undo.

## Positioning
Not another gallery or downloader: Stash and Komga remain the library, Pearlie is only the front door that searches, filters by the owner's own tag rules, saves and queues. A neighbouring product would have to keep its own copy of the media; Pearlie never does.

## Operating Context
Used in long browsing sessions, mostly with dense thumbnail grids, a tag chip search field, and a video that must keep playing while navigating. Sources are throttled and polite (one download per site at a time), so saves go through a visible queue. Content can be adult; items matching a "warn" tag are shown blurred with a label, rejected items never arrive.

## Capabilities and Constraints
- Stash and Komga are the library; Pearlie stores only jobs, rules, the saved-item index and trash records.
- Thin client: the UI only calls the backend JSON API; no logic, no secrets, no Stash/Komga keys in the browser.
- No delete without undo (trash folder + Undo toast, retention set by the user).
- Outbound calls only to configured sites, Stash and Komga; fonts and icons are self-hosted.
- No login yet (until T-06): dev servers bind 127.0.0.1 only.
- Desktop first; phone layout, light theme, PWA, bulk select and webtoon reader mode are deliberately later or out of scope.
- Touch targets at least 44 px, also on desktop; no hover-only controls.

## Brand Commitments
Name: Pearlie. Binding visual decisions made by the user on 2026-11-08: keep the mockup look (dark, Inter, blue accent); icons over text in tight bars; no clutter.

## Evidence on Hand
No real users, testimonials or metrics. Media in the prototype is generated placeholder plates served by a fixture stub; no real servers or sites are touched. Mockups (layout A, 390 px phone reference) exist in the planning history, not in the repo.

## Product Principles
1. The library belongs to Stash and Komga; Pearlie never owns a second copy.
2. Calm and scannable over expressive: media is the content, the interface recedes.
3. Reversible by default: every destructive action has an Undo.
4. Be polite to sites and explicit about queue state; never hide what is happening.
5. Keep the client thin: one JSON API, so the web UI and the later iOS app stay interchangeable.

## Accessibility & Inclusion
Text contrast at least 4.5:1, 44 px touch targets, full keyboard operation, dialogs trap and restore focus, colour is never the only signal, `prefers-reduced-motion` respected.
