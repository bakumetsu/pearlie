export interface SaveSlot {
  state: "idle" | "queued" | "in_library" | "blocked";
  href?: string;
  disabled?: boolean;
  onsave: () => void;
}
