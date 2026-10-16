import Image from "next/image";
import { cn } from "@/lib/utils";

// Marca com fundo transparente. A escala corta a margem interna do arquivo para a
// águia ocupar melhor o espaço. No tema claro, uma sombra fina contorna as partes
// brancas da águia, que sumiriam sobre o fundo branco.
const LOGO_SRC = "/brand/logo.png";

type BrandLogoProps = {
  /** Lado em px (o logo é quadrado). */
  size?: number;
  className?: string;
  /** Use `false` quando o nome do projeto já aparece ao lado. */
  labelled?: boolean;
  priority?: boolean;
};

export function BrandLogo({ size = 28, className, labelled = true, priority }: BrandLogoProps) {
  return (
    <span className={cn("inline-flex shrink-0 overflow-hidden", className)} style={{ width: size, height: size }}>
      <Image
        src={LOGO_SRC}
        width={size}
        height={size}
        alt={labelled ? "IC Grifo" : ""}
        priority={priority}
        className="size-full scale-[1.3] object-contain drop-shadow-[0_0_1px_rgb(3_10_31/0.45)] dark:drop-shadow-none"
      />
    </span>
  );
}
