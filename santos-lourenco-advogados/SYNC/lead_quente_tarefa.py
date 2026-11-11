# -*- coding: utf-8 -*-
"""LEAD QUENTE COMO TAREFA no Sistema Santos Lourenço, em tempo real (pedido da Vitória em 02/10/2026).

Os dois avisos de lead quente que iam para o WhatsApp da Vitória viram TAREFA URGENTE para a vendedora
da vez, e a faixa vermelha aparece na tela dela (bloco_aviso_tarefas.js, conferencia de 1 em 1 min):

  1. LIGAR AGORA (alarme_qualificado.py, de 5 em 5 min): lead que contou uma irregularidade e ja saiu
     da empresa. A tarefa vai para a vendedora que o alarme escolheu e leva o mesmo texto do alarme.
     A vendedora continua recebendo o alarme no WhatsApp; a Vitória saiu da copia (ALARME_DESTINO vazio).
  2. LEAD RESPONDEU a regua dos quentes (fluxo_quentes_sl.py): a regua so le resposta as 10h, 13h,
     16h e 19h; aqui a resposta e percebida em ate 2 minutos. Quem diz que ja tem acao ou advogado
     nao vira tarefa (a regua tira o card no horario dela). Vai para a vendedora da vez, no mesmo
     rodizio do LIGAR AGORA (roteamento_vendedoras.py), com sugestao de resposta pronta.

Regras: so LE a fila da regua e o estado do alarme (nao grava neles), so ACRESCENTA tarefa (uma por
lead e por resposta; rodar de novo nao duplica), nao move card e nao manda mensagem.
Na primeira rodada com --enviar, o que ja foi avisado a Vitória antes desta troca fica marcado como
feito e nao vira tarefa; resposta que ainda nao tinha sido lida pela regua vira tarefa.

Uso:  python3 lead_quente_tarefa.py            (simulacao: mostra as tarefas que abriria)
      python3 lead_quente_tarefa.py --enviar   (abre as tarefas)
"""
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# Os tres modulos abaixo trocam o sys.stdout por um TextIOWrapper ao serem importados. Importados
# juntos, o segundo descarta o wrapper do primeiro, que ao ser coletado FECHA a saida de todos.
# Durante o import o stdout fica num StringIO (sem .buffer, eles nao mexem) e o embrulho e feito uma vez.
_saida, sys.stdout = sys.stdout, io.StringIO()
try:
    import alarme_qualificado as AQ        # noqa: E402  estado do alarme e ultima_troca
    import fluxo_quentes_sl as FQ         # noqa: E402  fila da regua, _respondeu_depois, classificar_resposta
    import relatorio_reaquecimento as RR   # noqa: E402  conversa_recente e CLAUDE_BIN da sugestao
    import roteamento_vendedoras as ROTA   # noqa: E402  vendedora da vez
finally:
    sys.stdout = _saida
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB = '/opt/santoslourenco/SISTEMA/backend/sistema_sl.db'
ESTADO = os.path.join(HERE, 'lead_quente_tarefa_state.json')
TIPO = 'ENTRAR EM CONTATO COM O LEAD'
USUARIOS = {'Rafaella': (10, 'Rafaella Araújo'), 'Marcella': (7, 'Marcella Lourenço')}


def _json(path, padrao):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return padrao


def _salvar(path, dados):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _limpo(t):
    """Tira a formatacao do WhatsApp (*negrito*, _italico_), que no sistema apareceria crua."""
    t = re.sub(r'\*([^*\n]+)\*', r'\1', t or '')
    return re.sub(r'(^|\s)_([^_\n]+)_(?=\s|$)', r'\1\2', t, flags=re.M)


def _hora(iso):
    try:
        return datetime.fromisoformat(str(iso)[:19]).strftime('%d/%m às %H:%M')
    except Exception:
        return ''


