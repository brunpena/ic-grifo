import { msg } from "@/lib/i18n/core";
import { localizedMetadata } from "@/lib/i18n/metadata";

export const generateMetadata = () => localizedMetadata(msg("Documento"));

// A tela vem do layout (`AssistantView`), que lê o id do documento na URL.
export default function DocumentPage() {
  return null;
}
