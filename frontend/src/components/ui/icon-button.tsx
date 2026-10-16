"use client";

import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { BUTTON_VARIANTS, type ButtonVariant } from "./button";
import { Spinner } from "./spinner";
import { Tooltip } from "./tooltip";

export type IconButtonProps = Omit<ComponentProps<"button">, "aria-label" | "children"> & {
  /** Obrigatório: é o nome acessível e também o texto do tooltip. */
  "aria-label": string;
  icon: ReactNode;
  variant?: ButtonVariant;
  loading?: boolean;
  tooltipSide?: "top" | "bottom" | "right";
};

export function IconButton({
  icon,
  variant = "ghost",
  loading = false,
  tooltipSide = "top",
  type = "button",
  onClick,
  className,
  ...props
}: IconButtonProps) {
  return (
    <Tooltip content={props["aria-label"]} side={tooltipSide}>
      <button
        type={type}
        aria-busy={loading || undefined}
        aria-disabled={loading || undefined}
        onClick={loading ? (e) => e.preventDefault() : onClick}
        className={cn(
          "inline-flex size-8 shrink-0 items-center justify-center rounded-md",
          "transition-colors duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-50",
          BUTTON_VARIANTS[variant],
          variant === "ghost" && "text-foreground-muted enabled:hover:text-foreground",
          loading && "cursor-progress",
          className,
        )}
        {...props}
      >
        {loading ? <Spinner /> : icon}
      </button>
    </Tooltip>
  );
}
