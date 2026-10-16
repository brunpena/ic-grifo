import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** Visual comum a Input, Textarea e Select. Para indicar erro, use `aria-invalid`. */
export const FIELD_CLASSES = cn(
  "w-full rounded-md border border-border bg-surface px-3 text-sm text-foreground outline-none",
  "transition-[border-color,box-shadow] duration-150 ease-out placeholder:text-foreground-subtle",
  "focus:border-ring focus:ring-[3px] focus:ring-accent-soft",
  "aria-invalid:border-danger aria-invalid:focus:ring-danger-soft",
  "disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-foreground-subtle",
);

export function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return <input type={type} className={cn(FIELD_CLASSES, "h-9", className)} {...props} />;
}

export function Textarea({ className, rows = 3, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea rows={rows} className={cn(FIELD_CLASSES, "min-h-9 resize-y py-2", className)} {...props} />
  );
}
