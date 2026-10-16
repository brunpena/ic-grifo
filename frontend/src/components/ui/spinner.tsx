import { LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

/** Indicador de carregamento decorativo; o estado deve ser anunciado pelo contêiner (aria-busy). */
export function Spinner({ size = 16, className }: { size?: number; className?: string }) {
  return (
    <LoaderCircle
      size={size}
      strokeWidth={1.75}
      aria-hidden
      className={cn("shrink-0 animate-spin motion-reduce:animate-none", className)}
    />
  );
}
