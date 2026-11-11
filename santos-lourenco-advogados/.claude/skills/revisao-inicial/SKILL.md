---
name: revisao-inicial
description: Revisão de petição inicial e de emenda pela controladoria (revisao-controladoria + checklist da inicial).
---

# revisao-inicial

Aplique a `revisao-controladoria` e confira também:
- qualificação completa do reclamante e das reclamadas, com CNPJ;
- competência territorial (local da prestação do serviço);
- pedidos líquidos (art. 840, §1º);
- valor da causa igual à soma dos pedidos;
- todos os documentos citados existem na pasta.

Leia antes o `SISTEMA/backend/app/juridico/DNA_ESCRITORIO.md`.

## Padrão único de formatação (todas as peças)
Papel SOMENTE timbrado Vitória Barbosa; assinatura SOMENTE "VITÓRIA KAREN BARBOSA DOS SANTOS – OAB/SP 490.295";
"por sua advogada". Títulos centralizados em caixa; lei entre aspas no corpo; jurisprudência recuada 4 cm em itálico;
alíneas com letra e valores em negrito; memória de cálculo em tabela. Gere o .docx sempre pela skill `timbrado`
(`scripts/aplicar_timbrado.py` para Markdown, `montar_peca.py` para texto) — ela aplica o padrão de
`SISTEMA/backend/app/juridico/padrao_vitoria.py`, calibrado nas peças protocoladas (10/11/2026).
