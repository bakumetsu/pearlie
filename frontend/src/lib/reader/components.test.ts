import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import { describe, it, expect, vi, afterEach } from "vitest";

import EndCard from "./EndCard.svelte";
import BookList from "./BookList.svelte";
import ThumbStrip from "./ThumbStrip.svelte";

afterEach(cleanup);

describe("EndCard", () => {
  it("shows next book info, actions, and image", () => {
    const onnext = vi.fn();
    const onback = vi.fn();
    render(EndCard, {
      title: "My Book",
      next: { title: "Next Book", thumb_url: "/thumbs/next.jpg" },
      hasSeries: true,
      onnext,
      onback,
    });

    expect(screen.queryByText("End of My Book")).not.toBeNull();
    expect(screen.queryByText("Next: Next Book")).not.toBeNull();
    expect(screen.queryByAltText("Next Book")).not.toBeNull();

    fireEvent.click(screen.getByText("Next book"));
    expect(onnext).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText("Back to series"));
    expect(onback).toHaveBeenCalledTimes(1);
  });

  it("last book heading with only Back when next=null, hasSeries=true", () => {
    render(EndCard, {
      title: "My Book",
      next: null,
      hasSeries: true,
      onnext: vi.fn(),
      onback: vi.fn(),
    });

    expect(screen.queryByText("End of My Book · last book")).not.toBeNull();
    expect(screen.queryByText("Back")).not.toBeNull();
    expect(screen.queryByText("Next book")).toBeNull();
  });

  it("plain heading without last book when hasSeries=false", () => {
    render(EndCard, {
      title: "My Book",
      next: null,
      hasSeries: false,
      onnext: vi.fn(),
      onback: vi.fn(),
    });

    const heading = screen.getByText("End of My Book");
    expect(heading.textContent).not.toContain("last book");
  });
});

describe("BookList", () => {
  const books = [
    { id: "1", title: "Book A", thumb_url: null, read_page: 0, page_count: 100 },
    { id: "2", title: "Book B", thumb_url: null, read_page: 50, page_count: 200 },
    { id: "3", title: "Book C", thumb_url: null, read_page: 0, page_count: 150 },
  ] as never;

  it("renders one button per book; current has aria-current", () => {
    render(BookList, {
      books,
      currentId: "2",
      notice: null,
      onpick: vi.fn(),
      onclose: vi.fn(),
    });

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(3);
    expect(buttons[1].getAttribute("aria-current")).toBe("true");
  });

  it("calls onpick with the clicked book", () => {
    const onpick = vi.fn();
    render(BookList, {
      books,
      currentId: "1",
      notice: null,
      onpick,
      onclose: vi.fn(),
    });

    const buttons = screen.getAllByRole("button");
    fireEvent.click(buttons[1]);
    expect(onpick).toHaveBeenCalledWith(books[1]);
  });

  it("notice present when set", () => {
    render(BookList, {
      books,
      currentId: "1",
      notice: "Warning",
      onpick: vi.fn(),
      onclose: vi.fn(),
    });

    const dialog = screen.getByRole("dialog", { name: "Books" });
    expect(dialog.querySelector(".notice")).not.toBeNull();
  });

  it("notice absent when null", () => {
    render(BookList, {
      books,
      currentId: "1",
      notice: null,
      onpick: vi.fn(),
      onclose: vi.fn(),
    });

    const dialog = screen.getByRole("dialog", { name: "Books" });
    expect(dialog.querySelector(".notice")).toBeNull();
  });

  it("shows No books for empty list", () => {
    render(BookList, {
      books: [],
      currentId: "",
      notice: null,
      onpick: vi.fn(),
      onclose: vi.fn(),
    });

    expect(screen.queryByText("No books")).not.toBeNull();
  });

  it("calls onclose on Escape keydown on dialog", () => {
    const onclose = vi.fn();
    render(BookList, {
      books,
      currentId: "1",
      notice: null,
      onpick: vi.fn(),
      onclose,
    });

    const dialog = screen.getByRole("dialog", { name: "Books" });
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onclose).toHaveBeenCalledTimes(1);
  });
});

describe("ThumbStrip", () => {
  it("renders 100 buttons labelled Page N", () => {
    render(ThumbStrip, {
      count: 100,
      shown: [50],
      template: "/p/{n}",
      onjump: vi.fn(),
    });

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(100);
    expect(buttons[0].getAttribute("aria-label")).toBe("Page 1");
    expect(buttons[49].getAttribute("aria-label")).toBe("Page 50");
    expect(buttons[99].getAttribute("aria-label")).toBe("Page 100");
  });

  it("renders fewer than count img elements (windowed)", () => {
    const { container } = render(ThumbStrip, {
      count: 100,
      shown: [50],
      template: "/p/{n}",
      onjump: vi.fn(),
    });

    const imgs = container.querySelectorAll("img");
    expect(imgs.length).toBeLessThan(100);
    expect(imgs.length).toBeGreaterThan(0);
  });

  it("calls onjump with page number on click", () => {
    const onjump = vi.fn();
    render(ThumbStrip, {
      count: 100,
      shown: [50],
      template: "/p/{n}",
      onjump,
    });

    const buttons = screen.getAllByRole("button");
    fireEvent.click(buttons[49]);
    expect(onjump).toHaveBeenCalledWith(50);
  });
});
