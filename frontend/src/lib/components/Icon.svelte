<script module lang="ts">
  export type IconName =
    | "search" | "library" | "queue" | "rules" | "heart"
    | "heart-filled" | "x" | "plus" | "chevron-left" | "chevron-right"
    | "chevron-down" | "arrow-left" | "arrow-right" | "download" | "check"
    | "trash" | "star" | "play" | "pause" | "external-link"
    | "refresh" | "alert" | "loader" | "bookmark" | "image" | "film" | "book"
    | "star-filled" | "volume" | "volume-x" | "pip" | "maximize" | "minimize" | "undo";

  const paths: Record<IconName, string[]> = {
    "search": [
      "M21 21l-4.35-4.35",
      "M11 3a8 8 0 1 1 0 16 8 8 0 0 1 0-16z",
    ],
    "library": [
      "M4 4v16",
      "M8 8v12",
      "M12 6v14",
      "M16 6l4 14",
    ],
    "queue": [
      "M8 6h13",
      "M8 12h13",
      "M8 18h13",
      "M3 6h.01",
      "M3 12h.01",
      "M3 18h.01",
    ],
    "rules": [
      "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2",
      "M9 2h6a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z",
      "M9 12h6",
      "M9 16h6",
    ],
    "heart": [
      "M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z",
    ],
    "heart-filled": [
      "M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z",
    ],
    "x": [
      "M18 6L6 18",
      "M6 6l12 12",
    ],
    "plus": [
      "M12 5v14",
      "M5 12h14",
    ],
    "chevron-left": [
      "M15 18l-6-6 6-6",
    ],
    "chevron-right": [
      "M9 18l6-6-6-6",
    ],
    "chevron-down": [
      "M6 9l6 6 6-6",
    ],
    "arrow-left": [
      "M19 12H5",
      "M12 19l-7-7 7-7",
    ],
    "arrow-right": [
      "M5 12h14",
      "M12 5l7 7-7 7",
    ],
    "download": [
      "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4",
      "M7 10l5 5 5-5",
      "M12 15V3",
    ],
    "check": [
      "M20 6L9 17l-5-5",
    ],
    "trash": [
      "M3 6h18",
      "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6",
      "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2",
      "M10 11v6",
      "M14 11v6",
    ],
    "star": [
      "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z",
    ],
    "play": [
      "M5 3v18l14-9z",
    ],
    "pause": [
      "M6 4h4v16H6z",
      "M14 4h4v16h-4z",
    ],
    "external-link": [
      "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6",
      "M15 3h6v6",
      "M10 14L21 3",
    ],
    "refresh": [
      "M23 4v6h-6",
      "M1 20v-6h6",
      "M3.51 9a9 9 0 0 1 14.85-3.36L23 10",
      "M1 14l4.64 4.36A9 9 0 0 0 20.49 15",
    ],
    "alert": [
      "M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z",
      "M12 9v4",
      "M12 17h.01",
    ],
    "loader": [
      "M21 12a9 9 0 1 1-6.219-8.56",
    ],
    "bookmark": [
      "M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z",
    ],
    "image": [
      "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z",
      "M3 16l5-5 4 4 3-3 6 6",
      "M9 8h.01",
    ],
    "film": [
      "M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z",
      "M7 3v18",
      "M17 3v18",
      "M4 7h3",
      "M4 12h3",
      "M4 17h3",
      "M17 7h3",
      "M17 12h3",
      "M17 17h3",
    ],
    "book": [
      "M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z",
      "M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z",
    ],
    "star-filled": [
      "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z",
    ],
    "volume": [
      "M11 5L6 9H2v6h4l5 4z",
      "M15.5 8.5a5 5 0 0 1 0 7",
      "M19 5a10 10 0 0 1 0 14",
    ],
    "volume-x": [
      "M11 5L6 9H2v6h4l5 4z",
      "M23 9l-6 6",
      "M17 9l6 6",
    ],
    "pip": [
      "M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z",
      "M12 12h8v5h-8z",
    ],
    "maximize": [
      "M8 3H5a2 2 0 0 0-2 2v3",
      "M21 8V5a2 2 0 0 0-2-2h-3",
      "M3 16v3a2 2 0 0 0 2 2h3",
      "M16 21h3a2 2 0 0 0 2-2v-3",
    ],
    "minimize": [
      "M8 3v3a2 2 0 0 1-2 2H3",
      "M21 8h-3a2 2 0 0 1-2-2V3",
      "M3 16h3a2 2 0 0 1 2 2v3",
      "M16 21v-3a2 2 0 0 1 2-2h3",
    ],
    "undo": [
      "M3 7v6h6",
      "M21 17a9 9 0 0 0-15-6.7L3 13",
    ],
  };
</script>

<script lang="ts">
  let { name, size = 20 }: { name: IconName; size?: number } = $props();
</script>

<svg
  viewBox="0 0 24 24"
  width={size}
  height={size}
  fill={name === "heart-filled" || name === "star-filled" ? "currentColor" : "none"}
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  {#each paths[name] as d (d)}
    <path {d} />
  {/each}
</svg>
