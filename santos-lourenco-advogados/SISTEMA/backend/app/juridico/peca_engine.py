# -*- coding: utf-8 -*-
"""Motor de peca do escritorio: texto pela IA com o DNA + formatacao no TIMBRADO.docx.

Usado por routers/peca.py (Gerar Peca) e pelas skills (.claude/skills/timbrado/montar_peca.py
chama formatar_no_timbrado). Sem dependencia de pasta externa.

- gerar_texto_peca(): monta o prompt com juridico/DNA_ESCRITORIO.md (formatacao, abertura,
  fecho, teses, assinatura) e chama o Claude; se a Anthropic recusar, cai na IA de reserva.
- formatar_no_timbrado(): grava a peca no timbrado VITORIA BARBOSA no padrao unico das pecas
  protocoladas da Dra. Vitoria (ver juridico/padrao_vitoria.py): titulos centralizados em caixa,
  lei entre aspas no corpo, jurisprudencia recuada em italico, alineas com letra e valores em
  negrito, memoria de calculo em tabela, assinatura so da Dra. Vitoria.
"""
import os
import re
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DNA = AQUI / 'DNA_ESCRITORIO.md'
TIMBRADO = Path(os.getenv('SL_TIMBRADO_DOCX') or (AQUI / 'modelos' / 'TIMBRADO.docx'))
MODELO = os.getenv('SL_MODELO_PECA', 'claude-opus-5-5')
FONTE = os.getenv('SL_FONTE_PECA', 'Century Gothic')
TAMANHO = float(os.getenv('SL_TAMANHO_PECA', '12'))
RECUO_CM = float(os.getenv('SL_RECUO_PECA_CM', '3'))


def ler_dna():
    return DNA.read_text(encoding='utf-8') if DNA.exists() else ''


SISTEMA = """Voce e a advogada redatora do escritorio. Escreva a peca COMPLETA, pronta para revisao,
seguindo a risca o DNA abaixo (enderecamento, abertura "por sua advogada", topicos DA/DO em
caixa alta, transcricao de lei em paragrafo proprio entre aspas, ementa em paragrafo proprio
seguida da referencia entre parenteses, pedidos em alineas, fecho "Termos em que, pede
deferimento.", cidade e data, assinatura SO da Dra. Vitoria).

Regras inegociaveis:
- nunca invente jurisprudencia: sem precedente que esteja no DNA ou no bloco de jurisprudencia
  verificada, escreva [CONFERIR PRECEDENTE];
- nunca invente dado do cliente ou do processo: use [PREENCHER: campo];
- valores sempre com "R$"; memoria de calculo logo abaixo da alinea, uma linha por parcela no
  formato "Verba: R$ 0,00", terminando em "Total do pedido: R$ 0,00";
- assinatura unica: VITÓRIA KAREN BARBOSA DOS SANTOS – OAB/SP 490.295 (a Dra. Claudia nao assina);
- devolva SO o texto da peca, um paragrafo por linha, sem comentarios. Sem #. Use **negrito** apenas
  para destaques do padrao (nome das partes na qualificacao, datas-chave, valores, local de trabalho,
  expressao central da tese e do pedido) - no maximo 1 ou 2 por paragrafo.

===== DNA DO ESCRITORIO =====
{dna}
"""


