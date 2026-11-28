import { tv } from "tailwind-variants";

/** Class sets shared by the primitives. Sizes keep the 44 px hit area (design 4). */
export const buttonVariants = tv({
  base:
    "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap border font-normal transition-colors duration-[120ms] ease-ui " +
    "disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
  variants: {
    variant: {
      default: "rounded-md border-primary bg-primary font-semibold! text-primary-foreground! hover:bg-primary/90",
      outline: "rounded-md border-input bg-transparent text-foreground! hover:bg-border",
      ghost: "rounded-md border-transparent bg-transparent text-foreground! hover:bg-border",
      destructive: "rounded-md border-transparent bg-destructive/15 text-destructive! hover:bg-destructive/25",
      pill: "rounded-pill border-border bg-card text-muted-foreground! hover:text-foreground! aria-pressed:border-primary aria-pressed:bg-accent aria-pressed:text-primary!",
      chip: "rounded-md border-border bg-card text-foreground! aria-pressed:border-primary aria-pressed:bg-accent aria-pressed:text-primary!",
    },
    size: {
      default: "h-11 min-w-11 px-4",
      sm: "h-9 px-3 text-[13px] pointer-coarse:h-11 pointer-coarse:min-w-11",
      icon: "size-11 p-0",
    },
  },
  defaultVariants: { variant: "default", size: "default" },
});

export const fieldClass =
  "h-11 w-full min-w-0 border border-input bg-card text-foreground placeholder:text-muted-foreground " +
  "focus-visible:border-primary focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50";

export const menuPanelClass =
  "absolute z-30 min-w-[190px] rounded-lg border border-input bg-popover p-1.5 text-popover-foreground shadow-[var(--shadow-float)]";

export const menuItemClass =
  "flex h-11 w-full items-center gap-2.5 rounded-md px-2.5 text-left hover:bg-border " +
  "aria-checked:bg-accent aria-checked:text-primary! focus-visible:outline-2 focus-visible:outline-ring";
