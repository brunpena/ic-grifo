import type { Metadata } from "next";
import { AssistantView } from "@/components/assistant/assistant-view";

export const metadata: Metadata = { title: "Assistente · IC Grifo" };

export default function AssistantPage() {
  return <AssistantView />;
}
