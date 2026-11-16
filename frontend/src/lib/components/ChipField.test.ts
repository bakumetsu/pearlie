// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import ChipField from "./ChipField.svelte";
import type { Chip } from "../query";

afterEach(() => cleanup());

function setup() {
  const onchange = vi.fn<(c: Chip[]) => void>();
  render(ChipField, { chips: [], onchange });
  const input = screen.getByRole("textbox") as HTMLInputElement;
  return { onchange, input };
}

async function paste(input: HTMLInputElement, text: string) {
  const ev = new Event("paste", { bubbles: true, cancelable: true });
  Object.assign(ev, { clipboardData: { getData: () => text } });
  await fireEvent(input, ev);
}

describe("ChipField paste", () => {
  it("keeps a pasted sentence as plain text; Enter makes tag chips", async () => {
    const { onchange, input } = setup();
    await paste(input, "a long pasted sentence");
    expect(onchange).not.toHaveBeenCalled();
    expect(input.value).toBe("a long pasted sentence");
    await fireEvent.keyDown(input, { key: "Enter" });
    const chips = onchange.mock.calls[0][0];
    expect(chips.map((c) => c.value)).toEqual(["a", "long", "pasted", "sentence"]);
  });

  it('keeps title:"a b c" as text; Enter makes one title chip', async () => {
    const { onchange, input } = setup();
    await paste(input, 'title:"a b c"');
    expect(onchange).not.toHaveBeenCalled();
    expect(input.value).toBe('title:"a b c"');
    await fireEvent.keyDown(input, { key: "Enter" });
    const chips = onchange.mock.calls[0][0];
    expect(chips).toHaveLength(1);
    expect(chips[0].raw).toBe('title:"a b c"');
  });

  it('keeps "a b c" as text; Enter makes one title chip', async () => {
    const { onchange, input } = setup();
    await paste(input, '"a b c"');
    expect(onchange).not.toHaveBeenCalled();
    expect(input.value).toBe('"a b c"');
    await fireEvent.keyDown(input, { key: "Enter" });
    const chips = onchange.mock.calls[0][0];
    expect(chips).toHaveLength(1);
    expect(chips[0].raw).toBe('title:"a b c"');
  });
});
