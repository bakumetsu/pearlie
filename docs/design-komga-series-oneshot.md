# Design: Komga series / oneshot placement (D-22)

Status: accepted (user decisions 2026-11-14). Implemented by D-22 P1-P7.

## Brief

Today every nhentai save lands flat in one Komga folder, and ComicInfo `Series` is the first parody tag (or the title). All "Original" books then share one series name, and a lone book becomes a one-book series.

The change ports the user's "Nhentai Auto-Organizer.bat" (Sort-Doujin) into Pearlie. For each save, Pearlie cleans the title, reads the author tag (`[Author]`), finds a trailing volume (`2`, `#2`, `vol 2`, `ch 12`, Roman) and a root title, and decides: series book or oneshot. A series book goes into the folder `[Author] Root` (the exact name the script makes, so existing folders are found) under the source's Komga folder (created if missing). A oneshot goes into the oneshots folder, named by the Komga library's oneshots-directory setting (read from Komga) and placed under the source's Komga folder. Komga itself does the series/oneshot split; Pearlie only places the file and writes ComicInfo `Series` (= root) and `Number` for series books. A oneshot gets no `Series`.

Matching books already in Komga uses the folder and file names on the Komga host path (Pearlie already has write access). No Pearlie index change and no Komga search call is needed. A volume 2 saved a week later joins the existing folder. When a oneshot gets a second volume, Pearlie moves the first book into the new series folder at once, with a rename only: no copy, no delete, no change to the file bytes, so Komga keeps read progress if "hash files" is on. A failed move never fails the save.

One setting (Options > Save folders) picks mode A (Pearlie decides alone) or mode C (save dialog shows the suggestion; one tap switches series/oneshot). Batch, rule and filter saves always use the suggestion. The rule applies to all saves. A new title that only starts with an existing series name ("Love Hotel Nights" vs "Love") joins that series only in mode C (shown in the sheet); mode A needs an exact root match (user decision 2026-11-14).

The user decided (2026-11-14): Komga splits; Pearlie places and writes ComicInfo, no Pearlie filter; port the script; A/C toggle; all saves; auto move.

Trade-offs and risks: the number regex gives false positives ("Love 2" alone, "What I Did", "Fate 2025"). Mode C and one tap fix single saves. Three optional hardening rules (H1–H3) cut most false positives; they are a deviation from the script and need the user's OK. Folder scan cost grows with library size (cached, capped). The moved first book keeps its old ComicInfo (no Series/Number); Komga sorts it first by name. Item 8a (Done, no book) may share a cause; it is noted, not fixed.

## Implementation map

| Part | Design sections | Files |
|---|---|---|
| P1 Name parser (pure) | 1, 1.1 | NEW `backend/app/targets/placement_name.py`, NEW test |
| P2 Existing-book match + plan | 2, 3, 6.1 | NEW `backend/app/targets/placement.py`; `backend/app/komga.py:55-63` (`list_libraries` DTO), `targets/destinations.py:190` (`resolve_site`) |
| P3 ComicInfo | 4 | `backend/app/targets/comicinfo.py:25-61` |
| P4 Save + auto move | 6, 8 | `backend/app/targets/komga.py:157-260`, `backend/app/db.py` (jobs migration), `backend/app/jobs/store.py:78` |
| P5 API + mode setting | 5.1, 5.3 | `backend/app/api/jobs_real.py:33`, `backend/app/models.py:285`, `backend/app/api/options.py` |
| P6 UI | 5.2, 5.3 | `frontend/src/lib/options/SaveFoldersCard.svelte`, `frontend/src/lib/stores/search.svelte.ts:153`, `frontend/src/routes/SeeAll.svelte:290`, new save sheet component |
| P7 Docs | all | `docs/DESIGN.md` Komga section (line ~120) |

## 1. Name parsing and the series test

Input: `post.title` (the nhentai title, e.g. `[Kisaragi] Love 2 (Original) [English]`). Output: `ParsedName(author, root, number, is_series)`.

Port of Sort-Doujin (script lines 157-217), in this order:

