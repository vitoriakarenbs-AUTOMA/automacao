# -*- coding: utf-8 -*-
"""Padrao unico de formatacao das pecas da Dra. Vitoria (todas as pecas: inicial, replica, razoes
finais, recursos, contrarrazoes, embargos, manifestacoes, contestacao, execucao).

Calibrado em 10/11/2026 contra pecas efetivamente protocoladas (iniciais de Danilo Santana e Josiane
Cardoso; manifestacao de Jennifer Crisleine) e com as regras definidas pelo usuario:
- papel: SOMENTE o timbrado VITORIA BARBOSA ADVOGADA (juridico/modelos/TIMBRADO.docx);
- assinatura: SOMENTE "VITÓRIA KAREN BARBOSA DOS SANTOS – OAB/SP 490.295"; preambulo "por sua advogada";
- Century Gothic 12, justificado, entrelinha 1,5, recuo de 1a linha 3 cm;
- enderecamento centralizado em negrito; inicial: 9 linhas em branco depois; peca nos autos:
  3 linhas, "Processo nº" em negrito, mais 3 linhas;
- titulos DA/DO centralizados, em negrito, dentro de caixa com borda;
- transcricao de lei/sumula: paragrafo normal entre aspas; jurisprudencia: bloco 4 cm em italico;
- aliena de pedido: letra e valores "R$" em negrito; memoria de calculo em tabela verba | valor;
- "Dá-se à causa o valor de R$ ..., para fins de alçada." em negrito;
- fecho, cidade/data e assinatura centralizados.

Entradas aceitas:
- Markdown do padrao (mesma sintaxe da skill banco-teses-vitoria-trabalhista):
  ## enderecamento | # TITULO | >>> lei | >>>> jurisprudencia | >> centralizado | "| " sem recuo |
  "| Verba: R$ 0,00" tabela | a) alinea | - item | [[ESPACO n]] | [[QUEBRA]] | **negrito** *italico*
- Texto puro (um paragrafo por linha, como a IA devolve): convertido por texto_para_markdown().
"""
import os
import re
import sys
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
TIMBRADO = Path(os.getenv('SL_TIMBRADO_DOCX') or (AQUI / 'modelos' / 'TIMBRADO.docx'))

ASSINATURA = 'VITÓRIA KAREN BARBOSA DOS SANTOS – OAB/SP 490.295'

FONTE = ('<w:rFonts w:ascii="Century Gothic" w:hAnsi="Century Gothic" w:cs="Arial"/>'
         '<w:color w:val="000000"/><w:sz w:val="24"/><w:szCs w:val="24"/>')
CAIXA = ('<w:pBdr><w:top w:val="single" w:sz="4" w:space="1" w:color="auto"/>'
         '<w:left w:val="single" w:sz="4" w:space="4" w:color="auto"/>'
         '<w:bottom w:val="single" w:sz="4" w:space="1" w:color="auto"/>'
         '<w:right w:val="single" w:sz="4" w:space="4" w:color="auto"/></w:pBdr>')
L15 = '<w:spacing w:line="360" w:lineRule="auto"/>'
L10 = '<w:spacing w:line="240" w:lineRule="auto"/>'
RECUO = '<w:ind w:firstLine="1701"/>'               # 3 cm
CITACAO = '<w:ind w:left="2268" w:firstLine="0"/>'  # 4 cm
CORPO = L15 + RECUO + '<w:jc w:val="both"/>'
VALOR = re.compile(r"(?<!\*)(R\$\s?[\d.]+,\d{2})")
MEMORIA = re.compile(r"^\|\s+(.+?):\s*(R\$\s?[\d.]+,\d{2})\s*;?$")
PLACEHOLDER = re.compile(r"(?<!\[)\[(?!\[)(?!\.\.\.\]|…\]|sic\])[^\[\]\n]{1,120}\](?!\])")


