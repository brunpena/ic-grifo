import { msg } from "@/lib/i18n/core";
import { localizedMetadata } from "@/lib/i18n/metadata";

export const generateMetadata = () => localizedMetadata(msg("Nova análise"));

// A tela vem do layout (`AssistantView`), que lê o id da análise na URL.
export default function AnalysisPage() {
  return null;
}