1. Clean: in ONE loop, strip a trailing `[...]` or `(...)` group (any order) until neither matches at the end. Deviation from the script (172-173: all `[...]` first, then all `(...)`). User decision 2026-11-14: `Love 2 [TeamX] (Original)` kept `[TeamX]` in the title with the script's order. The author rule (step 2: first `[...]`, full text kept, e.g. `[Circle (Artist)]`) does not change. The store-id rule (163-169) is dropped: nhentai titles have no store id.
2. Author tag: the first `[...]` in the cleaned name; the rest is the title part (177-180). If none, use the first `artist` tag of the post as `[Artist]`; if none, author is empty.
3. Cut at the first `~` or `〜` (182).
4. Split at the first ` - ` (spaces around); the first part is `primaryTitle` (183-184).
5. Volume regex on `primaryTitle` (185, case-insensitive): a space or `#`, an optional keyword (`v vol volume c ch chapter no issue part episode #`), an optional `.`, then a number (`2`, `1.5`) or a Roman numeral (`I`–`XXXX` letters `[IVX]{1,4}`), then end or space/dash plus anything. A match removes the suffix: that is the root, `is_series = true`.
6. Else, if there was a ` - ` part and that second part matches the same pattern alone (192), the root is `primaryTitle`, `is_series = true`.
7. Else root = `primaryTitle`, `is_series = false`. Empty root = `Unknown_Title`.

New (the script does not output a number): `number` = the first numeric token of the matched suffix (`2`, `1.5`; Roman → int), as a string; empty if none.

### 1.1 Hardening (deviation, needs the user's OK; default ON if approved)

- H1: a 4-digit number from 1900 to 2099 is not a volume (years: `Fate Grand Order 2025`).
- H2: a Roman numeral counts only as the last token (`My Sister II` yes; `What I Did Last Summer` no).
- H3: a bare number (no keyword) counts only as the last token (`Love 2 You` no; `Love 2` yes). A keyword form (`Vol. 2 Beach`, `Chapter 12 - The Beach`) may be followed by a subtitle.

Unavoidable: `[Kisaragi] Love 2` alone is parsed as volume 2 of "Love". Mode C lets the user switch it to oneshot with one tap; mode A accepts it.

### 1.2 Test table (author `[Foo]` unless shown; the "script" column was checked by a Python port of the regexes; "hardened" is what H1-H3 give)

| Title (cleaned) | Root | Number | Script | Hardened |
|---|---|---|---|---|
| `[Kisaragi] Love 2 (Original) [English]` | Love | 2 | series | series (unavoidable) |
| `[Kisaragi] Love (Original) [English]` | Love | – | oneshot | oneshot |
| `[Kisaragi] Love 3 [English] [Digital]` | Love | 3 | series | series |
| `[Mizuki] What I Did Last Summer [English]` | What / whole | 1 / – | series (false) | oneshot |
| `[Nanao] Fate Grand Order 2025 [English]` | Fate Grand Order / whole | 2025 / – | series (false) | oneshot |
| `[Nanao] Sailor Moon 3D [English]` | Sailor Moon 3D | – | oneshot | oneshot |
| `My Sister Vol. 2 [English]` | My Sister | 2 | series | series |
| `My Sister #3` | My Sister | 3 | series | series |
| `My Sister Chapter 12 - The Beach` | My Sister | 12 | series | series |
| `My Sister - 4` | My Sister | 4 | series (rule 6) | series |
| `My Sister II` | My Sister | 2 | series | series |
| `My Sister 1.5` | My Sister | 1.5 | series | series |
| `My Sister Returns` | My Sister Returns | – | oneshot in mode A (exact match only); mode C suggests joining "My Sister" if that series exists (prefix absorb) | same |
| `Dark Room ~Extra~` | Dark Room | – | oneshot | oneshot |
| `No Game No Life` | whole | – | oneshot | oneshot |
| `Part Time Lover` | whole | – | oneshot | oneshot |
| `Love 2 You` | Love / whole | 2 / – | series (false) | oneshot |
| `Love Hotel 3 (Original) [Digital]` | Love Hotel | 3 | series | series |
| `Love Hotel Nights`, author has series "Love" | Love (absorbed) | – | mode A: own oneshot (no prefix join); mode C: suggests joining "[Foo] Love" (the user can change it) | same |
| `[Foo] Love 2 [TeamX] (Original)` | Love | 2 | series (single loop; the script would keep `[TeamX]`) | series |
| `[Foo] Love (Original) [English] [TeamX] [Digital]` | Love | – | oneshot | oneshot |
| `Some Title without author 2` (no artist tag) | Some Title without author | 2 | series, empty author | same |
| `[Kisaragi] Love 4 [English]`; library already holds the script-made folder `[Kisaragi] Love` | Love | 4 | series, joins `[Kisaragi] Love` (no new folder) | same |
| `[Ao:ki] Who? 2 [English]` | Who? | 2 | series; new folder `[Aoki] Who` (`:` and `?` removed; folder made by the script is identical) | same |
| `[Foo] ... 3 [English]` (root `...`) | `...` | 3 | folder name empty after trim → `[Foo]` if author, else `Grouped_Series` | same |