def _chave_anthropic():
    try:
        from dotenv import dotenv_values
        from ..config import ENV_CENTRAL
        v = dotenv_values(str(ENV_CENTRAL)) if ENV_CENTRAL.exists() else {}
    except Exception:
        v = {}
    return (v.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_API_KEY') or '').strip()


def montar_prompt(dados_caso, tipo_peca, esqueleto='', jurisprudencia=''):
    partes = ['TIPO DE PECA: %s' % (tipo_peca or '').upper(), '', 'DADOS DO CASO E DOS AUTOS:', dados_caso or '']
    if esqueleto:
        partes += ['', 'ESQUELETO / ORIENTACAO DA ADVOGADA (siga a ordem dos topicos):', esqueleto]
    if jurisprudencia:
        partes += ['', 'JURISPRUDENCIA VERIFICADA (use so esta):', jurisprudencia]
    return '\n'.join(partes)


def gerar_texto_peca(dados_caso, tipo_peca, esqueleto='', jurisprudencia='', incluir_amostras=True,
                     max_tokens=16000):
    """Devolve o texto puro da peca (um paragrafo por linha)."""
    sistema = SISTEMA.format(dna=ler_dna() if incluir_amostras else '')
    msg = montar_prompt(dados_caso, tipo_peca, esqueleto, jurisprudencia)
    chave = _chave_anthropic()
    erro = None
    modo = (os.getenv('SL_IA_PECA') or ('api' if chave else 'cli')).lower()
    if modo == 'cli':  # Claude Code da assinatura do escritorio (sem credito de API)
        try:
            return limpar(_via_cli(sistema, msg))
        except Exception as e:
            erro = e
    if chave and modo != 'cli':
        try:
            import anthropic
            cli = anthropic.Anthropic(api_key=chave)
            r = cli.messages.create(model=MODELO, max_tokens=max_tokens, system=sistema,
                                    messages=[{'role': 'user', 'content': msg}])
            return limpar(''.join(b.text for b in r.content if getattr(b, 'type', '') == 'text'))
        except Exception as e:  # sem credito, fora do ar: tenta a reserva
            erro = e
    try:
        from .. import ia_reserva
        if ia_reserva.disponivel():
            return limpar(ia_reserva.texto(sistema, [{'role': 'user', 'content': msg}], max_tokens=max_tokens,
                                           modelo=ia_reserva.MODELO_PRO))
    except Exception as e:
        erro = erro or e
    raise RuntimeError('Nenhuma IA disponivel para gerar a peca (%s)' % (erro or 'sem ANTHROPIC_API_KEY/GEMINI_API_KEY'))


def _via_cli(sistema, msg, timeout=None):
    """claude -p com o prompt de sistema; usa a assinatura logada na maquina (CLAUDE_CODE_OAUTH_TOKEN no servidor)."""
    import shutil
    import subprocess
    exe = os.getenv('SL_CLAUDE_BIN') or shutil.which('claude') or '/usr/local/bin/claude'
    env = dict(os.environ)
    env.pop('ANTHROPIC_API_KEY', None)
    r = subprocess.run([exe, '-p', '--model', os.getenv('SL_MODELO_PECA_CLI', 'opus'), '--append-system-prompt',
                        sistema], input=msg, capture_output=True, text=True, encoding='utf-8',
                       env=env, timeout=timeout or int(os.getenv('SL_TIMEOUT_PECA', '900')))
    if r.returncode or not r.stdout.strip():
        raise RuntimeError('claude -p falhou (%s): %s' % (r.returncode, (r.stderr or r.stdout)[-400:]))
    return r.stdout


def limpar(texto):
    """Tira cabecalhos markdown soltos (#) e excesso de linhas; MANTEM **negrito** (padrao da Dra. Vitoria)."""
    t = (texto or '').replace('\r\n', '\n')
    t = re.sub(r'^\s*#+\s*', '', t, flags=re.M)
    return re.sub(r'\n{3,}', '\n\n', t).strip()


# ---------------------------------------------------------------- formatacao
def formatar_no_timbrado(texto, out_path, modelo=None):
    """Grava a peca no timbrado Vitoria Barbosa, no padrao unico das pecas protocoladas.

    Aceita texto puro (um paragrafo por linha, como a IA devolve) ou o Markdown do padrao
    (## / # / >>> / >>>> / >> / | / a) / [[ESPACO n]]). Ver juridico/padrao_vitoria.py.
    """
    from .padrao_vitoria import gerar_docx
    conteudo = texto or ''
    if not re.search(r'(?m)^(#\s|##\s|>>|\[\[ESPACO)', conteudo):
        conteudo = limpar(conteudo)
    return gerar_docx(conteudo, out_path, modelo=modelo or TIMBRADO)


if __name__ == '__main__':  # teste offline: so formatacao
    import tempfile
    exemplo = """AO JUÍZO DA 1ª VARA DO TRABALHO DE SUZANO – SP
Processo nº 0000000-00.2026.5.02.0491
FULANO DE TAL, nos autos da reclamação trabalhista que move em face de EMPRESA X LTDA., por suas advogadas, vem respeitosamente perante Vossa Excelência, apresentar sua RÉPLICA À CONTESTAÇÃO, pelos motivos de fato e de direito a seguir expostos:
DO INTERVALO INTRAJORNADA
A Reclamada sustenta que o intervalo era integralmente usufruído.
Ao contrário.
DOS PEDIDOS
a) a rejeição das teses defensivas;
b) a procedência integral dos pedidos.
Termos em que, pede deferimento.
Suzano, 10 de novembro de 2026.
VITÓRIA KAREN BARBOSA DOS SANTOS – OAB/SP 490.295
CLÁUDIA ALVES PEREIRA DE LIMA – OAB/SP 410.648"""
    out = formatar_no_timbrado(exemplo, Path(tempfile.gettempdir()) / 'teste_timbrado_sl.docx')
    from docx import Document
    from docx.oxml.ns import qn
    d = Document(out)
    ps = [p for p in d.paragraphs if p.text.strip()]
    txt = '\n'.join(p.text for p in ps)
    assert ps[0].runs[0].bold and ps[0].alignment == 1          # enderecamento centralizado
    assert 'CLÁUDIA' not in txt and 'por sua advogada' in txt     # regras do escritorio
    tit = next(p for p in ps if p.text == 'DO INTERVALO INTRAJORNADA')
    assert tit.runs[0].bold and tit._p.pPr.find(qn('w:pBdr')) is not None
    assert ps[-1].text.startswith('VITÓRIA') and ps[-1].runs[0].bold
    assert d.sections[0].header.part is not None
    print('ok', out, len(ps), 'paragrafos')
