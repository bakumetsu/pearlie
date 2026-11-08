<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { getApi } from "../lib/api/client";
  import { getRouter } from "../lib/ctx";
  import type { Match } from "../lib/router";
  import { createRules } from "../lib/stores/rules.svelte";
  import Icon from "../lib/components/Icon.svelte";
  import type { ListKey } from "../lib/rules/draft";

  let { match }: { match: Match } = $props();
  const router = getRouter();
  const rules = createRules(getApi());

  const TARGETS = ["stash_tag", "comicinfo:Tags", "comicinfo:Genre", "comicinfo:Writer", "comicinfo:Series"] as const;

  const SECTIONS: { key: ListKey; title: string; hint: string }[] = [
    { key: "reject", title: "Reject", hint: "Posts with these tags are hidden and never saved." },
    { key: "warn", title: "Warn", hint: "Posts with these tags are shown with a warning." },
    { key: "require", title: "Require", hint: "Optional. When set, a post must carry at least one of these tags." },
  ];

  let inputs = $state<Record<string, string>>({ reject: "", warn: "", require: "" });
  let mapPattern = $state("");
  let mapTarget = $state<typeof TARGETS[number]>("stash_tag");
  let testerText = $state("");
  let baseOpen = $state(false);
  let importError = $state<string | null>(null);
  let leaveTo = $state<string | null>(null);

  let h1: HTMLHeadingElement | undefined = $state();
  let fileInput: HTMLInputElement | undefined = $state();
  let stayBtn: HTMLButtonElement | undefined = $state();

  onMount(() => {
    h1?.focus();
    rules.load();
    rules.loadHealth();
  });

  onDestroy(() => {
    rules.destroy();
  });

  function add(key: ListKey) {
    rules.addTo(key, inputs[key]);
    inputs[key] = "";
  }

  function addMapRow() {
    rules.addMap(mapPattern, mapTarget);
    mapPattern = "";
  }

  function doExport() {
    const text = rules.exportText();
    if (!text) return;
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "pearlie-rules.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  function onFile() {
    const file = fileInput?.files?.[0];
    if (!file) return;
    file.text().then((text) => {
      const result = rules.importText(text);
      importError = result.ok ? null : result.error;
      if (fileInput) fileInput.value = "";
    });
  }

  // Unsaved-leave guard: intercept internal navigation clicks
  $effect(() => {
    if (!rules.dirty) return;
    const handler = (e: MouseEvent) => {
      const el = e.target as HTMLElement;
      const anchor = el.closest("a[href]") as HTMLAnchorElement | null;
      if (anchor) {
        const href = anchor.getAttribute("href") ?? "";
        if (
          href.startsWith("/") &&
          anchor.getAttribute("target") !== "_blank" &&
          !e.metaKey &&
          !e.ctrlKey &&
          !e.shiftKey &&
          !e.altKey
        ) {
          e.preventDefault();
          e.stopPropagation();
          leaveTo = href;
        }
      }
    };
    document.addEventListener("click", handler, true);
    return () => document.removeEventListener("click", handler, true);
  });

  // beforeunload guard
  $effect(() => {
    if (!rules.dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  });

  // Focus stay button when leave prompt appears
  $effect(() => {
    if (leaveTo !== null) {
      stayBtn?.focus();
    }
  });

  function confirmLeave() {
    const to = leaveTo;
    leaveTo = null;
    rules.discard();
    if (to) router.navigate(to);
  }

  function chipClass(state: string): string {
    if (state === "ok") return "ok";
    if (state === "down") return "down";
    return "neutral";
  }

  function statusLabel(state: string): string {
    if (state === "ok") return "OK";
    if (state === "down") return "Down";
    if (state === "not_configured") return "Not configured";
    return state;
  }

  function decisionLabel(d: string): string {
    if (d === "allow") return "Allowed";
    if (d === "warn") return "Warning";
    if (d === "reject") return "Rejected";
    if (d === "require_missing") return "Missing a required tag";
    return d;
  }
</script>

<div class="content">
  <h1 tabindex="-1" bind:this={h1}>Rules</h1>

  {#if rules.status === "loading"}
    <div class="skel"></div>
    <div class="skel"></div>
    <div class="skel"></div>
  {:else if rules.status === "error"}
    <p>Could not load the rules.</p>
    <button class="btn" onclick={() => rules.load()}>Retry</button>
  {:else if rules.draft !== null}
    {#each SECTIONS as sec}
      <section class="card">
        <h2>{sec.title}</h2>
        <p class="hint">{sec.hint}</p>
        <ul class="chips">
          {#each rules.draft[sec.key] as tag}
            <li class="tagchip">
              {tag}
              <button type="button" aria-label="Remove {tag}" onclick={() => rules.removeFrom(sec.key, tag)}>
                <Icon name="x" size={14} />
              </button>
            </li>
          {/each}
        </ul>
        <form class="addrow" onsubmit={(e) => { e.preventDefault(); add(sec.key); }}>
          <input type="text" aria-label="Add to {sec.title}" placeholder="Add a tag" bind:value={inputs[sec.key]} />
          <button class="btn icon" type="submit" aria-label="Add">
            <Icon name="plus" size={18} />
          </button>
        </form>
      </section>
    {/each}

    <!-- Tag mapping -->
    <section class="card">
      <h2>Tag mapping</h2>
      <ul class="chips">
        {#each rules.draft.mapping as m, i}
          <li class="maprow">
            <span class="pattern">{m.pattern}</span>
            <Icon name="arrow-right" size={16} />
            <select
              aria-label="Target for {m.pattern}"
              value={m.to}
              onchange={(e) => rules.setMapTarget(i, e.currentTarget.value as typeof TARGETS[number])}
            >
              {#each TARGETS as t}
                <option value={t}>{t}</option>
              {/each}
            </select>
            <button class="btn icon" aria-label="Remove mapping {m.pattern}" onclick={() => rules.removeMap(i)}>
              <Icon name="x" size={16} />
            </button>
          </li>
        {/each}
      </ul>
      <form class="addrow" onsubmit={(e) => { e.preventDefault(); addMapRow(); }}>
        <input type="text" aria-label="Mapping pattern" placeholder="Pattern" bind:value={mapPattern} />
        <select aria-label="Mapping target" bind:value={mapTarget}>
          {#each TARGETS as t}
            <option value={t}>{t}</option>
          {/each}
        </select>
        <button class="btn icon" type="submit" aria-label="Add mapping">
          <Icon name="plus" size={18} />
        </button>
      </form>
    </section>

    <!-- Base list -->
    <section class="card">
      <button type="button" aria-expanded={baseOpen} onclick={() => (baseOpen = !baseOpen)} class="btn basetoggle">
        Base list ({rules.body?.base_list?.tags?.length ?? 0})
        {#if baseOpen}<Icon name="chevron-down" size={16} />{:else}<Icon name="chevron-right" size={16} />{/if}
      </button>
      {#if baseOpen}
        <ul class="chips">
          {#each rules.body?.base_list?.tags ?? [] as tag}
            <li class="tagchip readonly">{tag}</li>
          {/each}
        </ul>
        <p class="hint">Read-only</p>
      {/if}
    </section>

    <!-- Tester -->
    <section class="card">
      <h2>Tester</h2>
      <input
        type="text"
        aria-label="Test tags"
        placeholder="Type tags to test"
        value={testerText}
        oninput={(e) => {
          testerText = (e.currentTarget as HTMLInputElement).value;
          rules.setTesterTags(testerText.split(/[\s,]+/).filter(Boolean));
        }}
      />
      {#if rules.tester.result}
        <p class="testres" role="status">
          <span class="chip {rules.tester.result.decision}">{decisionLabel(rules.tester.result.decision)}</span>
          {rules.tester.result.layer ? "layer: " + rules.tester.result.layer : ""}
          {rules.tester.result.rule ? "rule: " + rules.tester.result.rule : ""}
        </p>
      {/if}
    </section>

    <!-- Import / Export -->
    <section class="card">
      <div class="addrow">
        <button class="btn" onclick={() => fileInput?.click()}>
          <Icon name="upload" size={16} />
          Import
        </button>
        <button class="btn" onclick={doExport}>
          <Icon name="download" size={16} />
          Export
        </button>
      </div>
      {#if importError}
        <p class="err" role="alert">{importError}</p>
      {/if}
      <input type="file" accept="application/json,.json" bind:this={fileInput} onchange={onFile} style="display:none" />
    </section>

    <!-- Status -->
    <section class="card">
      <h2>Status</h2>
      {#if rules.health}
        <ul class="statusrows">
          <li><span>Stash</span><span class="chip {chipClass(rules.health.stash.state)}">{statusLabel(rules.health.stash.state)}</span></li>
          <li><span>Komga</span><span class="chip {chipClass(rules.health.komga.state)}">{statusLabel(rules.health.komga.state)}</span></li>
          <li><span>Database</span><span class="chip {chipClass(rules.health.db === "ok" ? "ok" : "down")}">{statusLabel(rules.health.db === "ok" ? "ok" : "down")}</span></li>
          {#each rules.health.mounts as mount}
            <li><span>Mount {mount.name}</span><span class="chip {chipClass(mount.state)}">{statusLabel(mount.state)}</span></li>
          {/each}
          {#each rules.health.sites as site}
            <li><span>{site.id}</span><span class="chip {chipClass(site.state)}">{statusLabel(site.state)}</span></li>
          {/each}
        </ul>
      {:else if rules.healthError}
        <p class="hint">Status unavailable.</p>
      {/if}
    </section>

    <!-- Leave prompt -->
    {#if leaveTo !== null}
      <div class="leave" role="alertdialog" aria-label="Leave this page?">
        <span>Discard your unsaved changes and leave?</span>
        <div class="addrow">
          <button class="btn" bind:this={stayBtn} onclick={() => (leaveTo = null)}>Stay</button>
          <button class="btn primary" onclick={confirmLeave}>Leave</button>
        </div>
      </div>
    {/if}

    <!-- Save bar -->
    {#if rules.dirty}
      <div class="savebar" role="region" aria-label="Unsaved changes">
        <span>Unsaved changes: {rules.summary}</span>
        <button class="btn" onclick={() => rules.discard()}>Discard</button>
        {#if rules.conflict}
          <span>Rules changed elsewhere.</span>
          <button class="btn" onclick={() => rules.reload()}>Reload</button>
        {:else}
          <button class="btn primary" disabled={rules.saving} onclick={() => rules.save()}>Save</button>
        {/if}
      </div>
    {/if}
  {/if}
</div>

<style>
  .content {
    max-width: var(--content-max);
    margin: 0 auto;
    padding: var(--s-5);
    padding-bottom: 96px;
    display: flex;
    flex-direction: column;
    gap: var(--s-4);
  }

  .skel {
    height: 96px;
    background: var(--surface);
    border-radius: var(--r-md);
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    padding: var(--s-4);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-2);
    list-style: none;
    padding: 0;
  }

  .tagchip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 4px 4px 10px;
    border-radius: 999px;
    background: var(--accent-bg);
  }

  .tagchip button {
    width: 28px;
    height: 28px;
    background: transparent;
    border: none;
    color: inherit;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  input,
  select {
    min-height: 44px;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--line-strong);
    border-radius: var(--r-sm);
    padding: 0 var(--s-3);
  }

  .btn {
    min-height: 44px;
    min-width: 44px;
    padding: 0 var(--s-4);
    background: transparent;
    color: var(--text);
    border: 1px solid var(--line-strong);
    border-radius: var(--r-sm);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    cursor: pointer;
  }

  .btn.primary {
    background: var(--accent);
    color: #0b1220;
    border-color: var(--accent);
  }

  .btn.icon {
    width: 44px;
    height: 44px;
    padding: 0;
  }

  .basetoggle {
    width: 100%;
    justify-content: space-between;
  }

  .addrow {
    display: flex;
    gap: var(--s-2);
    align-items: center;
  }

  .addrow input,
  .addrow select {
    flex: 1;
  }

  .maprow {
    display: grid;
    grid-template-columns: 1fr auto auto auto;
    align-items: center;
    gap: var(--s-2);
    width: 100%;
  }

  .statusrows {
    list-style: none;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
  }

  .statusrows li {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .savebar,
  .leave {
    position: sticky;
    bottom: var(--s-4);
    display: flex;
    align-items: center;
    gap: var(--s-3);
    justify-content: space-between;
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--r-md);
    padding: var(--s-3) var(--s-4);
  }

  .chip {
    display: inline-flex;
    gap: 4px;
    font-size: var(--t-12);
    padding: 2px 8px;
    border-radius: 999px;
  }

  .chip.ok,
  .chip.allow {
    background: var(--ok-bg);
    color: var(--ok-fg);
  }

  .chip.down,
  .chip.reject,
  .chip.require_missing {
    background: var(--danger-bg);
    color: var(--danger-fg);
  }

  .chip.warn {
    background: var(--progress);
    color: #1a1204;
  }

  .chip.neutral {
    background: var(--line);
    color: var(--muted);
  }

  :focus-visible {
    outline: 2px solid var(--accent);
  }

  .err {
    color: var(--danger-fg);
  }

  .hint {
    color: var(--muted);
    font-size: var(--t-13);
  }
</style>
