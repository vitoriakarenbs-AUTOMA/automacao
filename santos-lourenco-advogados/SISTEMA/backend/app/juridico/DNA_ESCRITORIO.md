# DNA DAS PEÇAS — Santos Lourenço Advogados

Extraído em 10/11/2026 de 8 peças reais do escritório (inicial, 2 réplicas, recurso ordinário,
contrarrazões ao RO, razões finais, embargos de declaração e execução provisória) e dos modelos
de contrato e procuração. Os nomes das partes foram tirados. Todo prompt de produção e de revisão
de peça lê este arquivo **antes** de escrever. Se ele mudar, as peças mudam junto.

## 1. Quem assina e em nome de quem

- Sociedade: **VITÓRIA BARBOSA SOCIEDADE INDIVIDUAL DE ADVOCACIA**, CNPJ 69.977.673/0001-00,
  registro OAB/SP 72.647, com sede na Av. Armando Salles de Oliveira, 355, sala 05, Centro, Suzano/SP,
  CEP 08675-000 (é onde recebe as intimações).
- Assinatura (ÚNICA, em todas as peças, desde 10/11/2026 — instrução do usuário):
  ```
  VITÓRIA KAREN BARBOSA DOS SANTOS – OAB/SP 490.295
  ```
  A Dra. Cláudia **não assina mais as peças** (continua constando em procuração e contrato, que
  têm modelo próprio). O formatador remove a linha dela automaticamente.
- Quem revisa e protocola: **Dra. Vitória**. Ela também é a dona das tarefas.
- Na qualificação e no preâmbulo: "**por sua advogada**" (singular). O formatador corrige
  "por suas advogadas" automaticamente.
- Local e data: a cidade da vara, por extenso, seguida de vírgula, **centralizados**
  ("Suzano, 16 de junho de 2026.").

## 2. Formatação (igual em TODAS as peças — padrão das peças protocoladas)

Conferido em 10/11/2026 contra peças efetivamente protocoladas (iniciais de Danilo Santana e
Josiane Cardoso; manifestação de Jennifer Crisleine). Implementado em
`juridico/padrao_vitoria.py`, usado pelo sistema, pela skill `timbrado` e pelo agente de peças.

- Papel: SOMENTE o timbrado **VITÓRIA BARBOSA ADVOGADA** (`juridico/modelos/TIMBRADO.docx`, logo VB
  vinho no cabeçalho). Nunca o Lima & Lourenço. Nunca recrie o cabeçalho.
- Fonte **Century Gothic 12**, corpo **justificado**, entrelinha **1,5**, recuo da primeira linha
  **3 cm**.
- Títulos de tópico em **CAIXA ALTA, negrito, CENTRALIZADOS e DENTRO DE CAIXA (borda simples)**,
  sempre começando por "DA/DO/DAS/DOS". "RECLAMAÇÃO TRABALHISTA" também vai em caixa.
- Transcrição de **lei, súmula ou tese**: frase introdutória terminando em dois-pontos e o texto
  em **parágrafo próprio, entre aspas, no recuo normal do corpo**.
- **Jurisprudência** (ementa ou trecho de acórdão): bloco **recuado 4 cm, em itálico**, com a
  referência na linha seguinte entre parênteses ("(TST – RR …)"), também recuada.
- **Negrito de destaque**: nome das partes na qualificação, datas-chave, valores, local de trabalho
  e a expressão central da tese — com moderação (1–2 por parágrafo).
- Pedidos em alíneas `a)`, `b)`, `c)` ("a) A condenação da Reclamada…"), com a **letra e os
  valores em negrito** e a expressão-chave do pedido em negrito; cada uma termina em ponto e
  vírgula e a última em ponto.
- Memória de cálculo logo abaixo da alínea, em **tabela de 2 colunas** (verba | valor) com
  bordas; última linha "Total do pedido" em negrito.
- Valor da causa em negrito: "**Dá-se à causa o valor de R$ …, para fins de alçada.**"
- Fecho, cidade/data e assinatura **centralizados**; assinatura em negrito.
- Contrato e procuração usam Century Gothic 10 e 12, sem recuo (modelos próprios).

