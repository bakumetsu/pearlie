import { ApiError, errorText } from "../api/client";
import type { Api, ConnectionsOut, ConnectionOut, ConnectionIn, ConnectionTest } from "../api/client";

// Assumes ConnectionsOut = { can_store: boolean; connections: ConnectionOut[] }
// with each ConnectionOut carrying a `name` field (connections are addressed by name).
export function createConnections() {
  let data: ConnectionsOut | null = $state(null);
  let loading = $state(false);
  let testing: Record<string, boolean> = $state({});
  let results: Record<string, ConnectionTest | undefined> = $state({});
  let restartNeeded: Record<string, boolean> = $state({});
  let inflight: Promise<void> | null = null;

  function byName(name: string): ConnectionOut | undefined {
    if (!data) return undefined;
    return data.connections.find((c) => c.name === name);
  }

  function load(api: Api): Promise<void> {
    if (inflight) return inflight;
    inflight = (async () => {
      loading = true;
      try {
        data = await api.getConnections();
      } catch {
        data = null;
      } finally {
        loading = false;
        inflight = null;
      }
    })();
    return inflight;
  }

  async function save(api: Api, name: string, body: Partial<ConnectionIn>): Promise<void> {
    const updated = await api.putConnection(name, body);
    if (data) {
      const idx = data.connections.findIndex((c) => c.name === name);
      if (idx >= 0) {
        const connections = [...data.connections];
        connections[idx] = updated;
        data = { ...data, connections };
      } else {
        data = { ...data, connections: [...data.connections, updated] };
      }
    }
    restartNeeded = { ...restartNeeded, [name]: updated.restart_needed };
    results = { ...results, [name]: undefined };
  }

  async function test(api: Api, name: string): Promise<void> {
    testing = { ...testing, [name]: true };
    try {
      const res = await api.testConnection(name);
      results = { ...results, [name]: res };
    } catch (e) {
      if (e instanceof ApiError) {
        results = { ...results, [name]: { ok: false, message: errorText(e) } };
      } else {
        throw e;
      }
    } finally {
      testing = { ...testing, [name]: false };
    }
  }

  return {
    get data(): ConnectionsOut | null { return data; },
    get loading(): boolean { return loading; },
    get canStore(): boolean { return data?.can_store ?? false; },
    get results(): Record<string, ConnectionTest | undefined> { return results; },
    get restartNeeded(): Record<string, boolean> { return restartNeeded; },
    get testing(): Record<string, boolean> { return testing; },
    byName,
    load,
    save,
    test,
  };
}

export const connections = createConnections();
export type ConnectionsStore = ReturnType<typeof createConnections>;
