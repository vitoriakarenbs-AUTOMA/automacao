---
name: timbrado
description: Coloca qualquer peça no papel timbrado VITÓRIA BARBOSA, no padrão único das peças protocoladas da Dra. Vitória (Century Gothic 12, títulos centralizados em caixa, assinatura só da Dra. Vitória).
---

# timbrado

Use SEMPRE no último passo de QUALQUER peça (inicial, réplica, razões finais, RO, contrarrazões,
embargos, manifestação, contestação, execução). O papel é SOMENTE o timbrado **Vitória Barbosa**:
`SISTEMA/backend/app/juridico/modelos/TIMBRADO.docx`. Nunca recrie o cabeçalho e nunca use o
timbrado Lima & Lourenço.

O padrão foi calibrado em 10/11/2026 contra peças protocoladas e está em
`SISTEMA/backend/app/juridico/padrao_vitoria.py`, a mesma regra para todas as peças.

## Como usar

```
python .claude/skills/timbrado/scripts/aplicar_timbrado.py --in PECA.md --out "PECA.docx"   # Markdown
python .claude/skills/timbrado/montar_peca.py --texto PECA.txt --saida "PECA.docx"         # texto puro
```

## Marcações (Markdown)

| Marcação | Resultado |
|---|---|
| `## AO JUÍZO DA …` | endereçamento centralizado em negrito |
| `[[ESPACO 9]]` / `[[ESPACO 3]]` | linhas em branco (inicial: 9 após o endereçamento; peça nos autos: 3, "Processo nº", 3) |
| `\| **Processo nº …**` | linha sem recuo (nº do processo, RECORRENTE/RECORRIDA/ORIGEM) |
| `# DO TÍTULO` | título centralizado, negrito, dentro de caixa |
| texto normal | justificado, 1,5, recuo de 1ª linha 3 cm |
| `>>> "texto da lei"` | transcrição de lei/súmula: parágrafo normal entre aspas |
| `>>>> EMENTA…` e `>>>> (TST – RR …)` | jurisprudência: recuo 4 cm, itálico |
| `a) A condenação…` | alínea — letra e valores "R$" em negrito automático |
| `\| Verba: R$ 0,00` (linhas seguidas) | tabela de memória de cálculo; "Total…" em negrito |
| `- item` | lista com travessão no recuo do corpo |
| `>> Termos em que, pede deferimento.` / `>> Cidade, data.` | centralizado |
| `>> **VITÓRIA KAREN BARBOSA DOS SANTOS – OAB/SP 490.295**` | assinatura (única) |
| `**negrito**` | destaque: partes, datas-chave, valores, expressão central da tese/pedido (1–2 por parágrafo) |

Texto puro (um parágrafo por linha) também é aceito: o formatador reconhece endereçamento,
"Processo nº", títulos em caixa alta, citações entre aspas, ementas, alíneas, linhas
"Verba: R$ …", fecho, data e assinatura.

## Regras aplicadas automaticamente a toda peça
- remove a linha de assinatura da Dra. Cláudia (ela não assina mais as peças);
- "por suas advogadas" → "por sua advogada";
- "Dá-se a causa" → "Dá-se à causa" (e o valor da causa sai em negrito).
