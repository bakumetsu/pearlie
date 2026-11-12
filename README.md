# Pearlie

A self-hosted media hub. Browse your Stash and Komga libraries and booru/nhentai-style
sites in one place, and save from the sites into Stash or Komga with your own tag filters.

- **Stash and Komga stay the library.** Pearlie stores only its own data: jobs, rules,
  an index of what it saved (source, post id, MD5) and trash records. It never keeps a
  second copy of your media.
- **Never expose it directly.** Pearlie has no login of its own. Reach it through
  Tailscale/WireGuard or a reverse proxy with login. It only calls the sites you
  configure, plus your Stash and Komga.
- **Secrets stay local.** API keys and site cookies live in `.env` (or are typed into the
  Options page, write-only and stored encrypted). They are never logged and never sent to
  the browser.

Deletes go to a Pearlie trash with an Undo, and each site is throttled (one download at a
time per site by default). The backend holds all logic; the web UI only calls its JSON API.
Design notes are in [docs/DESIGN.md](docs/DESIGN.md).

## Install on Proxmox

Creates a Debian 13 LXC (1 CPU, 1 GB, 4 GB) in community-scripts style. Run on the Proxmox host:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/bakumetsu/pearlie/main/ct/pearlie.sh)"
```

To use real media, first mount the Stash Temp and Stash Other shares on the Proxmox host
shell (NFS or any other method), then run the installer and give it those host folders.
Answer `N` to run in fixture mode. The installer never asks for an NFS IP and never edits
fstab. On OMV, set `all_squash,anonuid=<Stash/Komga UID>,anongid=<GID>` on both exports so
files Pearlie writes belong to the Stash/Komga user.

Pearlie has no login of its own: reach it only over Tailscale or a reverse proxy. Update with `update` in the container or from Options > System.

## Dev setup

Needs Python 3.12+ and Node.js.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
cd ..\frontend
npm install
cd ..
deploy\dev.ps1
```

`deploy\dev.ps1` starts the backend on `127.0.0.1:8000` and the Vite dev server. By default
it runs in **fixture mode**: generated stub data, no calls to Stash, Komga or any site.
`deploy\dev.ps1 -Real` runs in real mode against what you set in `.env`
(copy [.env.example](.env.example) to `backend/.env` first).

Tests use mocked sites, Stash and Komga:

```powershell
cd backend; .venv\Scripts\python -m pytest
cd ..\frontend; npm test
```

## Status

Early development (v0.1.0). A Proxmox installer is coming; until then run it from source.

## License

[MIT](LICENSE)
