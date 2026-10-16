"use client";

import { CircleCheck, CircleX, Info, type LucideIcon, X } from "lucide-react";
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
} from "react";
import { cn } from "@/lib/utils";
import { IconButton } from "./icon-button";

export type ToastVariant = "info" | "success" | "error";
export type ToastInput = { title: string; description?: string; variant?: ToastVariant };
type ToastItem = ToastInput & { id: number };

// Erros ficam até a pessoa fechar; os demais somem sozinhos.
const AUTO_DISMISS_MS = 5000;

const VARIANTS: Record<ToastVariant, { Icon: LucideIcon; bar: string; icon: string }> = {
  info: { Icon: Info, bar: "border-l-accent", icon: "text-accent" },
  success: { Icon: CircleCheck, bar: "border-l-success", icon: "text-success" },
  error: { Icon: CircleX, bar: "border-l-danger", icon: "text-danger" },
};

const ToastContext = createContext<((toast: ToastInput) => void) | null>(null);

export function useToast() {
  const toast = useContext(ToastContext);
  if (!toast) throw new Error("useToast precisa estar dentro de <ToastProvider>.");
  return toast;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const toast = (input: ToastInput) => {
    const id = nextId.current++;
    setToasts((current) => [...current, { ...input, id }]);
  };
  const dismiss = (id: number) => setToasts((current) => current.filter((t) => t.id !== id));

  return (
    <ToastContext value={toast}>
      {children}
      {/* A região existe desde o início para que os leitores de tela anunciem o que entrar nela. */}
      <div
        role="region"
        aria-label="Notificações"
        aria-live="polite"
        className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-90 max-w-[calc(100vw-32px)] flex-col gap-2"
      >
        {toasts.map((t) => (
          <Toast key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext>
  );
}

function Toast({ toast, onDismiss }: { toast: ToastItem; onDismiss: () => void }) {
  const variant = toast.variant ?? "info";
  const { Icon, bar, icon } = VARIANTS[variant];
  const [paused, setPaused] = useState(false);
  // Evita reiniciar o tempo a cada nova renderização da lista.
  const onTimeout = useEffectEvent(onDismiss);

  useEffect(() => {
    if (variant === "error" || paused) return;
    const timer = window.setTimeout(onTimeout, AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [variant, paused]);

  return (
    <div
      role={variant === "error" ? "alert" : "status"}
      onPointerEnter={() => setPaused(true)}
      onPointerLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      className={cn(
        "pointer-events-auto flex items-start gap-3 rounded-lg border border-l-[3px] border-border bg-surface",
        "py-3 pr-2 pl-3 text-foreground shadow-md animate-enter",
        bar,
      )}
    >
      <Icon size={16} strokeWidth={1.75} aria-hidden className={cn("mt-0.5 shrink-0", icon)} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <p className="text-sm font-medium">{toast.title}</p>
        {toast.description && <p className="text-[13px] text-foreground-muted">{toast.description}</p>}
      </div>
      <IconButton
        aria-label="Fechar notificação"
        icon={<X size={16} strokeWidth={1.75} aria-hidden />}
        onClick={onDismiss}
        className="-my-1"
      />
    </div>
  );
}
