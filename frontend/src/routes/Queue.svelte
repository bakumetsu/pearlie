<script lang="ts">
  import { onMount } from "svelte";
  import { getJobs, getRouter } from "../lib/ctx";
  import { linkClick } from "../lib/router";

  import Icon from "../lib/components/Icon.svelte";
  import {
    etaLabel,
    stateInfo,
    canRetry,
    canRemove,
    removeLabel,
    attentionText,
    needsFolderFix,
    routeFor,
  } from "../lib/jobs/group";
  import type { Job } from "../lib/jobs/group";



  const jobs = getJobs();
  const router = getRouter();

  let h1: HTMLHeadingElement;

  onMount(() => {
    h1.focus();
    jobs.refresh();
  });
</script>

<div class="content">
  <h1 tabindex="-1" bind:this={h1}>Queue</h1>

  {#if jobs.offline}
    <div class="offline" role="status"><Icon name="alert" size={16} /> Offline, retrying</div>
  {:else if jobs.error}
    <div class="offline" role="status"><Icon name="alert" size={16} /> {jobs.error}</div>
  {/if}

  {#if !jobs.loaded}
    <div class="skel"></div>
    <div class="skel"></div>
    <div class="skel"></div>
  {:else if jobs.items.length === 0}
    <p class="empty">The queue is empty</p>
  {:else}
    {#if jobs.groups.active.length > 0}
      <section>
        <h2>Active <span class="count">{jobs.groups.active.length}</span></h2>
        <ul class="list">
          {#each jobs.groups.active as job (job.id)}
            {@render row(job)}
          {/each}
        </ul>
      </section>
    {/if}

    {#if jobs.groups.attention.length > 0}
      <section>
        <h2>Needs attention <span class="count">{jobs.groups.attention.length}</span></h2>
        <ul class="list">
          {#each jobs.groups.attention as job (job.id)}
            {@render row(job)}
          {/each}
        </ul>
      </section>
    {/if}

    {#if jobs.groups.done.length > 0}
      <section>
        <h2>
          Done <span class="count">{jobs.groups.done.length}</span>
          <button class="btn" onclick={() => jobs.clearFinished()}>
            <Icon name="trash" size={14} /> Clear finished
          </button>
        </h2>
        <ul class="list">
          {#each jobs.groups.done as job (job.id)}
            {@render row(job)}
          {/each}
        </ul>
      </section>
    {/if}
  {/if}
</div>

{#snippet row(job: Job)}
  {@const route = routeFor(job)}
  {@const info = stateInfo(job.state)}
  {@const eta = etaLabel(job)}
  <li class="row">
    <img src={job.thumb_url} alt="" decoding="async" />
    <div class="text">
      <span class="title">
        {#if route !== null && job.state === "done"}
          <a href={route} onclick={(e) => linkClick(e, router)}>{job.title}</a>
        {:else}
          <span>{job.title}</span>
        {/if}
      </span>
      <span class="muted">{job.source} → {job.target === "stash" ? "Stash" : "Komga"}</span>
      <span class="chip {job.state}">
        <Icon name={info.icon} size={14} /> {info.label}
      </span>
      {#if job.state === "done" && job.dest_path}
        <span class="muted path">{job.dest_path}</span>
      {/if}
      {#if eta}
        <span class="eta">{eta}</span>
      {/if}
      {#if job.state === "running"}
        <div
          class="bar"
          role="progressbar"
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow={Math.round(job.progress * 100)}
        >
          <div class="fill" style:width="{Math.round(job.progress * 100)}%"></div>
        </div>
      {/if}
      {#if job.state === "failed" || job.state === "needs_click"}
        <p class="attn">{attentionText(job)}</p>
        {#if needsFolderFix(job)}
          <a class="fix" href="/options/save-folders" onclick={(e) => linkClick(e, router)}>Set the save folder</a>
        {/if}
      {/if}
    </div>
    <div class="actions">
      {#if canRetry(job)}
        <button aria-label="Retry" onclick={() => jobs.retry(job.id)}>
          <Icon name="refresh" size={16} />
        </button>
      {/if}
      {#if canRemove(job)}
        <button aria-label={removeLabel(job)} onclick={() => jobs.remove(job.id)}>
          <Icon name="x" size={16} />
        </button>
      {/if}
    </div>
  </li>
{/snippet}

<style>
  .content {
    max-width: var(--content-max);
    margin: 0 auto;
    padding: var(--s-5);
    display: flex;
    flex-direction: column;
    gap: var(--s-4);
  }

  h1 {
    font-size: var(--t-20);
    margin: 0;
  }

  h1:focus-visible {
    outline: none;
  }

  h2 {
    font-size: var(--t-14);
    margin: 0;
    display: flex;
    align-items: center;
    gap: var(--s-2);
  }

  .count {
    color: var(--muted);
    font-size: var(--t-13);
    font-weight: 400;
  }

  .list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
  }

  .row {
    display: grid;
    grid-template-columns: 56px 1fr auto;
    gap: var(--s-3);
    align-items: center;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    padding: var(--s-3);
  }

  .row img {
    width: 56px;
    height: 56px;
    border-radius: var(--r-sm);
    object-fit: cover;
    background: var(--line);
    flex-shrink: 0;
  }

  .text {
    display: flex;
    flex-direction: column;
    gap: var(--s-1);
    min-width: 0;
  }

  .title {
    font-size: var(--t-14);
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .title a {
    color: var(--accent);
    text-decoration: none;
  }

  .title a:hover {
    text-decoration: underline;
  }

  .muted.path {
    text-transform: none;
    word-break: break-all;
    white-space: normal;
  }

  .muted {
    color: var(--muted);
    font-size: var(--t-13);
    text-transform: capitalize;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: var(--t-12);
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--accent-bg);
    color: var(--accent);
    width: fit-content;
  }

  .chip.failed,
  .chip.needs_click {
    background: var(--danger-bg);
    color: var(--danger-fg);
  }

  .chip.done {
    background: var(--ok-bg);
    color: var(--ok-fg);
  }

  .chip.skipped {
    background: var(--line);
    color: var(--muted);
  }

  .eta {
    color: var(--muted);
    font-size: var(--t-12);
  }

  .bar {
    height: 4px;
    background: var(--line);
    border-radius: 2px;
    overflow: hidden;
  }

  .fill {
    background: var(--progress);
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s ease;
  }

  .attn {
    color: var(--danger-fg);
    font-size: var(--t-13);
    margin: 0;
  }

  .fix {
    display: inline-flex;
    align-items: center;
    min-height: 44px;
    font-size: var(--t-13);
  }

  .actions {
    display: flex;
    align-items: center;
    gap: var(--s-1);
  }

  .actions button {
    background: transparent;
    color: var(--text);
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 44px;
    min-height: 44px;
    padding: 0;
  }

  .btn {
    background: transparent;
    color: var(--text);
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: var(--s-1);
    min-height: 44px;
    padding: var(--s-2) var(--s-3);
    font-size: var(--t-13);
    margin-left: auto;
  }

  button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .offline {
    background: var(--danger-bg);
    color: var(--danger-fg);
    display: flex;
    align-items: center;
    gap: var(--s-1);
    padding: var(--s-2) var(--s-3);
    border-radius: var(--r-sm);
    font-size: var(--t-13);
  }

  .empty {
    color: var(--muted);
    text-align: center;
    padding: var(--s-5) 0;
  }

  .skel {
    height: 72px;
    background: var(--line);
    border-radius: var(--r-md);
  }
</style>
