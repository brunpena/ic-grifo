import { msg } from "@/lib/i18n";

/**
 * Mensagens fixas que o back-end envia em português (erros e situação do processamento).
 * `errorMessage` e as telas passam esses textos por `t(...)`; listados aqui, o
 * `npm run i18n:check` exige a versão em inglês. Mensagens montadas com valores (nomes,
 * contagens) ou geradas pela IA continuam em português. Ao mudar um texto no back-end,
 * atualize-o aqui e em `en.ts`, senão ele volta a aparecer em português.
 */
export const SERVER_MESSAGES = [
  // Sessão e conta
  msg("Sua sessão expirou. Entre novamente."),
  msg("E-mail ou senha incorretos."),
  msg("Já existe uma conta com este e-mail."),
  msg("A senha atual está incorreta."),
  // Não encontrado / estado
  msg("Análise não encontrada."),
  msg("Documento não encontrado."),
  msg("Regra não encontrada."),
  msg("Base de dados não encontrada."),
  msg("Arquivo não encontrado."),
  msg("A base não está disponível nesta análise."),
  msg("Aguarde o documento terminar de ser analisado."),
  msg("Aguarde a verificação terminar antes de editar a regra."),
  msg("Aguarde a verificação terminar antes de excluir a regra."),
  msg("Uma verificação deste documento já está em andamento."),
  msg("Somente documentos interrompidos podem ser retomados."),
  msg("Esta regra ainda não tem busca."),
  msg("Esta regra não tem uma busca válida."),
  msg("Esta regra precisa ser validada novamente."),
  msg("As bases ou suas colunas mudaram. Valide a regra novamente."),
  // Arquivos e links
  msg("O arquivo está vazio."),
  msg("O arquivo não é um PDF válido."),
  msg("Este PDF é protegido por senha."),
  msg("O arquivo não parece ser um CSV de texto."),
  msg("Este arquivo parece ser do Excel. Salve a planilha como CSV."),
  msg("A base só tem o cabeçalho, sem nenhuma linha de dados."),
  msg("O cabeçalho da base mudou. Envie a base novamente."),
  msg("O arquivo da base não foi encontrado. Envie a base de novo."),
  msg("Não foi possível ler a base. Envie de novo."),
  msg("Não foi possível diagramar o conteúdo em páginas."),
  msg("Não foi possível ler o texto do conteúdo convertido."),
  msg("O link não é válido."),
  msg("O link não tem um endereço de site."),
  msg("Use um link que comece com http:// ou https://."),
  msg("Links com usuário e senha não são aceitos."),
  msg("Este link aponta para um endereço interno ou privado e foi bloqueado."),
  msg("Não foi possível conectar ao site do link."),
  msg("A conexão com o site caiu durante o download."),
  msg("A página não foi encontrada (erro 404). Confira o link."),
  msg("O site limitou os acessos agora. Tente de novo em alguns minutos."),
  msg("O site redirecionou para um endereço inválido."),
  // IA
  msg("A IA não interpretou as colunas da base."),
  msg("A IA não concluiu a interpretação. Tente validar novamente."),
  msg("Resposta incompleta da IA. Continue para tentar este pacote novamente."),
  // Situação do processamento
  msg("Interpretando o significado das colunas com IA"),
  msg("Aguardando a interpretação das bases"),
  msg("Gerando as buscas nas bases de dados"),
  msg("Validando todas as regras nas bases"),
  msg("Retomando pacotes pendentes"),
  msg("1 busca gerada pela IA não passou na validação. Corrija na regra."),
];
