// Single active video-card preview key (T-36)
let activeKey: string | null = $state(null);

export const videoPreview = {
  get active(): string | null { return activeKey; },
  start(key: string) { activeKey = key; },
  stop(key: string) { if (activeKey === key) activeKey = null; },
  isActive(key: string): boolean { return activeKey === key; },
  reset() { activeKey = null; },
};
