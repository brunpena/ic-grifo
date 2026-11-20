"use client";

import { useQuery } from "@tanstack/react-query";
import { api, errorMessage, unwrap } from "@/lib/api";
import { useT } from "@/lib/i18n";

/** Indicador discreto de conexão com a API (usa GET /health). */
export function ApiStatus() {
  const { data, error, isPending } = useQuery({
    queryKey: ["health"],
    queryFn: () => unwrap(api.GET("/api/v1/health")),
  });
  const t = useT();

  let color = "bg-pending";
  let label = t("Verificando conexão com a API…");
  if (error) {
    color = "bg-danger";
    label = errorMessage(error, t);
  } else if (data?.status === "ok") {
    color = "bg-success";
    label = t("API conectada");
  } else if (data) {
    color = "bg-amber-500";
    label = t("API no ar, mas sem acesso ao banco de dados");
  }

  return (
    <p role="status" aria-live="polite" className="flex items-center gap-2 text-[13px] text-foreground-muted">
      <span aria-hidden className={`size-2 rounded-full ${color} ${isPending ? "animate-pulse" : ""}`} />
      {label}
    </p>
  );
}