### 1.3 Grouping (script 219-248, 256) against existing books

The script groups a batch by author then absorbs a root into the shortest other root of that author for which `root` starts with `shorter + whitespace`. Pearlie runs jobs one by one, so the "batch" is the set of books already on disk (section 2). Rules:

- Candidate roots for the author = names of series folders `[Author] Root` plus parsed roots of books in the oneshots folder.
- Exact match wins. Else, only in mode `suggest` (and for batch/rule saves under it), the shortest candidate that is a whole-word prefix of the new root wins (absorb) and the sheet shows it. In mode `auto` there is no absorb: exact match only, so Pearlie never guesses a join (user decision 2026-11-14).
- The reverse (new root is a prefix of an existing folder's root) does not absorb and never renames an existing folder.
- Series if: `is_series`, or a series folder exists for the group, or a oneshot of the same group exists (the group then has 2+ books, script line 256).
- Folder name, exact script format. Script line 240: `$groupKey = "$aTag $assignedRoot".Trim()`, where `$aTag` is the tag WITH its brackets (line 178: `$authorTag = $matches[1]` of `(\[[^\]]+\])`). Line 257: `$folderName = $key -replace '[<>:"/\\|?*]', ''`, line 258: `$folderName = $folderName.TrimEnd('. ')`, lines 259: empty → `Grouped_Series`. So the folder is `[Author] Root` (brackets kept: `[` `]` are not in the removed set), one space, no author → just `Root`. Pearlie writes this exact format, so folders made by the script and by Pearlie are the same and one scan reads both. Matching compares the folder name after the same sanitizing, case-insensitively (Windows-made names), against the sanitized `[Author] Root` of the candidate.

## 2. Matching books already in Komga

Data source: the Komga host path (Pearlie writes there already; `komga.py:94-107` `_check_writable`). One `os.scandir` of the source's series root (folder names, in the script's `[Author] Root` format of 1.3, so folders the organizer script made are found) and one of the source's oneshots folder (file names, parsed with section 1). Both scans are per source. No Komga search, no new database column.

Why not Pearlie's index: `saved_items` (db.py:30) has no title, author or path, and it misses books the user added to Komga another way. Why not the Komga API: a text search per save is slower, fuzzy, and still needs path mapping; the Komga API is used only for libraries (`list_libraries`) and the scan.

Cost: two directory listings per save; a name index (author → roots) is built from them and cached for 30 s, dropped after Pearlie places or moves a file. A listing is capped at 50 000 entries; above that the index is skipped with a `placement_index_too_large` notice and the book is treated as new. Series-only matching by ComicInfo `Series` of books Pearlie did not name is out of scope.

## 3. The oneshots folder

