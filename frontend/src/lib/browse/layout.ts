export type Mode = "grid" | "wall" | "masonry" | "list";

export const ZOOM_MIN = 1;
export const ZOOM_MAX = 5;

const TABLE: Record<Mode, number[]> = {
  grid: [100, 130, 160, 200, 260],
  wall: [100, 140, 180, 240, 320],
  masonry: [100, 130, 160, 200, 260],
  list: [48, 64, 80, 104, 136],
};

export function zoomSize(mode: Mode, zoom: number): number {
  const clamped = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(zoom)));
  return TABLE[mode][clamped - 1];
}

export function columnCount(containerWidth: number, colWidth: number, gap: number): number {
  return Math.max(1, Math.floor((containerWidth + gap) / (colWidth + gap)));
}

function safeAspect(value: number): number {
  return value > 0 && isFinite(value) ? value : 1;
}

export function dealMasonry(aspects: number[], columns: number): number[][] {
  const cols = Math.max(1, columns);
  const result: number[][] = Array.from({ length: cols }, () => []);
  const heights: number[] = new Array(cols).fill(0);

  for (let i = 0; i < aspects.length; i++) {
    const aspect = safeAspect(aspects[i]);
    const height = 1 / aspect;

    let minCol = 0;
    for (let c = 1; c < cols; c++) {
      if (heights[c] < heights[minCol]) {
        minCol = c;
      }
    }

    result[minCol].push(i);
    heights[minCol] += height;
  }

  return result;
}

export function wallRows(
  aspects: number[],
  containerWidth: number,
  rowHeight: number,
  gap: number,
): number[][] {
  const rows: number[][] = [];
  let currentRow: number[] = [];
  let currentWidth = 0;

  for (let i = 0; i < aspects.length; i++) {
    const aspect = safeAspect(aspects[i]);
    const itemWidth = aspect * rowHeight;

    if (currentRow.length === 0) {
      currentRow.push(i);
      currentWidth = itemWidth;
    } else if (currentWidth + gap + itemWidth <= containerWidth) {
      currentRow.push(i);
      currentWidth += gap + itemWidth;
    } else {
      rows.push(currentRow);
      currentRow = [i];
      currentWidth = itemWidth;
    }
  }

  if (currentRow.length > 0) {
    rows.push(currentRow);
  }

  return rows;
}

export function fallbackAspect(
  kind: string | undefined,
  width?: number | null,
  height?: number | null,
): number {
  if (typeof width === "number" && typeof height === "number" && width > 0 && height > 0) {
    return width / height;
  }
  switch (kind) {
    case "video":
      return 16 / 9;
    case "images":
    case "series":
    case "books":
      return 2 / 3;
    default:
      return 1;
  }
}
