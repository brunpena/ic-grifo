"use client";

import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Spinner } from "./spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

const BASE =
  "relative inline-flex shrink-0 items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap select-none " +
  "transition-colors duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-50";

export const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-primary text-primary-foreground enabled:hover:bg-primary-hover",
  secondary:
    "border border-border-strong bg-surface text-foreground enabled:hover:bg-surface-hover",
  ghost: "text-foreground enabled:hover:bg-surface-hover",
  danger: "bg-danger text-danger-foreground enabled:hover:bg-danger/90",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-9 px-4 text-sm",
};

export type ButtonProps = ComponentProps<"button"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Ícone à esquerda do texto; durante o carregamento vira o spinner. */
  icon?: ReactNode;
  loading?: boolean;
};

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  loading = false,
  type = "button",
  onClick,
  className,
  children,
  ...props
}: ButtonProps) {
  // Sem ícone, o spinner fica por cima do texto invisível, mantendo a largura.
  const overlaySpinner = loading && !icon;

  return (
    <button
      type={type}
      aria-busy={loading || undefined}
      aria-disabled={loading || undefined}
      onClick={loading ? (e) => e.preventDefault() : onClick}
      className={cn(BASE, SIZES[size], BUTTON_VARIANTS[variant], loading && "cursor-progress", className)}
      {...props}
    >
      {icon && (loading ? <Spinner /> : icon)}
      <span className={cn("inline-flex items-center gap-2", overlaySpinner && "invisible")}>
        {children}
      </span>
      {overlaySpinner && <Spinner className="absolute inset-0 m-auto" />}
    </button>
  );
}
