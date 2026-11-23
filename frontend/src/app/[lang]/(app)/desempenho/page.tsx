import { msg } from "@/lib/i18n/core";
import { localizedMetadata } from "@/lib/i18n/metadata";
import { PerformanceView } from "@/components/performance/performance-view";

export const generateMetadata = () => localizedMetadata(msg("Desempenho"));

export default function Page() {
  return <PerformanceView />;
}