def sugerir_resposta(c):
    """Mensagem curta para a vendedora mandar antes de ligar. Mesma leitura do relatorio_reaquecimento,
    mas quem liga e a NOSSA EQUIPE, nao a Dra. Vitória (Pam, 02/10/2026). Claude da assinatura."""
    ctx = RR.conversa_recente(c['conversa_id'])
    env = dict(os.environ)
    env.pop('ANTHROPIC_API_KEY', None)          # assinatura, nunca API
    prompt = (
        'Voce escreve mensagens de WhatsApp para um escritorio de advocacia '
        'trabalhista que atende CAMINHONEIROS. Escreva a proxima mensagem que o '
        'escritorio deve mandar para este lead, que acabou de responder.\n\n'
        'REGRAS OBRIGATORIAS:\n'
        '- objetivo unico: confirmar dia e horario da LIGACAO da nossa equipe\n'
        '- quem liga e "a nossa equipe"; nao diga que a Dra. Vitória vai ligar\n'
        '- linguagem simples, de boleia, tratamento respeitoso\n'
        '- NUNCA prometer resultado, valor ou ganho de causa (Provimento 205/2021 da OAB)\n'
        '- NAO usar travessao como pontuacao\n'
        '- no maximo 4 linhas curtas\n'
        '- se a pessoa deu um horario, confirme esse horario\n'
        '- se a pessoa perguntou algo, responda de forma breve e leve para a ligacao\n\n'
        f"LEAD: {c.get('nome') or 'sem nome'}\n"
        f"SITUACAO: {c.get('situacao') or 'nao informado'}\n"
        f"CASO: {c.get('violacao') or 'nao detalhado'}\n"
        f"ULTIMA RESPOSTA DELE: \"{(c.get('resposta') or '')[:300]}\"\n\n"
        f"CONVERSA RECENTE:\n{ctx[:1500]}\n\n"
        'Responda APENAS o texto da mensagem, sem aspas e sem explicacao.')
    try:
        r = subprocess.run([RR.CLAUDE_BIN, '-p', '--model', 'sonnet', '--tools', '',
                            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}'],
                           input=prompt.encode('utf-8'), stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, env=env,
                           cwd=tempfile.gettempdir(), timeout=150)
        if r.returncode == 0:
            t = r.stdout.decode('utf-8', 'replace').strip()
            t = re.sub(r'^["\']|["\']$', '', t).strip()
            if 10 < len(t) < 700:
                return t.replace(' — ', ', ').replace('—', ',')
    except Exception as e:
        print(f'  (CLI falhou na sugestao: {str(e)[:90]})')
    nome = (c.get('nome') or '').split()[0] if c.get('nome') else ''
    ola = f'Que bom te ver por aqui, {nome}! ' if nome else 'Que bom te ver por aqui! '
    return (ola + 'A nossa equipe vai te ligar desse mesmo número.\n'
            'Me confirma se pode ser hoje ainda, ou se prefere amanhã de manhã.')


def contato(cid):
    con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True, timeout=20)
    r = con.execute('select contato_nome, contato_telefone from wa_conversas where id=?', (cid,)).fetchone()
    con.close()
    return (r[0] or '', r[1] or '') if r else ('', '')


# ------------------------------------------------------------------ 1) LIGAR AGORA

def ligar_agora(est):
    """Alarmes ja disparados (tem vendedora no estado do alarme) que ainda nao viraram tarefa."""
    out = []
    vistos = AQ._json(AQ.ESTADO, {'vistos': {}}).get('vistos', {})
    for cid, v in vistos.items():
        ref = f'ligar-agora:{cid}'
        if not v.get('vendedora') or ref in est['feitos']:
            continue
        nome, tel = contato(int(cid))
        if v.get('texto'):
            corpo = v['texto'] + f"\n\n👤 Com a {v['vendedora']}."
        else:                                          # alarme sem o texto guardado: monta o essencial
            lead, nosso = AQ.ultima_troca(int(cid))
            L = ['🚨 LIGAR AGORA 🚨', '', nome or 'Sem nome', f'📱 {tel}', '',
                 f"✅ Violação: {v.get('caso') or 'ver conversa'}", '✅ JÁ SAIU da empresa',
                 '   prescrição bienal já correndo']
            if lead:
                L += ['', f'Última fala dele ({lead[1]}):', f'   "{lead[0]}"']
            if nosso:
                L += [f'Nossa última ({nosso[1]}):', f'   "{nosso[0]}"']
            L += ['', f'Código #{cid} · card em Lead Quente.', '',
                  '⏱️ Ligar nos próximos minutos é o que fecha esse caso.', '', f"👤 Com a {v['vendedora']}."]
            corpo = '\n'.join(L)
        out.append({'ref': ref, 'origem': 'ligar-agora', 'cid': int(cid), 'nome': nome, 'tel': tel,
                    'vend': v['vendedora'],
                    'titulo': f'LIGAR AGORA: {nome or "Sem nome"} · {tel}',
                    'texto': _limpo(corpo) + '\n\nDepois da ligação, atualize o card no CRM e conclua esta tarefa.'})
    return out


# ------------------------------------------------------------------ 2) LEAD RESPONDEU

