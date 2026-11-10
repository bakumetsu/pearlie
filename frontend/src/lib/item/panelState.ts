// panelState — persist & resolve the item-panel open/closed state

export const PANEL_KEY = "pearlie.item.panel";
export const PHONE_MAX = 720;

export type PanelStorage = Pick<Storage, "getItem" | "setItem">;

export function loadPanel(storage?: PanelStorage): "open" | "closed" | null {
  try {
    const s = storage ?? localStorage;
    const v = s.getItem(PANEL_KEY);
    return v === "open" ? "open" : v === "closed" ? "closed" : null;
  } catch {
    return null;
  }
}

export function savePanel(open: boolean, storage?: PanelStorage): void {
  try {
    const s = storage ?? localStorage;
    s.setItem(PANEL_KEY, open ? "open" : "closed");
  } catch {
    // ignore
  }
}

export function initialOpen(width: number, storage?: PanelStorage): boolean {
  const stored = loadPanel(storage);
  if (stored === "open") return true;
  if (stored === "closed") return false;
  return width >= PHONE_MAX;
}