## 3. Endereçamento e abertura

- Primeira instância: `AO JUÍZO DA 1ª VARA DO TRABALHO DE SUZANO – SP` (sem "EXCELENTÍSSIMO",
  sem "MM."), **centralizado e em negrito**.
- Inicial: endereçamento + **9 linhas em branco** + qualificação.
- Peça nos autos: endereçamento + 3 linhas em branco + `Processo nº 0000000-00.0000.5.02.0000`
  (negrito, sem recuo) + 3 linhas em branco + abertura.
- Abertura padrão (manifestação no processo):
  > {RECLAMANTE EM CAIXA ALTA}, nos autos da reclamação trabalhista que move em face de
  > {RECLAMADA EM CAIXA ALTA}, por sua advogada, vem respeitosamente perante Vossa Excelência,
  > apresentar sua {NOME DA PEÇA EM CAIXA ALTA}, pelos motivos de fato e de direito a seguir
  > expostos:
- Inicial: qualificação completa (nacionalidade, estado civil, profissão, RG, CPF, endereço com
  CEP), "por sua advogada, vem respeitosamente perante Vossa Excelência, com fundamento no art.
  840, §1º da CLT, propor a presente", então `RECLAMAÇÃO TRABALHISTA` em linha própria (em caixa)
  e depois "Em face de" com cada reclamada (razão social em negrito, CNPJ, sede).
- Ordem dos primeiros tópicos da inicial: JUÍZO 100% DIGITAL → responsabilidade subsidiária/grupo
  econômico (se houver) → COMPETÊNCIA TERRITORIAL → CONTRATO DE TRABALHO.
- Seções fixas finais da inicial: JUSTIÇA GRATUITA → DA NÃO LIMITAÇÃO DOS VALORES DA INICIAL →
  DA LIQUIDAÇÃO DA INICIAL EM SEDE DE EXECUÇÃO → DOS JUROS E CORREÇÃO MONETÁRIA (ADCs 58/59 e
  Lei 14.905/2024) → DOS HONORÁRIOS ADVOCATÍCIOS → DOS PEDIDOS.
- Recursos: uma petição de interposição curta (fundamento, tempestividade, justiça gratuita,
  pedido de remessa ao TRT da 2ª Região, fecho e assinatura) e depois as razões, com o cabeçalho:
  ```
  EGRÉGIO TRIBUNAL REGIONAL DO TRABALHO DA 2ª REGIÃO
  RECORRENTE: …
  RECORRIDA: …
  PROCESSO Nº: …
  ORIGEM: 1ª VARA DO TRABALHO DE SUZANO/SP
  RAZÕES DE RECURSO ORDINÁRIO
  ```
  Nas contrarrazões entra também a saudação `EGRÉGIA TURMA,`.

## 4. Fecho

- Último tópico: `DOS PEDIDOS` (réplica, inicial, recursos) ou `DOS REQUERIMENTOS` /
  `DOS REQUERIMENTOS FINAIS` (embargos, razões finais).
- Fórmula de fecho, sempre em linha própria: **`Termos em que, pede deferimento.`**
- Depois vêm a cidade e a data (centralizadas) e por fim a assinatura única do item 1.
- Inicial: antes do fecho, em negrito, `Dá-se à causa o valor de R$ …, para fins de alçada.`
  (padrão das peças protocoladas, sem valor por extenso; o valor é a soma das alíneas, sem os
  pedidos sucessivos).

## 5. Tom e construção do argumento

- É um tom técnico e direto, de quem conhece o processo. O escritório não usa adjetivação
  excessiva nem jargão latino gratuito.
