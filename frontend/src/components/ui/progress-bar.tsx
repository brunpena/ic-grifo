import { cn } from "@/lib/utils";

type ProgressBarProps = {
  value: number;
  max?: number;
  /** Nome acessível, por exemplo "Regras validadas". */
  label: string;
  className?: string;
};

export function ProgressBar({ value, max = 100, label, className }: ProgressBarProps) {
  const percent = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      className={cn("h-1 w-full overflow-hidden rounded-full bg-surface-muted", className)}
    >
      <div
        className="bg-brand-gradient h-full rounded-full transition-[width] duration-150 ease-out"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
