// Focus trap for dialogs: remembers the opener, traps Tab, restores focus on destroy.
export function trapFocus(node: HTMLElement) {
  const opener = document.activeElement as HTMLElement | null;
  const SEL = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  const items = () => Array.from(node.querySelectorAll<HTMLElement>(SEL)).filter((el) => !el.hasAttribute("disabled"));
  (items()[0] ?? node).focus();
  function onKey(e: KeyboardEvent) {
    if (e.key !== "Tab") return;
    const list = items();
    if (!list.length) { e.preventDefault(); return; }
    const first = list[0];
    const last = list[list.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === node)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
  }
  node.addEventListener("keydown", onKey);
  return {
    destroy() {
      node.removeEventListener("keydown", onKey);
      if (opener && document.contains(opener)) opener.focus();
    },
  };
}
