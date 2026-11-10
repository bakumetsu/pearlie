<!-- Favourite heart badge shared by Tile and VideoCard (T-61) -->
<script lang="ts">
  import Icon from "./Icon.svelte";
</script>

<span class="fav"><Icon name="heart-filled" size={14} /></span>

<style>
  .fav {
    position: absolute;
    top: var(--s-1);
    right: var(--s-1);
    z-index: 1;
    color: var(--danger-fg);
  }
</style>
