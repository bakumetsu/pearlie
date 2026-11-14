<script module lang="ts">
  export type IconName =
    | "search" | "library" | "queue" | "rules" | "heart"
    | "heart-filled" | "x" | "plus" | "chevron-left" | "chevron-right"
    | "chevron-down" | "arrow-left" | "arrow-right" | "download" | "check"
    | "trash" | "star" | "play" | "pause" | "external-link"
    | "refresh" | "alert" | "loader" | "bookmark" | "image" | "film" | "book"
    | "star-filled" | "volume" | "volume-x" | "pip" | "maximize" | "minimize" | "undo"
    | "clock" | "minus" | "upload" | "columns" | "settings" | "arrow-left-right" | "rotate-ccw" | "power"
    | "help" | "chevron-up" | "list" | "fit-width" | "fit-height" | "fit-both" | "fit-actual" | "mode-single" | "mode-spread" | "mode-scroll"
    | "home" | "wrench" | "eye" | "eye-off"
    | "grid" | "wall" | "masonry" | "sliders" | "chevrons-left" | "chevrons-right"
    | "skip-back" | "skip-forward" | "rewind" | "fast-forward" | "replay-10" | "forward-10"
    | "zoom-in" | "zoom-out" | "info" | "order" | "shield"
    | "wand-sparkles" | "mouse-pointer"
    | "octagon-x" | "triangle-alert" | "bug" | "copy" | "history";

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
    "clock": [
      "M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z",
      "M12 7v5l3 2",
    ],
    "history": [
      "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8",
      "M3 3v5h5",
      "M12 7v5l4 2",
    ],
    "wand-sparkles": [
      "m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72",
      "m14 7 3 3",
      "M5 6v4",
      "M19 14v4",
      "M10 2v2",
      "M7 8H3",
      "M21 16h-4",
      "M11 3H9",
    ],
    "mouse-pointer": [
      "M12.586 12.586 19 19",
      "M3.688 3.037a.497.497 0 0 0-.651.651l6.5 15.999a.501.501 0 0 0 .947-.062l1.569-6.083a2 2 0 0 1 1.448-1.479l6.124-1.579a.5.5 0 0 0 .063-.947z",
    ],
    "minus": [
      "M5 12h14",
    ],
    "upload": [
      "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4",
      "M17 8l-5-5-5 5",
      "M12 3v12",
    ],
    "columns": [
      "M4 4h16v16H4z",
      "M12 4v16",
    ],
    "settings": [
      "M4 6h10",
      "M18 6h2",
      "M4 12h2",
      "M10 12h10",
      "M4 18h12",
      "M20 18h0",
      "M16 4v4",
      "M8 10v4",
      "M18 16v4",
    ],
    "arrow-left-right": [
      "M8 3L4 7l4 4",
      "M4 7h16",
      "M16 21l4-4-4-4",
      "M20 17H4",
    ],
    "power": [
      "M12 2v10",
      "M18.4 6.6a9 9 0 1 1-12.77.04",
    ],
    "rotate-ccw": [
      "M1 4v6h6",
      "M3.51 15a9 9 0 1 0 2.13-9.36L1 10",
    ],
    "help": [
      "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z",
      "M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3",
      "M12 17h.01",
    ],
    "chevron-up": [
      "M18 15l-6-6-6 6",
    ],
    "list": [
      "M8 6h13",
      "M8 12h13",
      "M8 18h13",
      "M3 6h.01",
      "M3 12h.01",
      "M3 18h.01",
    ],
    "fit-width": [
      "M4 3v18",
      "M20 3v18",
      "M8 12h8",
      "M11 9L8 12l3 3",
      "M13 9l3 3-3 3",
    ],
    "fit-height": [
      "M3 4h18",
      "M3 20h18",
      "M12 8v8",
      "M9 11l3-3 3 3",
      "M9 13l3 3 3-3",
    ],
    "fit-both": [
      "M3 8V5a2 2 0 0 1 2-2h3",
      "M16 3h3a2 2 0 0 1 2 2v3",
      "M21 16v3a2 2 0 0 1-2 2h-3",
      "M8 21H5a2 2 0 0 1-2-2v-3",
      "M9 9h6v6H9z",
    ],
    "fit-actual": [
      "M6 5v14",
      "M12 8h.01",
      "M12 16h.01",
      "M18 5v14",
    ],
    "mode-single": [
      "M8 4h8v16H8z",
    ],
    "mode-spread": [
      "M3 4h8v16H3z",
      "M13 4h8v16h-8z",
    ],
    "mode-scroll": [
      "M5 4h14v16H5z",
      "M12 8v5",
      "M9 11l3 3 3-3",
    ],
    "home": [
      "M3 11l9-8 9 8",
      "M5 10v10h14V10",
      "M10 20v-6h4v6",
    ],
    "wrench": [
      "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z",
    ],
    "eye": ["M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z", "M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z"],
    "eye-off": ["M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94", "M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19", "M14.12 14.12a3 3 0 1 1-4.24-4.24", "M1 1l22 22"],
    "grid": [
      "M3 3h7v7H3z",
      "M14 3h7v7h-7z",
      "M3 14h7v7H3z",
      "M14 14h7v7h-7z",
    ],
    "wall": [
      "M3 4h10v7H3z",
      "M15 4h6v7h-6z",
      "M3 13h6v7H3z",
      "M11 13h10v7H11z",
    ],
    "masonry": [
      "M3 3h5v9H3z",
      "M3 14h5v7H3z",
      "M10 3h5v5h-5z",
      "M10 10h5v11h-5z",
      "M17 3h4v12h-4z",
      "M17 17h4v4h-4z",
    ],
    "sliders": [
      "M4 6h10",
      "M18 6h2",
      "M4 12h4",
      "M12 12h8",
      "M4 18h12",
      "M20 18h0",
      "M16 4v4",
      "M10 10v4",
      "M18 16v4",
    ],
    "chevrons-left": [
      "M11 17l-5-5 5-5",
      "M18 17l-5-5 5-5",
    ],
    "chevrons-right": [
      "M13 17l5-5-5-5",
      "M6 17l5-5-5-5",
    ],
    "skip-back": [
      "M19 20L9 12l10-8v16z",
      "M5 19V5",
    ],
    "skip-forward": [
      "M5 4l10 8-10 8V4z",
      "M19 5v14",
    ],
    "rewind": [
      "M11 19L2 12l9-7v14z",
      "M22 19l-9-7 9-7v14z",
    ],
    "fast-forward": [
      "M13 19l9-7-9-7v14z",
      "M2 19l9-7-9-7v14z",
    ],
    "replay-10": [
      "M3 12a9 9 0 1 0 3-6.7",
      "M3 4v5h5",
      "M10 9.5v5",
      "M13 9.5h2.5v5H13z",
    ],
    "forward-10": [
      "M21 12a9 9 0 1 1-3-6.7",
      "M21 4v5h-5",
      "M10 9.5v5",
      "M13 9.5h2.5v5H13z",
    ],
    "zoom-in": [
      "M11 3a8 8 0 1 1 0 16 8 8 0 0 1 0-16z",
      "M21 21l-4.35-4.35",
      "M11 8v6",
      "M8 11h6",
    ],
    "zoom-out": [
      "M11 3a8 8 0 1 1 0 16 8 8 0 0 1 0-16z",
      "M21 21l-4.35-4.35",
      "M8 11h6",
    ],
    "info": [
      "M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20z",
      "M12 16v-4",
      "M12 8h.01",
    ],
    "order": [
      "m3 16 4 4 4-4",
      "M7 20V4",
      "M11 4h4",
      "M11 8h7",
      "M11 12h10",
    ],
    "shield": [
      "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z",
    ],
    "octagon-x": [
      "m15 9-6 6",
      "M2.586 16.726A2 2 0 0 1 2 15.312V8.688a2 2 0 0 1 .586-1.414l4.688-4.688A2 2 0 0 1 8.688 2h6.624a2 2 0 0 1 1.414.586l4.688 4.688A2 2 0 0 1 22 8.688v6.624a2 2 0 0 1-.586 1.414l-4.688 4.688a2 2 0 0 1-1.414.586H8.688a2 2 0 0 1-1.414-.586z",
      "m9 9 6 6",
    ],
    "triangle-alert": [
      "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3",
      "M12 9v4",
      "M12 17h.01",
    ],
    "bug": [
      "M12 20v-9",
      "M14 7a4 4 0 0 1 4 4v3a6 6 0 0 1-12 0v-3a4 4 0 0 1 4-4z",
      "M14.12 3.88 16 2",
      "M21 21a4 4 0 0 0-3.81-4",
      "M21 5a4 4 0 0 1-3.55 3.97",
      "M22 13h-4",
      "M3 21a4 4 0 0 1 3.81-4",
      "M3 5a4 4 0 0 0 3.55 3.97",
      "M6 13H2",
      "m8 2 1.88 1.88",
      "M9 7.13V6a3 3 0 1 1 6 0v1.13",
    ],
    "copy": [
      "M20 8h-8a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2z",
      "M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2",
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
