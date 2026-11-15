import { describe, expect, it } from "vitest";
import { ORDER_LABELS, parseOrder } from "./filters";

const NHENTAI = ["newest", "popular-today", "popular-week", "popular-month", "popular"];

describe("nhentai sort orders", () => {
  it("has a label for every order the site lists", () => {
    for (const o of NHENTAI) expect(ORDER_LABELS[o]).toBeTruthy();
    expect(ORDER_LABELS["popular"]).toBe("Popular all time");
  });

  it("parseOrder keeps a listed popular order and drops it for sites without it", () => {
    expect(parseOrder("popular-week", NHENTAI)).toBe("popular-week");
    expect(parseOrder("popular-week")).toBe("");
    expect(parseOrder("newest", NHENTAI)).toBe("");
  });
});