# ------------------------------------------------------------------ regras do escritorio
def normalizar(md):
    """Aplica as regras fixas do escritorio a qualquer peca."""
    linhas = []
    for ln in md.replace('\r\n', '\n').split('\n'):
        if re.search(r'CL[ÁA]UDIA\s+ALVES\s+PEREIRA\s+DE\s+LIMA', ln, re.I) and re.search(r'OAB', ln):
            continue  # a Dra. Claudia nao assina mais as pecas (instrucao de 10/11/2026)
        linhas.append(ln)
    md = '\n'.join(linhas)
    md = re.sub(r'\bpor suas advogadas\b', 'por sua advogada', md)
    md = re.sub(r'\bPor suas advogadas\b', 'Por sua advogada', md)
    md = re.sub(r'\bpor seus advogados\b', 'por sua advogada', md)
    md = re.sub(r'Dá-se a causa', 'Dá-se à causa', md)
    md = re.sub(r'OAB/SP\s+nº\s+490\.295', 'OAB/SP 490.295', md)
    return md


# ------------------------------------------------------------------ texto puro -> markdown
_ENDERECO = re.compile(r'^(AO JU[IÍ]ZO|EXCELENT|EGR[EÉ]GI|AO EGR[EÉ]GIO|AO TRIBUNAL|AO COLENDO|COLENDO)', re.I)
_PROCESSO = re.compile(r'^(PROCESSO|AUTOS)\s*(N[ºo°.]|:)', re.I)
_CABECALHO_RECURSO = re.compile(r'^(RECORRENTE|RECORRID[OA]S?|ORIGEM|PROCESSO Nº|AGRAVANTE|AGRAVAD[OA]|EMBARGANTE|EMBARGAD[OA])\s*:', re.I)
_ASSIN = re.compile(r'OAB/[A-Z]{2}\s*(nº\s*)?[\d.]+\s*$')
_DATA_LOCAL = re.compile(r'^[A-ZÀ-Ú][\wÀ-ú\' ]+, \d{1,2}º? de [a-zç]+ de \d{4}\.?$')
_MEMO_TXT = re.compile(r'^(?!\s*[a-z]{1,2}\))([^:]{3,70}):\s*(R\$\s?[\d.]+,\d{2})\s*;?$')


def _eh_titulo(s):
    letras = re.sub(r'[^A-Za-zÀ-ú]', '', s)
    return (3 < len(s) <= 160 and letras and s.upper() == s and not s.endswith((';', ','))
            and not _ASSIN.search(s))


def _eh_jurisprudencia_txt(s):
    t = s.lstrip('"“ ')
    return bool(re.match(r'^[A-ZÀ-Ú]{4,}[A-ZÀ-Ú .,/–-]{10,}', t)) and not _eh_titulo(s)


def texto_para_markdown(texto):
    """Converte o texto puro devolvido pela IA (um paragrafo por linha) no Markdown do padrao."""
    brutas = [l.strip() for l in (texto or '').replace('\r\n', '\n').split('\n')]
    brutas = [l for l in brutas if l]
    out, i = [], 0
    ja_enderecou = False
    while i < len(brutas):
        s = brutas[i]
        prox = brutas[i + 1] if i + 1 < len(brutas) else ''
        if s.startswith(('#', '>>', '| ', '[[', '- ')) or re.match(r'^[a-z]{1,2}\)\s', s):
            out.append(s)  # ja esta em Markdown do padrao
        elif not ja_enderecou and _ENDERECO.match(s):
            ja_enderecou = True
            out.append('## ' + s.replace('**', ''))
            out.append('[[ESPACO 3]]' if _PROCESSO.match(prox) or _CABECALHO_RECURSO.match(prox) else '[[ESPACO 9]]')
        elif _PROCESSO.match(s) and len(s) < 80:
            out.append('| **%s**' % s.replace('**', ''))
            out.append('[[ESPACO 3]]')
        elif _CABECALHO_RECURSO.match(s):
            out.append('| **%s**' % s.replace('**', ''))
        elif _ASSIN.search(s):
            out.append('>> **%s**' % s.replace('**', ''))
        elif s.lower().startswith('termos em que') or _DATA_LOCAL.match(s):
            out.append('>> ' + s)
        elif s.startswith(('Dá-se', 'Da-se', '**Dá-se')):
            out.append('**%s**' % s.replace('**', ''))
        elif _eh_titulo(s):
            out.append('# ' + s)
        elif _MEMO_TXT.match(s) and (_MEMO_TXT.match(prox) or (out and out[-1].startswith('| ') and MEMORIA.match(out[-1]))):
            out.append('| ' + s.rstrip(';'))
        elif s[:1] in '"“' or (s.startswith('(') and out and out[-1].startswith('>>>')):
            out.append('>>> ' + s)
        elif _eh_jurisprudencia_txt(s):
            out.append('>>>> ' + s)
        else:
            out.append(s)
        i += 1
    return '\n\n'.join(out)