def responderam(est, enviar):
    """Resposta a regua dos quentes, percebida na hora (lead aberto) ou ja lida pela regua."""
    out = []
    fila = FQ._json(FQ.FILA, None)
    if fila is None:                                   # regua gravando a fila neste instante
        return out
    for k, c in fila.items():
        desde = c['toques'][-1]['em'] if c.get('toques') else c.get('entrou_em', '')
        ref = f'lead-respondeu:{k}:{desde}'
        if ref in est['feitos']:
            continue
        if c.get('encerrado'):
            if c.get('motivo') != 'respondeu, ligar' or not c.get('respondeu_em'):
                continue                               # cadencia acabou ou ja tem acao
            resp = c.get('resposta') or ''
        else:
            resp = FQ._respondeu_depois(c['conversa_id'], desde)
            if not resp:
                continue
            tipo = FQ.classificar_resposta(resp)
            if tipo == 'ja_tem_acao':                  # a regua tira o card no horario dela
                print(f"   [FORA] {c.get('nome') or c.get('telefone')}: disse que já tem ação")
                if enviar:
                    est['feitos'][ref] = 'ja_tem_acao'
                continue
        vend = ROTA.quem_recebe_demitido(registrar=enviar)['nome']
        sug = sugerir_resposta({**c, 'resposta': resp})
        L = ['🔥 LEAD RESPONDEU À RÉGUA DOS QUENTES: ligar hoje', '',
             f"{c.get('nome') or 'Sem nome'} · {c.get('telefone', '')}",
             f"Termômetro: {c.get('temperatura') or ''} · {c.get('situacao') or 'situação não informada'}",
             f"Caso: {c.get('violacao') or 'ver conversa'}", '',
             'Ele respondeu' + (f" ({_hora(c['respondeu_em'])})" if c.get('respondeu_em') else '') + ':',
             f'"{resp[:300]}"', '',
             '💬 Sugestão de resposta para mandar antes de ligar:', sug, '',
             f"Código #{c['conversa_id']}. A régua move o card para Lead Quente no próximo horário dela.",
             'Depois da ligação, atualize o card no CRM e conclua esta tarefa.', '', f'👤 Com a {vend}.']
        out.append({'ref': ref, 'origem': 'lead-respondeu', 'cid': c['conversa_id'],
                    'nome': c.get('nome') or '', 'tel': c.get('telefone') or '', 'vend': vend,
                    'titulo': f"LEAD RESPONDEU: {c.get('nome') or 'Sem nome'} · {c.get('telefone', '')}",
                    'texto': _limpo('\n'.join(L))})
    return out


# ------------------------------------------------------------------ gravacao

def gravar(t):
    uid, nome_sis = USUARIOS.get(t['vend'], USUARIOS['Rafaella'])
    con = sqlite3.connect(DB, timeout=20)
    con.execute('pragma busy_timeout=8000')
    try:
        r = con.execute('select id from tarefas where origem=? and origem_ref=?', (t['origem'], t['ref'])).fetchone()
        if r:
            return r[0]
        hoje, agora = date.today().isoformat(), time.time()
        cur = con.execute(
            'INSERT INTO tarefas (tipo, titulo, descricao, data, prazo_interno, prioridade, status, origem, '
            'origem_ref, criado_por, criado_em, atualizado_em, contato_nome, contato_telefone, conversa_id) '
            "VALUES (?,?,?,?,?,'urgente','aberta',?,?,?,?,?,?,?,?)",
            (TIPO, t['titulo'], t['texto'], hoje, hoje, t['origem'], t['ref'], 'Comercial (automação)',
             agora, agora, t['nome'], t['tel'], t['cid']))
        con.execute('INSERT INTO tarefa_responsaveis (tarefa_id, usuario_id, nome, importante, urgente) '
                    'VALUES (?,?,?,1,1)', (cur.lastrowid, uid, nome_sis))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def semear(est):
    """Primeira rodada: o que a Vitória ja recebeu no WhatsApp antes da troca nao vira tarefa.
    Devolve False se o estado do alarme ou a fila da regua nao puderam ser lidos agora."""
    vistos = AQ._json(AQ.ESTADO, {}).get('vistos')
    fila = FQ._json(FQ.FILA, None)
    if not vistos or not fila:
        return False
    for cid, v in vistos.items():
        if v.get('vendedora'):
            est['feitos'][f'ligar-agora:{cid}'] = 'antes da troca'
    for k, c in fila.items():
        if c.get('encerrado') and c.get('respondeu_em'):
            desde = c['toques'][-1]['em'] if c.get('toques') else c.get('entrou_em', '')
            est['feitos'][f'lead-respondeu:{k}:{desde}'] = 'antes da troca'
    return True


if __name__ == '__main__':
    enviar = '--enviar' in sys.argv
    est = _json(ESTADO, None)
    if est is None:
        est = {'inicio': datetime.now().isoformat(timespec='seconds'), 'feitos': {}}
        if not semear(est):
            print('estado do alarme ou fila da regua sendo gravados agora; tenta na proxima rodada')
            sys.exit(0)
        print(f"primeira rodada: {len(est['feitos'])} aviso(s) antigos marcados como feitos")
        if enviar:
            _salvar(ESTADO, est)
    novas = ligar_agora(est) + responderam(est, enviar)
    for t in novas:
        print('=' * 70)
        print(f"[{t['origem']}] para {t['vend']}: {t['titulo']}")
        print('-' * 70)
        print(t['texto'])
        if enviar:
            tid = gravar(t)
            est['feitos'][t['ref']] = tid
            _salvar(ESTADO, est)                       # grava a cada tarefa: queda no meio nao duplica
            print(f'tarefa #{tid} aberta para {t["vend"]}')
    if not novas:
        print('nenhum lead quente novo')
    elif not enviar:
        print('\n(simulacao: nada gravado)')