- Read from Komga: `GET /api/v1/libraries` (already called in `_roots`, komga.py:88) returns per library `oneshotsDirectory`. Take the library whose root holds the source folder.
- Semantics (reviewer's view, verify in swagger at coding): the value is a folder NAME (e.g. `_oneshots`) that Komga treats as oneshots at any depth inside the library, not a path. Design for that: oneshots go in `<source series root>/<name>`, and the oneshot scan (section 2) is per source, in that folder only. Fallback only if swagger shows a path: resolve relative-to-library-root or absolute, then map to the Pearlie path with the prefix pair of `validate_komga_folder` (`komga_path_prefix_komga` → `komga_path_prefix_pearlie`); the folder must be inside the library.
- The oneshots folder under the source series root is created if missing (`mkdir`), so a book in it and in the series folders sit in one library. Section 2 scans only that folder for oneshots. A name that also starts with a dot or contains a separator is refused (`oneshots_not_set` notice).
- No Options field: one source of truth, no drift. Options > Save folders shows a read-only line "Oneshots: <folder>" or "Not set in Komga".
- One library, two folders: the series root stays the per-source folder from `destinations.resolve_site` (komga.py:76, falls back to `komga_incoming_dir`); the oneshots folder is derived from it (name from the library), so there is no second per-source setting. Both are under the same root, so the move (section 6) is one rename on one volume.
- If the library has no oneshots directory: a oneshot is saved flat in the series root as today, with notice `oneshots_not_set` ("set the oneshots directory in Komga"). Series books are unaffected.

## 4. ComicInfo

`comic_info(post, page_count)` (comicinfo.py:25) gains `placement`:

- Series book: `<Series>` = root (script 271); `<Number>` = parsed number when present. Komga groups by folder, so author-clashing roots stay apart by folder, not by this tag.
- Oneshot: no `<Series>` and no `<Number>` (Komga names a oneshot after its book title). Line 36 (`parody[0] else title`) is removed for both. The parody tag is not lost: it already goes into `<Tags>` via `general` only if the source puts it there; adding `parody` to `<Tags>` is optional and not part of this design.
- `Title`, `Writer`, `Penciller`, `Genre`, `LanguageISO`, `PageCount`, `Web` stay. The CBZ stays byte-repeatable for the same inputs; the MD5 in `saved_items` is the MD5 of the file as placed.
- Existing saved books are not rewritten.

## 5. The mode setting and the dialog

### 5.1 Setting
`settings` table key `komga.place_mode` = `auto` | `suggest` (default `suggest`, planner pick in T-179). Read/written through the Options API (`api/options.py`); part of the `/api/options` payload.

### 5.2 UI (rule 7)
- Options > Save folders, under the Komga rows: a two-segment switch, icons with a short label under each (wand "Auto", pointer "Suggest"); each segment at least 44 × 44 px. A one-line hint under it. Pick icons with the lucide-icons skill at coding.
- Mode `suggest`: the Save button on a nhentai-to-Komga item opens a small sheet (bottom on phone, centred on desktop): line 1 "Series  [Foo] My Sister · vol 2" or "Oneshot"; line 2 a one-tap chip "Make oneshot" / "Make series"; a 44 px Save button. Close = no save. The sheet loads `GET /api/save/placement` (5.3); while loading it shows the Save button disabled.
- Mode `auto`: Save works as today (no sheet).
- Batch, rule and filter saves: no sheet in either mode; they call `POST /api/save` without `placement`.

### 5.3 API
- `GET /api/save/placement?source=&post_id=` → `{kind: "series"|"oneshot", series: str|null, number: str|null, joins_existing: bool, moves_first: bool, reason: str}`. Pure: no file is written.
- `POST /api/save` body gains optional `placement: {kind: "series"|"oneshot"}` (the series name is always recomputed). Absent = the suggestion. The decision is made again inside the worker when the job runs, so two jobs of one batch see each other's files (jobs run one at a time per site, rule 5). The override is stored in a new `jobs.placement` TEXT column (nullable, ALTER migration in `db.py:83-99`).
- Applies to every nhentai → Komga save (manual, rule, filter), since all go through `KomgaTarget.save`.

## 6. Placement and the automatic move

### 6.1 Flow in `KomgaTarget.save` (komga.py:157)
1. Duplicate check as today.
2. Parse + plan (sections 1-3) → `Placement(kind, folder, number, move_from?)`.
3. Build the CBZ in the temp folder with the new ComicInfo (as today, `.part`, MD5).
4. Series: `mkdir` the series folder (parents ok); oneshot: the oneshots folder. `_place` (komga.py:222) does the rename and name-clash `_2` as today.
5. If `move_from` is set (a oneshot of the same group exists) → section 6.2.
6. Insert into `saved_items`; one `scan_library` call for the whole job.

### 6.2 Auto move of the first book
- Trigger: the new book becomes a series book (it has a number, OR a series folder exists for its group, OR it is a oneshot pair: the new book has no number but the oneshots folder already holds a book of the same author+root group) and the oneshots folder holds a book of that group. The pair case also makes a series: both books go to `[Author] Root`, the new one without Number, the old one moved. Several old oneshots of the group are all moved.
- How: `os.rename(old, series_folder / old.name)` on the Pearlie path. A rename on one volume only. If it fails (`EXDEV`, permission, target exists with another MD5) the move is skipped: no copy-and-delete fallback.
- The file bytes are not changed. Its MD5 and name stay; the old ComicInfo stays (no Series/Number). Komga sorts that book first inside the series by name (e.g. "Love" before "Love 2").
- Order: first place the new book (step 4), then rename the old one, then one scan. If the rename fails, the series holds only the new book; the old one stays a oneshot.
- Read progress: Komga treats a moved file as a new book unless it matches a removed book by file hash. This works only if the Komga library option "Hash files" is on; if off, progress on the first book is lost. Pearlie cannot read that option reliably, so Options > Save folders shows a one-line note under the oneshots line. Open question 3.
- Rule 1: no second copy exists at any time. Rule 4: nothing is deleted; a move is a rename. A record row in the log (below) is enough to move the book back by hand; an in-app "move back" button is out of scope.
- Failure handling: the save stays `Done` with notice `move_failed` ("first book stays in oneshots"); log at WARNING with code. A missing source file at move time (user removed it) = notice `move_skipped`, no error.

### 6.3 Log lines (logger `pearlie.komga`, one line, `key=value`, same tag prefix as komga.py:160)
- `KOMGA source=nhentai post=ID placement kind=series root_hash=… number=2 via=folder|new|absorb|oneshot_pair mode=auto|suggest|override`
- `KOMGA … oneshots dir=<komga path> via=komga|none`
- `KOMGA … move start from=<name> to=<folder name>` / `move done` / `move failed code=<errno name>`
- No author or title text in the log beyond what the existing `place` lines already log (file name).

## 7. Item 8a (Done jobs, no book in Komga)

Possible shared cause, not confirmed and not fixed here: the CBZ is placed flat in `komga_incoming_dir`; if that equals a library root (or a folder Komga does not treat as a series folder), Komga may not create a book from a loose file, while Pearlie logs "scan requested". The new series/oneshots layout removes loose files, which would hide the symptom, so the 8a card (verify after scan, log Pearlie-side path) stays useful and needs the user's folder check first. The Series = "Original" merge is a cosmetic issue only (Komga groups by folder).

## 8. Proposed coding cards (S/M each; order top to bottom)

1. **feat-placement-name-parser** (S): P1. Pure function + table test from 1.2 (script and hardened variants). No I/O.
2. **feat-placement-index-plan** (M): P2. Verify first in swagger: the `oneshotsDirectory` field is a folder name or a path (section 3). Directory scans, name index, absorb rules, oneshots dir from `list_libraries`, path mapping, caching. Tests with `tmp_path` and a mocked Komga.
3. **feat-comicinfo-series-number** (S): P3. `comic_info` / `build_cbz` take the placement; tests for series, oneshot, no-number.
4. **feat-komga-save-placement** (M): P4. Use the plan in `KomgaTarget.save`, create folders, oneshots folder, move step, notices, log lines, `jobs.placement` migration. Needs cards 1-3.
5. **feat-placement-api-mode** (S): P5. `GET /api/save/placement`, `SaveBody.placement`, `komga.place_mode` option, `schema.gen.ts` update.
6. **feat-placement-ui** (M): P6. Options switch + read-only oneshots line + the save sheet in `suggest` mode. Needs card 5.
7. **docs-placement** (S): P7 (can go into card 6).
Related, separate: **fix-komga-save-verify** (T-179 card 9, item 8a).

## 9. Open questions for the user

1. Accept hardening H1-H3 (section 1.1)? Recommendation: yes.
2. Default mode `suggest`? Recommendation: yes.
3. The first book moved without a ComicInfo rewrite loses read progress if the Komga library has "Hash files" off. Accept, or rewrite ComicInfo (changes the hash, progress is then always lost)? Recommendation: accept.
4. DECIDED 2026-11-14 (user, option 3): prefix absorb (`Love Hotel Nights` into `Love`) only in mode C; mode A uses exact match only. Q1-Q3 accepted.
