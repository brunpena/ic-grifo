import { ChevronDown } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";
import { FIELD_CLASSES } from "./input";

/** Select nativo com o mesmo visual do Input (teclado e leitores de tela de graça). */
export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <div className={cn("relative", className)}>
      <select className={cn(FIELD_CLASSES, "h-9 cursor-pointer appearance-none pr-8")} {...props}>
        {children}
      </select>
      <ChevronDown
        size={16}
        strokeWidth={1.75}
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-foreground-subtle"
      />
    </div>
  );
}
