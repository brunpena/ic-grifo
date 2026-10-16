// Dados de exemplo da Base de regras. Ainda não existe API de regras: troque por
// uma consulta ao back quando ela existir e apague este arquivo.
import type { RuleView } from "@/components/rules/types";

export type DemoKbRule = RuleView & { document: string };

export const DEMO_DOCUMENTS = [
  "Contrato 042/2026 – Manutenção predial",
  "Edital de Pregão 17/2026",
  "Regulamento de Compras",
];

export const DEMO_KB_RULES: DemoKbRule[] = [
  { id: "k1", document: DEMO_DOCUMENTS[0], page: 3, type: "obrigacao", status: "validada", summary: "Entregar relatório mensal de atividades", excerpt: "A contratada deverá entregar o relatório mensal de atividades em até 10 dias úteis após o encerramento de cada mês." },
  { id: "k2", document: DEMO_DOCUMENTS[0], page: 3, type: "prazo", status: "validada", summary: "Relatório em até 10 dias úteis", excerpt: "em até 10 dias úteis após o encerramento de cada mês de execução" },
  { id: "k3", document: DEMO_DOCUMENTS[0], page: 4, type: "proibicao", status: "validada", summary: "Proibida a subcontratação sem autorização", excerpt: "É vedada a subcontratação total ou parcial do objeto sem prévia autorização por escrito da contratante." },
  { id: "k4", document: DEMO_DOCUMENTS[0], page: 7, type: "prazo", status: "validada", summary: "Vigência de 12 meses", excerpt: "O prazo de vigência do contrato é de 12 meses, contados da data de sua assinatura." },
  { id: "k5", document: DEMO_DOCUMENTS[0], page: 8, type: "condicao", status: "pendente", summary: "Multa de 0,5% ao dia em caso de atraso", excerpt: "Caso haja atraso injustificado na execução, será aplicada multa de 0,5% ao dia sobre o valor da parcela em atraso." },
  { id: "k6", document: DEMO_DOCUMENTS[0], page: 9, type: "obrigacao", status: "validada", summary: "Pagamento em até 30 dias do atesto", excerpt: "O pagamento será efetuado em até 30 dias após o atesto da nota fiscal pelo fiscal do contrato." },
  { id: "k7", document: DEMO_DOCUMENTS[1], page: 2, type: "prazo", status: "validada", summary: "Impugnação até 3 dias úteis antes da sessão", excerpt: "Qualquer pessoa poderá impugnar este edital até 3 dias úteis antes da data da sessão pública." },
  { id: "k8", document: DEMO_DOCUMENTS[1], page: 5, type: "obrigacao", status: "validada", summary: "Apresentar proposta com validade de 60 dias", excerpt: "A proposta deverá ter validade mínima de 60 dias, contados da data de sua apresentação." },
  { id: "k9", document: DEMO_DOCUMENTS[1], page: 6, type: "proibicao", status: "rejeitada", summary: "Vedada a participação de consórcios", excerpt: "Não será admitida a participação de empresas reunidas em consórcio." },
  { id: "k10", document: DEMO_DOCUMENTS[1], page: 9, type: "condicao", status: "validada", summary: "Garantia de 5% se o valor passar do limite", excerpt: "Se o valor global ultrapassar o limite previsto, será exigida garantia de 5% do valor do contrato." },
  { id: "k11", document: DEMO_DOCUMENTS[2], page: 1, type: "obrigacao", status: "validada", summary: "Três orçamentos para compras acima do limite", excerpt: "As compras acima do limite de dispensa exigem a apresentação de, no mínimo, três orçamentos." },
  { id: "k12", document: DEMO_DOCUMENTS[2], page: 2, type: "proibicao", status: "validada", summary: "Proibido fracionar despesas", excerpt: "É vedado o fracionamento de despesas para enquadramento em modalidade de menor valor." },
  { id: "k13", document: DEMO_DOCUMENTS[2], page: 4, type: "prazo", status: "pendente", summary: "Prestação de contas em até 15 dias", excerpt: "A prestação de contas deverá ocorrer em até 15 dias após a entrega do material." },
  { id: "k14", document: DEMO_DOCUMENTS[2], page: 5, type: "outro", status: "validada", summary: "Casos omissos decididos pela diretoria", excerpt: "Os casos omissos neste regulamento serão decididos pela diretoria administrativa." },
];
