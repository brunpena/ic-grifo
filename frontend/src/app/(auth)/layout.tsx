import { BrandLogo } from "@/components/brand-logo";
import { ThemeToggle } from "@/components/theme-toggle";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="relative flex min-h-dvh flex-1 flex-col items-center justify-center overflow-hidden px-4 py-12">
      {/* Brilho suave do azul da marca atrás do formulário. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_50%_45%_at_50%_40%,rgb(10_132_255/0.08),transparent_70%)] dark:bg-[radial-gradient(ellipse_50%_45%_at_50%_40%,rgb(10_132_255/0.15),transparent_70%)]"
      />
      <ThemeToggle className="absolute top-3 right-4 border border-border" />
      <div className="relative flex w-full max-w-sm flex-col items-center gap-6">
        <div className="flex flex-col items-center gap-3">
          <BrandLogo size={64} priority />
          <span className="text-brand-gradient text-2xl font-bold tracking-tight">IC Grifo</span>
        </div>
        {children}
      </div>
    </div>
  );
}
