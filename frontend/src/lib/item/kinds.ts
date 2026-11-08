export type Kind = "images" | "videos" | "series" | "books";
export type SingularKind = "image" | "video" | "series" | "book";

const singularToPlural: Record<SingularKind, Kind> = {
  image: "images",
  video: "videos",
  series: "series",
  book: "books",
};

export function toPlural(k: string): Kind | null {
  switch (k) {
    case "images":
    case "videos":
    case "series":
    case "books":
      return k;
    case "image":
    case "video":
    case "book":
      return singularToPlural[k as SingularKind];
    default:
      return null;
  }
}

export function toSingular(k: Kind): SingularKind {
  switch (k) {
    case "images":
      return "image";
    case "videos":
      return "video";
    case "series":
      return "series";
    case "books":
      return "book";
  }
}

export function itemHref(item: { kind: SingularKind; id: string }): string {
  return `/item/${singularToPlural[item.kind]}/${encodeURIComponent(item.id)}`;
}

export function itemKey(item: { kind: SingularKind; id: string }): string {
  return `${item.kind}:${item.id}`;
}
