// Single active video-card preview key (T-36)
let activeKey: string | null = $state(null);
// Keys whose preview file failed to load (Stash has none generated); not retried on every hover.
const failedKeys = new Set<string>();

export const videoPreview = {
  get active(): string | null { return activeKey; },
  start(key: string) { activeKey = key; },
  stop(key: string) { if (activeKey === key) activeKey = null; },
  isActive(key: string): boolean { return activeKey === key; },
  fail(key: string) { failedKeys.add(key); if (activeKey === key) activeKey = null; },
  hasFailed(key: string): boolean { return failedKeys.has(key); },
  reset() { activeKey = null; failedKeys.clear(); },
};