# ------------------------------------------------------------------ markdown -> OOXML
def _esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _aspas(t):
    t = re.sub(r'(?<![\w])"(?=\S)', '“', t)
    return t.replace('"', '”')


def _runs(texto, bold=False, italic=False):
    texto = _aspas(texto)
    out = []
    for p in re.split(r'(\*\*.+?\*\*|__.+?__|\*[^*\s][^*]*?\*)', texto):
        if not p:
            continue
        b, i, u = bold, italic, False
        if p.startswith('**') and p.endswith('**') and len(p) > 4:
            p, b = p[2:-2], True
        elif p.startswith('__') and p.endswith('__') and len(p) > 4:
            p, u = p[2:-2], True
        elif p.startswith('*') and p.endswith('*') and len(p) > 2:
            p, i = p[1:-1], True
        rpr = FONTE + ('<w:b/><w:bCs/>' if b else '') + ('<w:i/><w:iCs/>' if i else '') + ('<w:u w:val="single"/>' if u else '')
        out.append('<w:r><w:rPr>%s</w:rPr><w:t xml:space="preserve">%s</w:t></w:r>' % (rpr, _esc(p)))
    return ''.join(out)


def _par(ppr, conteudo='', bold=False, italic=False):
    mark = '<w:rPr>%s%s</w:rPr>' % (FONTE, '<w:b/>' if bold else '')
    return '<w:p><w:pPr>%s%s</w:pPr>%s</w:p>' % (ppr, mark, _runs(conteudo, bold, italic) if conteudo else '')


def _alinea(linha):
    m = re.match(r'^([a-z]{1,2}\))\s+(.*)$', linha.strip())
    corpo = re.sub(r'\*\*\*\*', '', VALOR.sub(r'**\1**', m.group(2)))
    return _par(CORPO, '**%s** %s' % (m.group(1), corpo))


def _eh_jurisprudencia(texto):
    t = texto.lstrip('"“ ')
    return texto.startswith('(') or bool(re.match(r'^[A-ZÀ-Ú]{4,}[A-ZÀ-Ú .,/–-]{10,}', t))


def _paragrafo(linha, jurisprudencia=False):
    if linha.startswith('## '):
        return _par(L10 + '<w:jc w:val="center"/>', linha[3:].strip(), bold=True)
    if linha.startswith('# '):
        return _par(CAIXA + L15 + '<w:jc w:val="center"/>', linha[2:].strip(), bold=True)
    if linha.startswith('>>>> '):
        return _par(L15 + CITACAO + '<w:jc w:val="both"/>', linha[5:].strip(), italic=True)
    if linha.startswith('>>> '):
        txt = linha[4:].strip()
        if jurisprudencia or _eh_jurisprudencia(txt):
            return _par(L15 + CITACAO + '<w:jc w:val="both"/>', txt, italic=True)
        return _par(CORPO, txt)
    if linha.startswith('>> '):
        return _par('<w:jc w:val="center"/>', linha[3:].strip())
    if linha.startswith('| '):
        return _par(L15 + '<w:ind w:firstLine="0"/><w:jc w:val="both"/>', linha[2:].strip())
    if re.match(r'^[a-z]{1,2}\)\s', linha):
        return _alinea(linha)
    if re.match(r'^[-•]\s', linha):
        return _par(CORPO, '– ' + linha[2:].strip())
    return _par(CORPO, linha.strip())


