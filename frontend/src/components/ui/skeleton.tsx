import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** Bloco de carregamento. O contêiner deve anunciar o carregamento (aria-busy). */
export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded-md bg-surface-muted motion-reduce:animate-none", className)}
      {...props}
    />
  );
}
