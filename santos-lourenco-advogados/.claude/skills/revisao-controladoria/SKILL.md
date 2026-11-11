---
name: revisao-controladoria
description: Revisão final da controladoria: confere a peça contra o DNA, os autos e as regras e devolve o parecer com STATUS.
---

# revisao-controladoria

Confira:
- formatação e estrutura do DNA;
- abertura, fecho e assinatura;
- cada pedido com fato, fundamento e valor;
- aritmética;
- prazos;
- jurisprudência só verificada;
- nenhum [PREENCHER] esquecido;
- coerência com a decisão ou com a defesa rebatida.

Entregue `saida/PARECER_REVISAO.md` com uma linha exatamente em um destes formatos:
`STATUS: APROVADA` | `STATUS: APROVADA COM RESSALVAS` | `STATUS: NÃO APROVADA`
seguida dos achados, classificados como crítico, ajuste ou sugestão. Se houver ressalvas, aplique-as
e diga o que mudou.

Leia antes o `SISTEMA/backend/app/juridico/DNA_ESCRITORIO.md`.

## Padrão único de formatação (todas as peças)
Papel SOMENTE timbrado Vitória Barbosa; assinatura SOMENTE "VITÓRIA KAREN BARBOSA DOS SANTOS – OAB/SP 490.295";
"por sua advogada". Títulos centralizados em caixa; lei entre aspas no corpo; jurisprudência recuada 4 cm em itálico;
alíneas com letra e valores em negrito; memória de cálculo em tabela. Gere o .docx sempre pela skill `timbrado`
(`scripts/aplicar_timbrado.py` para Markdown, `montar_peca.py` para texto) — ela aplica o padrão de
`SISTEMA/backend/app/juridico/padrao_vitoria.py`, calibrado nas peças protocoladas (10/11/2026).
