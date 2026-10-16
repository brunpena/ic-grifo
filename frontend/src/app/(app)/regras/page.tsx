import type { Metadata } from "next";
import { KnowledgeBaseView } from "@/components/knowledge/knowledge-base-view";

export const metadata: Metadata = { title: "Base de regras · IC Grifo" };

export default function KnowledgeBasePage() {
  return <KnowledgeBaseView />;
}
