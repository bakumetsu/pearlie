<script lang="ts">
  import "@fontsource-variable/inter";
  import "./lib/tokens.css";

  import { onMount } from "svelte";
  import { createRouter, linkClick } from "./lib/router";
  import { setRouter, setJobs } from "./lib/ctx";
  import { createJobs } from "./lib/stores/jobs.svelte";
  import Queue from "./routes/Queue.svelte";
  import Home from "./routes/Home.svelte";
  import Rules from "./routes/Rules.svelte";
  import Trash from "./routes/Trash.svelte";
  import Option from "./routes/Option.svelte";
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
  import SfwToggle from "./lib/components/SfwToggle.svelte";
  import { installReveal } from "./lib/stores/sfw-reveal";
  import { player } from "./lib/player/player.svelte";
  import { playerSettings } from "./lib/player/playerSettings.svelte";
  import { gridFor } from "./lib/stores/shared.svelte";
  import { toasts } from "./lib/stores/toasts.svelte";
  import { createPlayerNav } from "./lib/player/playerNav.svelte";

  const router = createRouter();
  setRouter(router);
  const api = createApi();
  setApi(api);
  const jobs = createJobs(api);
  setJobs(jobs);
  player.setNav(createPlayerNav({
    player,
    grid: gridFor("videos"),
    getDetail: (k, id) => api.getItem(k, id),
    navigate: (h) => router.navigate(h, { replace: true }),
    notify: (m) => toasts.push({ kind: "error", message: m }),
  }));

  let match = $state(router.current());

  onMount(() => {
    const off = router.subscribe((m) => {
      match = m;
    });
    const offReveal = installReveal();
    jobs.start();
    void playerSettings.load(api);
    return () => {
      offReveal();
      jobs.stop();
      off();
      router.destroy();
    };
  });
</script>

<Nav current={match.name} queueBadge={jobs.badge} onnavigate={(e) => linkClick(e, router)} />

<main style="margin-left: var(--rail-w)">
  {#key match.name}
    {#if match.name === "discover"}
      <Search {match} />
    {:else if match.name === "home"}
      <Home />
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
    {:else if match.name === "option"}
      <Option />
    {:else}
      <section class="placeholder">
        <h1 tabindex="-1">Page not found</h1>
        <p><a href="/" onclick={(e) => linkClick(e, router)}>Go to home</a></p>
      </section>
    {/if}
  {/key}
</main>

<SfwToggle />
<Toast />
<PlayerHost />
<MiniDock />
