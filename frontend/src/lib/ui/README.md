# src/lib/ui: primitives (T-441)

Every primitive renders under `.ui-root` (rendered in place, no Portal). Source of "today's control": `kit/reports/D-07-design-web-ui-redesign/CONTROL-TABLE.md` and the files it names. Screen cards (T-442+) move each screen to these.

**`!` utilities.** Old unlayered `button { color: inherit; font: inherit }` in `lib/tokens.css` beats Tailwind layered utilities, so every `<button>` primitive marks its text color and weight with `!` (`text-*!`, `font-semibold!`). Drop them when `tokens.css` goes (T-451).

| Primitive | Today's control (file:line) | Built with | `!` utilities |
|---|---|---|---|
| Button (default, outline, ghost, destructive, pill, chip) | Queue Clear finished Queue.svelte:79-81; Trash Empty/Cancel Trash.svelte:48-56,140-149; Library chips Library.svelte:163-173; Library filter chips :175-198 | plain Svelte | `font-semibold!`, `text-primary-foreground!`, `text-foreground!`, `text-destructive!`, `text-muted-foreground!`, `hover:text-foreground!`, `aria-pressed:text-primary!` |
| IconButton | Queue Retry/Remove Queue.svelte:109-126,138-146; Trash Restore/Delete Trash.svelte:119-123; SelectBar.svelte:17-31 | plain Svelte (Button variants) | same as Button |
| Input, Textarea, Select (native) | TrashRetentionCard.svelte:130-142 (number input); ViewBar.svelte:114 (Enter commits) | plain Svelte | none (not buttons) |
| Switch | components/Switch.svelte (same role=switch contract, Space/Enter); DiscoverRailCard.svelte:22-28 | plain Svelte | none |
| Slider (native range) | ImageViewerCard.svelte:50-65 | plain Svelte | none |
| Checkbox | Tile.svelte:273-283 select circle is its own control; no form checkbox today | plain Svelte | none |
| RadioGroup | no radio today; own roving arrow keys | plain Svelte | none |
| Badge, Card, Separator, Skeleton | Queue state chip Queue.svelte:109-126; Options cards sections.ts:40-274; DebugKeyCard.svelte:191 (skel) | plain Svelte | none |
| Tabs | Library source chips Library.svelte:163-173; Options section list sections.ts:40-274 | bits-ui Tabs | `text-muted-foreground!`, `hover:text-foreground!`, `data-[state=active]:text-primary!` |
| Tooltip | icon buttons with `title` (Queue.svelte:109-126, Trash.svelte:119-123) | bits-ui Tooltip | none |
| Popover | ViewBar.svelte:93 (Escape closes, focus back to button), FilterPanel.svelte:55 | bits-ui Popover | none |
| DropdownMenu | Library filter Library.svelte:175-198; ViewBar.svelte:228,282 | bits-ui DropdownMenu | `aria-checked:text-primary!` (menu item) |
| Dialog, Sheet | FilterSheet.svelte:37, ViewBar.svelte:190, PlacementSheet.svelte:50, ConnectionPopup.svelte:192 | bits-ui Dialog | none |
| AlertDialog | Trash Empty confirm Trash.svelte:140-149; shrink confirm TrashRetentionCard.svelte:155-173 | bits-ui AlertDialog | none |
| Toaster, undoToast | components/Toast.svelte:28,33 (Undo, Dismiss), stores/toasts.svelte.ts | plain Svelte | `text-primary!`, `font-semibold!` |
| Tile | Tile.svelte:220-284 (site mark, In library badge, select circle, favorite) | plain Svelte | none |
| SiteMark | Tile.svelte:220-222, SiteMarks.svelte:164-172 (icon, letter fallback) | plain Svelte | none |
| ChipField | components/ChipField.svelte:62 (same keys) | plain Svelte | none |
| PageHeader, EmptyState | Trash.svelte:48-56, :78-82; Queue.svelte:51 | plain Svelte | none |

Skipped on purpose (design: "only where needed"): ScrollArea, Command.

Tests: `ui.test.ts` (vitest), `../touchTargets.test.ts` (44 px class check). Browser checks in `e2e/` (stub :8010, `vite --config vite.stub.config.ts` :5183): `computed-style.mjs`, `keyboard.mjs` (Popover and DropdownMenu keys), `shots.mjs`, `old-screens.mjs`, `diff.mjs`.