def _tabela(linhas):
    borda = ''.join('<w:%s w:val="single" w:sz="4" w:space="0" w:color="auto"/>' % l
                    for l in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
    xml = ['<w:tbl><w:tblPr><w:tblW w:w="8505" w:type="dxa"/><w:tblBorders>%s</w:tblBorders>'
           '<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid><w:gridCol w:w="6237"/><w:gridCol w:w="2268"/></w:tblGrid>' % borda]
    for verba, valor in linhas:
        total = verba.strip().lower().startswith('total')
        cel = ''
        for txt, w in ((verba.strip(), 6237), (valor.strip(), 2268)):
            cel += ('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/></w:tcPr>' % w
                    + _par('<w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:jc w:val="left"/>', txt, bold=total)
                    + '</w:tc>')
        xml.append('<w:tr>%s</w:tr>' % cel)
    xml.append('</w:tbl>')
    xml.append('<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:rPr><w:sz w:val="12"/></w:rPr></w:pPr></w:p>')
    return ''.join(xml)


def _especial(ln):
    return (ln.startswith(('# ', '## ', '>> ', '>>> ', '>>>> ', '| ', '[[')) or re.match(r'^[a-z]{1,2}\)\s', ln)
            or re.match(r'^[-•]\s', ln))


def markdown_para_body(md):
    linhas = []
    for bruto in re.split(r'\n\s*\n', md.strip()):
        acum = []
        for ln in [l.rstrip() for l in bruto.splitlines() if l.strip()]:
            if re.match(r'^\[\[ESPACO\s*(\d+)\]\]$', ln.strip(), re.I) or ln.strip().upper() == '[[QUEBRA]]' or _especial(ln):
                if acum:
                    linhas.append(' '.join(acum)); acum = []
                linhas.append(ln)
            else:
                acum.append(ln.strip())
        if acum:
            linhas.append(' '.join(acum))
    blocos, i = [], 0
    while i < len(linhas):
        ln = linhas[i]
        m = re.match(r'^\[\[ESPACO\s*(\d+)\]\]$', ln.strip(), re.I)
        if m:
            blocos.extend(_par(L10) for _ in range(int(m.group(1)))); i += 1; continue
        if ln.strip().upper() == '[[QUEBRA]]':
            blocos.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>'); i += 1; continue
        if MEMORIA.match(ln):
            grupo = []
            while i < len(linhas) and MEMORIA.match(linhas[i]):
                grupo.append(MEMORIA.match(linhas[i]).groups()); i += 1
            blocos.append(_tabela(grupo)); continue
        if ln.startswith('>>> '):
            prox = linhas[i + 1] if i + 1 < len(linhas) else ''
            ant = linhas[i - 1] if i else ''
            juris = (prox.startswith(('>>> (', '>>>> (')) or
                     (ant.startswith(('>>> ', '>>>> ')) and ln[4:].lstrip().startswith('(')))
            blocos.append(_paragrafo(ln, jurisprudencia=juris)); i += 1; continue
        blocos.append(_paragrafo(ln)); i += 1
    return ''.join(blocos)


def pendencias(md):
    return sorted(set(PLACEHOLDER.findall(md)))


def gerar_docx(conteudo, out_path, modelo=None):
    """Grava a peca (Markdown do padrao OU texto puro) no timbrado Vitoria Barbosa. Devolve o caminho."""
    md = conteudo or ''
    if not re.search(r'(?m)^(#\s|##\s|>>|\[\[ESPACO)', md):
        md = texto_para_markdown(md)
    md = normalizar(md)
    base = Path(modelo or TIMBRADO)
    if not base.exists():
        raise FileNotFoundError('Timbrado nao encontrado: %s (copie o TIMBRADO.docx Vitoria Barbosa)' % base)
    body = markdown_para_body(md)
    zin = zipfile.ZipFile(str(base))
    doc = zin.read('word/document.xml').decode('utf-8')
    i_body = doc.find('<w:body>') + len('<w:body>')
    i_sect = doc.rfind('<w:sectPr')
    if i_body < 8 or i_sect < 0:
        raise ValueError('timbrado invalido: %s' % base)
    novo = doc[:i_body] + body + doc[i_sect:]
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(out), 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'word/document.xml':
                data = novo.encode('utf-8')
            zout.writestr(item, data)
    return str(out)


if __name__ == '__main__':  # teste offline
    import tempfile
    exemplo = """AO JUÍZO DA 1ª VARA DO TRABALHO DE SUZANO – SP
Processo nº 0000000-00.2026.5.02.0491
FULANO DE TAL, nos autos da reclamação trabalhista que move em face de EMPRESA X LTDA., por suas advogadas, vem respeitosamente perante Vossa Excelência, apresentar sua RÉPLICA, pelos motivos de fato e de direito a seguir expostos:
DO INTERVALO INTRAJORNADA
A Reclamada sustenta que o intervalo era integralmente usufruído. O art. 71, § 4º, da CLT estabelece:
"A não concessão ou a concessão parcial do intervalo intrajornada mínimo..."
Nesse sentido:
RECURSO DE REVISTA. INTERVALO INTRAJORNADA. PRÉ-ASSINALAÇÃO. Texto da ementa.
(TST - RR: 0000000-00.0000.5.00.0000, 1ª Turma)
DOS PEDIDOS
a) A condenação da Reclamada ao pagamento do intervalo, no valor estimado de R$ 1.234,56;
Intervalo: R$ 1.000,00
Total do pedido: R$ 1.234,56
b) A procedência integral dos pedidos.
Dá-se a causa o valor de R$ 1.234,56, para fins de alçada.
Termos em que, pede deferimento.
Suzano, 10 de novembro de 2026.
VITÓRIA KAREN BARBOSA DOS SANTOS – OAB/SP 490.295
CLÁUDIA ALVES PEREIRA DE LIMA – OAB/SP 410.648"""
    out = gerar_docx(exemplo, Path(tempfile.gettempdir()) / 'teste_padrao_vitoria.docx')
    from docx import Document
    from docx.oxml.ns import qn
    d = Document(out)
    ps = [p for p in d.paragraphs if p.text.strip()]
    txt = '\n'.join(p.text for p in ps)
    assert 'CLÁUDIA' not in txt and 'por sua advogada' in txt and 'Dá-se à causa' in txt
    titulo = next(p for p in ps if p.text == 'DO INTERVALO INTRAJORNADA')
    assert titulo._p.pPr.find(qn('w:pBdr')) is not None and titulo.runs[0].bold
    ementa = next(p for p in ps if p.text.startswith('RECURSO DE REVISTA'))
    assert ementa._p.pPr.find(qn('w:ind')).get(qn('w:left')) == '2268' and ementa.runs[0].italic
    lei = next(p for p in ps if p.text.startswith('“A não concessão'))
    assert lei._p.pPr.find(qn('w:ind')).get(qn('w:left')) is None
    al = next(p for p in ps if p.text.startswith('a)'))
    assert al.runs[0].bold and any(r.bold and 'R$' in r.text for r in al.runs)
    assert len(d.tables) == 1 and d.tables[0].rows[-1].cells[0].paragraphs[0].runs[0].bold
    assert ps[-1].text.startswith('VITÓRIA') and ps[-1].runs[0].bold
    assert d.sections[0].header.part is not None
    print('ok', out, len(ps), 'paragrafos')
