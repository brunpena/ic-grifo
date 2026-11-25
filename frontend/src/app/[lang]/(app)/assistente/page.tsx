import { msg } from "@/lib/i18n/core";
import { localizedMetadata } from "@/lib/i18n/metadata";

export const generateMetadata = () => localizedMetadata(msg("Assistente"));

// A tela vem do layout (`AssistantView`).
export default function AssistantPage() {
  return null;
}
