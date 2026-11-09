<script lang="ts">
  import "@fontsource-variable/inter";
  import "./lib/tokens.css";

  import { onMount } from "svelte";
  import { createRouter, linkClick } from "./lib/router";
  import { setRouter, setJobs } from "./lib/ctx";
  import { createJobs } from "./lib/stores/jobs.svelte";
  import Queue from "./routes/Queue.svelte";
  import Rules from "./routes/Rules.svelte";
  import Trash from "./routes/Trash.svelte";
  import Reader from "./routes/Reader.svelte";
  import { setApi, createApi } from "./lib/api/client";
  import Nav from "./lib/components/Nav.svelte";
  import Toast from "./lib/components/Toast.svelte";
  import Search from "./routes/Search.svelte";
  import Library from "./routes/Library.svelte";
  import SeeAll from "./routes/SeeAll.svelte";
  import Item from "./routes/Item.svelte";
  import PlayerHost from "./lib/player/PlayerHost.svelte";
  import MiniDock from "./lib/player/MiniDock.svelte";

  const router = createRouter();
  setRouter(router);
  const api = createApi();
  setApi(api);
  const jobs = createJobs(api);
  setJobs(jobs);

  let match = $state(router.current());

  onMount(() => {
    const off = router.subscribe((m) => {
      match = m;
    });
    jobs.start();
    return () => {
      jobs.stop();
      off();
      router.destroy();
    };
  });
</script>

<Nav current={match.name} queueBadge={jobs.badge} onnavigate={(e) => linkClick(e, router)} />

<main style="margin-left: var(--rail-w)">
  {#key match.name}
    {#if match.name === "search"}
      <Search {match} />
    {:else if match.name === "library"}
      <Library {match} />
    {:else if match.name === "seeall" || match.name.startsWith("library_")}
      <SeeAll {match} />
    {:else if match.name === "item"}
      <Item {match} />
    {:else if match.name === "read"}
      <Reader {match} />
    {:else if match.name === "queue"}
      <Queue />
    {:else if match.name === "rules"}
      <Rules />
    {:else if match.name === "trash"}
      <Trash />
    {:else}
      <section class="placeholder">
        <h1 tabindex="-1">Page not found</h1>
        <p><a href="/" onclick={(e) => linkClick(e, router)}>Go to home</a></p>
      </section>
    {/if}
  {/key}
</main>

<Toast />
<PlayerHost />
<MiniDock />
