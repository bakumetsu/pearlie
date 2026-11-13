// Set by the api client when the backend refuses the Host header (code host_not_allowed).
class HostBlock {
  message = $state<string | null>(null);

  set(message: string): void {
    this.message = message;
  }

  clear(): void {
    this.message = null;
  }
}

export const hostBlock = new HostBlock();