- A peça vai **rebatendo a defesa ponto a ponto**. Primeiro diz o que a reclamada alega
  ("A Reclamada impugna…, sustentando que…"), depois mostra por que isso não se sustenta ("A
  defesa, contudo, não enfrenta adequadamente os fatos narrados na petição inicial.").
- Usa frases curtas de virada em parágrafo próprio: "Ao contrário.", "Isso porque…",
  "Portanto, …", "Assim, …".
- Cita o trecho exato da inicial ou da defesa entre aspas, para fixar o que foi pedido.
- Ancora cada tópico em dispositivo legal (CLT, CF, Lei 9.029/95), em súmula ou OJ do TST e,
  quando houver, em precedente vinculante (ADI 5766, Tema 1046 etc.).
- A prova é narrada com dados concretos: horários, datas, valores, mensagens com hora, autos de
  infração, laudo.
- Quando o pedido é cautelar, usa "Por cautela, registra-se que…".

## 6. Teses recorrentes (lado do reclamante, TRT-2)

Jornada e intervalo
- Minutos residuais e tempo à disposição antes e depois do turno (art. 4º e art. 58, §1º, CLT;
  Súm. 366 e 429 TST). A tese não nega o ponto: mostra que o tempo marcado não entrava no cálculo.
- Supressão do intervalo intrajornada (art. 71, §4º, CLT), com **adicional convencional** quando a
  CCT prevê percentual maior (ex.: 80%).
- Súmula 338, I, TST: ônus da empresa com mais de 20 empregados de juntar os controles.
- Reflexos das horas extras no adicional noturno; omissão sobre adicional noturno de 40% vira ED.

Saúde, segurança e ambiente
- Adicional de insalubridade e reflexos, prova pericial e entrega ou retificação do PPP com
  multa cominatória.
- Adicional de periculosidade e reflexos.
- Afastar a tese defensiva de "ausência de nexo causal" quando o pedido não é de doença ocupacional.

Dispensa e dano moral
- Dispensa discriminatória (Lei 9.029/95, art. 4º, II: indenização em dobro) e majoração do dano
  moral no RO.
- Assédio moral.
- Danos morais por salário em atraso e por descumprimento convencional.

Vínculo e responsabilidade
- Reconhecimento de vínculo contra pejotização: subordinação, pessoalidade, habitualidade,
  onerosidade, inserção na estrutura e primazia da realidade; nulidade do contrato de prestação de
  serviços (art. 9º CLT).
- Grupo econômico (art. 2º, §§2º e 3º, CLT) e responsabilidade solidária.
- Responsabilidade subsidiária do ente público (Súm. 331, V, TST; fiscalização do contrato).
- Legitimidade do sócio no polo passivo.

Verbas e liquidação
- Verbas rescisórias, férias + 1/3, 13º, FGTS + 40%, seguro-desemprego, multa do art. 477, §8º, e
  multas convencionais.
- **Não limitação da condenação aos valores da inicial** (estimativa do art. 840, §1º, CLT; IN
  41/2018 TST). Essa tese aparece em quase toda peça.
- Liquidação: dedução só do que foi pago sob o mesmo título, períodos efetivamente abrangidos,
  juros e correção conforme a jurisprudência vinculante.
- Execução provisória com planilha de cálculos (arts. 876 e 878 CLT): intimação para pagar ou
  garantir e pesquisa patrimonial pelos sistemas do juízo.

Honorários e gratuidade
- Honorários sucumbenciais de 15% (art. 791-A CLT), majoração de 10% para 15% no RO.
- Na sucumbência recíproca do beneficiário da gratuidade: ADI 5766 (sem exigibilidade
  automática).
- Justiça gratuita e Juízo 100% Digital na inicial; segredo de justiça quando houver dado sensível.

## 7. Regra de ouro da automação

- **A IA decide sozinha** em caso simples e padronizado e em petição de andamento (ciência,
  juntada, manifestação de cálculo sem divergência, requerimento de execução com planilha pronta,
  ED de omissão evidente).
- Tudo o mais (inicial, réplica com tese nova, recurso, contrarrazões, acordo) **para para
  revisão da Dra. Vitória** antes de protocolar.
- A IA nunca inventa jurisprudência. Se o precedente não estiver neste DNA ou na base conferida,
  ela marca `[CONFERIR PRECEDENTE]` e segue.
- A IA nunca inventa dado do cliente. Se faltar, deixa `[PREENCHER: campo]`, e a peça com
  marcação aberta não sai para protocolo.
