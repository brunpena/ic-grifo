"use client";

import { Eye, EyeOff } from "lucide-react";
import { type ComponentProps, useState } from "react";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { IconButton } from "./icon-button";
import { Input } from "./input";

/** Campo de senha com botão para mostrar ou ocultar o texto. */
export function PasswordInput({ className, ...props }: Omit<ComponentProps<"input">, "type">) {
  const [visible, setVisible] = useState(false);
  const t = useT();
  return (
    <div className={cn("relative", className)}>
      <Input type={visible ? "text" : "password"} className="pr-10" {...props} />
      <IconButton
        aria-label={visible ? t("Ocultar senha") : t("Mostrar senha")}
        aria-pressed={visible}
        icon={visible ? <EyeOff size={16} strokeWidth={1.75} aria-hidden /> : <Eye size={16} strokeWidth={1.75} aria-hidden />}
        onClick={() => setVisible((v) => !v)}
        className="absolute top-0.5 right-0.5"
      />
    </div>
  );
}
