import { AssistantView } from "@/components/assistant/assistant-view";

/**
 * O Assistente fica no layout: trocar entre a tela inicial, a análise em montagem e o
 * documento aberto muda só a URL (e o histórico do navegador), sem desmontar a tela. Assim
 * envios em andamento, o PDF aberto e o cache continuam onde estavam. As páginas abaixo
 * existem para cada etapa ter o seu endereço (recarregar, Voltar/Avançar, compartilhar);
 * `AssistantView` lê os ids da URL.
 *
 * - `/assistente`: nova análise (bases de dados e histórico)
 * - `/assistente/analises/{id}`: análise com as bases, esperando o documento
 * - `/assistente/documentos/{id}`: documento aberto no espaço de trabalho
 */
export default function AssistantLayout({ children }: LayoutProps<"/[lang]/assistente">) {
  return (
    <>
      <AssistantView />
      {children}
    </>
  );
}
