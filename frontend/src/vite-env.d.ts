/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Build-time flag: "1" or "true" swaps the old rail Nav for the new shell (T-442). Default off. */
  readonly VITE_UI_SHELL?: string;
}
