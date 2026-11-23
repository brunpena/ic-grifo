import { msg } from "@/lib/i18n/core";
import { localizedMetadata } from "@/lib/i18n/metadata";
import { KnowledgeBaseView } from "@/components/knowledge/knowledge-base-view";

export const generateMetadata = () => localizedMetadata(msg("Base de regras"));

export default function Page() {
  return <KnowledgeBaseView />;
}
