"""Ponte entre o banco do sistema e o ASTREA (10/11/2026).

O banco do sistema continua sendo a fonte da verdade. Com SISTEMA_JURIDICO=astrea:

  ENTRA do Astrea (so leitura la):
    - carteira: processos/casos e os clientes ligados a eles  -> jur_processos / jur_clientes
      (casa pelo CNJ e pelo CPF/CNPJ antes de criar: o que ja existe aqui so ganha o vinculo)
    - andamentos de cada processo                              -> jur_andamentos (origem 'astrea')
    - agenda (prazos, tarefas, audiencias, atendimentos)      -> lida na hora, nao e copiada

  SAI para o Astrea (copia, best-effort, nunca segura a tela):
    - tarefa criada aqui    -> tarefa no Astrea (responsavel casado por e-mail/nome)
    - andamento escrito aqui -> andamento manual no processo do Astrea

Os ids do Astrea ficam em `astrea_vinculos` (nenhuma tabela existente mudou). O que falhou
ao enviar fica em `astrea_pendencias` e o robo SYNC/astrea_espelho.py tenta de novo.
"""
import logging
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger('astrea_sync')

DB = str(Path(__file__).resolve().parents[1] / 'sistema_sl.db')
PROJ = Path(__file__).resolve().parents[3]
CONTRARIA = 'PARTE CONTRÁRIA'

TIPO_ANDAMENTO = {
    'MANUALLY': 'ANDAMENTO', 'AUTOMATIC_LAWSUIT': 'MOVIMENTAÇÃO DO TRIBUNAL', 'CLIPPING': 'PUBLICAÇÃO',
    'DONE_TASK': 'TAREFA CONCLUÍDA', 'HEARING': 'AUDIÊNCIA', 'DEADLINE': 'PRAZO',
    'APPOINTMENT': 'ATENDIMENTO', 'AGENDA': 'AGENDA', 'ACTIVITY_DELETED': 'ATIVIDADE EXCLUÍDA',
}
TIPO_AGENDA = {'TASK': 'tarefa', 'DEADLINE': 'prazo', 'EVENT': 'atendimento', 'HEARING': 'audiencia'}


# ------------------------------------------------------------------ base
def escolha():
    """SISTEMA_JURIDICO do ambiente ou do config/.env (o backend nao joga o .env no os.environ)."""
    _caminho()
    import astrea_client as AC
    return (AC._env('SISTEMA_JURIDICO', 'nenhum') or 'nenhum').lower()


def ligado():
    """Integracao ativa: SISTEMA_JURIDICO=astrea e credencial no .env."""
    import astrea_client as AC
    return escolha() == 'astrea' and AC.configurado()


def _caminho():
    p = str(PROJ / 'INTEGRACOES')
    if p not in sys.path:
        sys.path.insert(0, p)


def cliente():
    _caminho()
    import astrea_client as AC
    return AC.Astrea()


def con(db=None):
    c = sqlite3.connect(db or DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    garantir(c)
    return c


def garantir(c):
    c.execute("""CREATE TABLE IF NOT EXISTS astrea_vinculos (
                   entidade TEXT NOT NULL, local_id INTEGER NOT NULL, astrea_id TEXT NOT NULL,
                   atualizado_em TEXT, PRIMARY KEY (entidade, local_id))""")
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_astrea_vinc ON astrea_vinculos (entidade, astrea_id)')
    c.execute("""CREATE TABLE IF NOT EXISTS astrea_pendencias (
                   entidade TEXT NOT NULL, local_id INTEGER NOT NULL, erro TEXT, tentativas INTEGER DEFAULT 0,
                   em TEXT, PRIMARY KEY (entidade, local_id))""")


def agora_txt():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def so_digitos(s):
    return re.sub(r'\D', '', str(s or ''))


def astrea_de(c, entidade, local_id):
    r = c.execute('SELECT astrea_id FROM astrea_vinculos WHERE entidade=? AND local_id=?',
                  (entidade, local_id)).fetchone()
    return r[0] if r else None


def local_de(c, entidade, astrea_id):
    r = c.execute('SELECT local_id FROM astrea_vinculos WHERE entidade=? AND astrea_id=?',
                  (entidade, str(astrea_id))).fetchone()
    return r[0] if r else None


def vincular(c, entidade, local_id, astrea_id):
    c.execute('INSERT OR REPLACE INTO astrea_vinculos (entidade, local_id, astrea_id, atualizado_em) '
              'VALUES (?,?,?,?)', (entidade, int(local_id), str(astrea_id), agora_txt()))


def _quando(h):
    """Data/hora de um item do Astrea -> 'YYYY-MM-DD HH:MM:SS' (hora local)."""
    v = h.get('dateStr') or h.get('date') or h.get('createdAt') or ''
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        n = float(v)
        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(n / 1000 if n > 1e11 else n))
    s = str(v)
    if 'T' in s:      # o Astrea manda '2026-11-05T13:00:00.000-03:00' (com fuso)
        try:
            d = datetime.fromisoformat(s.replace('Z', '+00:00'))
            if d.tzinfo:
                d = d.astimezone()
            return d.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
    return s.replace('T', ' ')[:19]


# ------------------------------------------------------------------ responsaveis excluidos
class FiltroErro(Exception):
    """Exclusao configurada mas nao deu para aplicar: nada e importado (falha fechada)."""


def filtro_responsaveis(a):
    """Le ASTREA_EXCLUIR_RESPONSAVEIS (e-mails ou nomes completos no Astrea, separados por virgula).
    Devolve (permitidos, excluidos): permitidos=None quando nao ha exclusao; senao a lista de ids
    dos usuarios ativos MENOS os excluidos, para o filtro do proprio Astrea. Se algum nome/e-mail
    configurado nao for achado, levanta FiltroErro: melhor nao importar nada do que importar a mais."""
    _caminho()
    import astrea_client as AC
    cfg = [x.strip() for x in AC._env('ASTREA_EXCLUIR_RESPONSAVEIS').split(',') if x.strip()]
    if not cfg:
        return None, set()
    import unicodedata

    def norm(s):
        s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
        return re.sub(r'[^a-z ]', '', s).strip()
    try:
        usuarios = a.usuarios()
    except Exception as e:
        raise FiltroErro('nao deu para ler os usuarios do Astrea para aplicar a exclusao: %s' % e)
    todos, excl = {}, set()
    for u in usuarios:
        uid = str(u.get('id') or u.get('userId') or '')
        if uid:
            todos[uid] = u
    for item in cfg:
        alvo_mail, alvo_nome = item.lower(), norm(item)
        achou = [uid for uid, u in todos.items()
                 if (u.get('email') or '').strip().lower() == alvo_mail or norm(u.get('name')) == alvo_nome]
        if not achou:
            raise FiltroErro('responsavel excluido "%s" nao foi achado entre os usuarios do Astrea: '
                             'importacao suspensa (confira ASTREA_EXCLUIR_RESPONSAVEIS)' % item)
        excl.update(achou)
    return sorted(set(todos) - excl), excl


def _responsavel_do_caso(ficha):
    """Id do responsavel na ficha do caso (getCaseById), se vier; senao None."""
    for k in ('responsible', 'responsibleId', 'responsibleUser', 'owner'):
        v = ficha.get(k)
        if isinstance(v, dict):
            v = v.get('id') or v.get('userId')
        if v:
            return str(v)
    return None


# ------------------------------------------------------------------ carteira (entra)
def _cliente_local(c, a, contato, cache):
    """Cliente do Astrea -> id em jur_clientes (vinculo, depois CPF/CNPJ, depois nome; senao cria)."""
    aid = str(contato.get('id') or contato.get('customerId') or '')
    if not aid:
        return None
    lid = local_de(c, 'cliente', aid)
    if lid:
        return lid
    try:
        d = cache.get(aid) or a.cliente(aid)
    except Exception as e:
        log.warning('astrea: ficha do contato %s: %s', aid, e)
        d = {}
    cache[aid] = d
    nome = (d.get('name') or contato.get('name') or '').strip().upper()
    doc = d.get('taxDocumentNumber') or ''
    alvo = so_digitos(doc)
    achado = None
    if alvo:
        for r in c.execute("SELECT id, documento FROM jur_clientes WHERE documento != ''"):
            if so_digitos(r['documento']) == alvo:
                achado = r['id']
                break
    if not achado and nome:
        r = c.execute('SELECT id FROM jur_clientes WHERE UPPER(TRIM(nome))=?', (nome,)).fetchone()
        achado = r['id'] if r else None
    if not achado:
        tel = [t.get('number') or t.get('phone') or '' for t in (d.get('telephones') or [])]
        mail = [e.get('address') or e.get('email') or '' for e in (d.get('emails') or [])]
        end = (d.get('addresses') or [{}])[0] or {}
        agora = agora_txt()
        linha = dict(nome=nome or '(SEM NOME)', documento=doc or '', email=(mail[0] if mail else '')[:200],
                     telefone=(tel[0] if tel else '')[:40], celular=(tel[1] if len(tel) > 1 else '')[:40],
                     origem='ASTREA', nascimento=str(d.get('birthDate') or '')[:20], estado_civil='',
                     profissao=(d.get('jobAndCompany') or '')[:120],
                     logradouro=(end.get('street') or end.get('display') or '')[:250],
                     cidade=(end.get('city') or '')[:120], estado=(end.get('state') or '')[:40],
                     cep=(end.get('zipCode') or end.get('postalCode') or '')[:20], notas='',
                     criado_em=agora, atualizado_em=agora)
        achado = c.execute('INSERT INTO jur_clientes (%s) VALUES (%s)' % (', '.join(linha), ', '.join('?' * len(linha))),
                           list(linha.values())).lastrowid
    vincular(c, 'cliente', achado, aid)
    return achado


def importar_carteira(c=None, a=None, so_ativos=False, responsavel_padrao=None, vistos=None):
    """Traz processos/casos do Astrea. Idempotente: casa por vinculo e por CNJ antes de criar.
    Processos de quem esta em ASTREA_EXCLUIR_RESPONSAVEIS nunca entram (ver filtro_responsaveis).
    `vistos` (set opcional) recebe os ids do Astrea que passaram no filtro nesta rodada.
    Devolve {'processos_novos', 'processos_vinculados', 'clientes_novos', 'encerrados', 'lidos', 'excluidos'}."""
    fechar = c is None
    c = c or con()
    a = a or cliente()
    _caminho()
    import astrea_client as AC
    resp = responsavel_padrao or AC._env('ASTREA_RESPONSAVEL_PADRAO') or 'Vitória'
    out = dict(processos_novos=0, processos_vinculados=0, clientes_novos=0, encerrados=0, lidos=0, excluidos=0)
    cache = {}
    try:
        permitidos, excluidos = filtro_responsaveis(a)
        por_cnj = {}
        for r in c.execute("SELECT id, numero FROM jur_processos WHERE numero != ''"):
            por_cnj.setdefault(so_digitos(r['numero']), r['id'])
        antes_cli = c.execute('SELECT COUNT(*) FROM jur_clientes').fetchone()[0]
        for caso in a.processos(status='Active' if so_ativos else None, usuarios=permitidos):
            out['lidos'] += 1
            aid = str(caso.get('id'))
            ativo = caso.get('active') is not False
            lid = local_de(c, 'processo', aid)
            if excluidos and not lid:
                # 2a camada: confere o responsavel na ficha antes de trazer um processo novo
                try:
                    dono = _responsavel_do_caso(a.caso(aid) or {})
                except Exception as e:
                    log.warning('astrea: ficha do caso %s (conferencia do responsavel): %s', aid, e)
                    out['excluidos'] += 1
                    continue
                if dono in excluidos:
                    out['excluidos'] += 1
                    continue
            if vistos is not None:
                vistos.add(aid)
            if not lid:
                lid = por_cnj.get(so_digitos(caso.get('number'))) if so_digitos(caso.get('number')) else None
                if lid:
                    out['processos_vinculados'] += 1
            if lid:
                vincular(c, 'processo', lid, aid)
                if not ativo:
                    n = c.execute("UPDATE jur_processos SET encerrado=1, status_encerramento='ARQUIVADO NO ASTREA', "
                                  'atualizado_em=? WHERE id=? AND encerrado=0', (agora_txt(), lid)).rowcount
                    out['encerrados'] += n
                continue
            eh_proc = 'LAWSUIT' in str(caso.get('type') or '').upper()
            agora = agora_txt()
            linha = dict(numero=(caso.get('number') or '')[:60] if eh_proc else '', protocolo='',
                         area='', tipo=(caso.get('lawsuitType') or ('' if eh_proc else 'CASO'))[:250],
                         fase='', etapa='', responsavel=resp, encerrado=0 if ativo else 1,
                         status_encerramento='' if ativo else 'ARQUIVADO NO ASTREA',
                         data_processo='', pasta=(caso.get('court') or '')[:120],
                         valor_expectativa=0.0, valor_honorarios=0.0, contingencia=0.0,
                         notas=('Importado do Astrea: %s' % (caso.get('title') or '')).strip(),
                         criado_em=agora, atualizado_em=agora)
            lid = c.execute('INSERT INTO jur_processos (%s) VALUES (%s)' % (', '.join(linha), ', '.join('?' * len(linha))),
                            list(linha.values())).lastrowid
            vincular(c, 'processo', lid, aid)
            if linha['numero']:
                por_cnj[so_digitos(linha['numero'])] = lid
            out['processos_novos'] += 1
            for cust in (caso.get('customers') or []):
                cid = _cliente_local(c, a, cust, cache)
                if cid:
                    cr = c.execute('SELECT nome, documento FROM jur_clientes WHERE id=?', (cid,)).fetchone()
                    c.execute('INSERT INTO jur_processo_partes (processo_id, cliente_id, nome, documento, papel) '
                              'VALUES (?,?,?,?,?)', (lid, cid, cr['nome'], cr['documento'] or '', 'CLIENTE'))
            if out['lidos'] % 50 == 0:
                c.commit()
        c.commit()
        out['clientes_novos'] = c.execute('SELECT COUNT(*) FROM jur_clientes').fetchone()[0] - antes_cli
        return out
    finally:
        if fechar:
            c.close()


# ------------------------------------------------------------------ andamentos (entra)
def caso_do_processo(c, processo_id, a=None, buscar=True):
    """Id do caso no Astrea para um processo local (vinculo; senao procura pelo CNJ e vincula)."""
    aid = astrea_de(c, 'processo', processo_id)
    if aid or not buscar:
        return aid
    r = c.execute('SELECT numero FROM jur_processos WHERE id=?', (processo_id,)).fetchone()
    if not r or not so_digitos(r['numero']):
        return None
    a = a or cliente()
    permitidos, _ = filtro_responsaveis(a)
    caso = a.buscar_processo(r['numero'], usuarios=permitidos)
    if not caso:
        return None
    vincular(c, 'processo', processo_id, caso['id'])
    c.commit()
    return str(caso['id'])


def sincronizar_andamentos(c, processo_id, a=None):
    """Le os andamentos do Astrea do processo e grava os novos. (novos, lidos) ou None se nao deu."""
    a = a or cliente()
    try:
        caso = caso_do_processo(c, processo_id, a)
        if not caso:
            return None
        itens = a.andamentos(caso, limite=500)
    except Exception as e:
        log.warning('astrea: andamentos do processo %s: %s', processo_id, e)
        return None
    num = (c.execute('SELECT numero FROM jur_processos WHERE id=?', (processo_id,)).fetchone() or [''])[0]
    novos = 0
    for h in itens:
        hid = str(h.get('id') or '')
        if not hid or local_de(c, 'andamento', hid):     # foi escrito aqui e enviado: ja esta na linha
            continue
        cur = c.execute(
            'INSERT OR IGNORE INTO jur_andamentos (processo_id, processo_numero, lawsuit_id, tipo, texto, autor, '
            "responsavel, criado_em, origem, chave) VALUES (?,?,?,?,?,?,?,?,'astrea',?)",
            (processo_id, num or None, int(caso), TIPO_ANDAMENTO.get(h.get('type'), h.get('type') or 'ANDAMENTO'),
             (h.get('description') or h.get('descriptionTranslation') or '').strip() or None,
             (h.get('responsibleName') or '').strip() or None, (h.get('responsibleName') or '').strip() or None,
             _quando(h), 'astrea:' + hid))
        novos += cur.rowcount
    c.execute('INSERT OR REPLACE INTO jur_andamentos_sync (processo_id, lawsuit_id, sincronizado_em, itens) '
              'VALUES (?,?,?,?)', (processo_id, int(caso), agora_txt(), len(itens)))
    c.commit()
    return novos, len(itens)


# ------------------------------------------------------------------ envio (sai)
def _responsavel_astrea(c, a, usuario_ids=(), nomes=(), _cache={}):
    """Primeiro responsavel local que casa com um usuario do Astrea (e-mail, nome, primeiro nome)."""
    if 'mapa' not in _cache or time.time() - _cache.get('em', 0) > 3600:
        _caminho()
        import astrea_client as AC
        _cache['mapa'], _cache['norm'] = AC.mapa_usuarios(a)
        _cache['em'] = time.time()
    mapa, norm = _cache['mapa'], _cache['norm']
    cand = []
    for uid in usuario_ids:
        r = c.execute('SELECT email, nome FROM usuarios WHERE id=?', (uid,)).fetchone()
        if r:
            cand += [(r['email'] or '').lower(), norm(r['nome'])]
    cand += [norm(n) for n in nomes if n]
    for k in cand:
        if k and (mapa.get(k) or mapa.get(k.split(' ')[0])):
            return mapa.get(k) or mapa.get(k.split(' ')[0])
    return None


def _pendencia(c, entidade, local_id, erro):
    c.execute('INSERT INTO astrea_pendencias (entidade, local_id, erro, tentativas, em) VALUES (?,?,?,1,?) '
              'ON CONFLICT(entidade, local_id) DO UPDATE SET erro=excluded.erro, tentativas=tentativas+1, em=excluded.em',
              (entidade, local_id, str(erro)[:500], agora_txt()))
    c.commit()


def _resolvida(c, entidade, local_id):
    c.execute('DELETE FROM astrea_pendencias WHERE entidade=? AND local_id=?', (entidade, local_id))


def enviar_andamento(andamento_id, c=None, a=None):
    """Copia um andamento escrito no sistema para o processo no Astrea. Devolve o id la (ou None)."""
    fechar = c is None
    c = c or con()
    try:
        if astrea_de(c, 'andamento', andamento_id):
            return astrea_de(c, 'andamento', andamento_id)
        r = c.execute('SELECT * FROM jur_andamentos WHERE id=? AND removido=0', (andamento_id,)).fetchone()
        if not r or r['origem'] in ('astrea', 'advbox'):
            return None
        a = a or cliente()
        try:
            caso = caso_do_processo(c, r['processo_id'], a)
            if not caso:
                _pendencia(c, 'andamento', andamento_id, 'processo nao achado no Astrea')
                return None
            texto = '%s\n\n(%s, pelo sistema do escritorio)' % (r['texto'], r['autor'] or 'equipe')
            resp = _responsavel_astrea(c, a, [r['autor_id']] if r['autor_id'] else [], [r['autor']])
            num = (c.execute('SELECT numero FROM jur_processos WHERE id=?', (r['processo_id'],)).fetchone() or [''])[0]
            feito = a.lancar_andamento(caso, texto, r['criado_em'], resp, instancia=1 if num else None)
            hid = (feito or {}).get('id')
            if hid:
                vincular(c, 'andamento', andamento_id, hid)
            _resolvida(c, 'andamento', andamento_id)
            c.commit()
            return hid
        except Exception as e:
            log.warning('astrea: envio do andamento %s: %s', andamento_id, e)
            _pendencia(c, 'andamento', andamento_id, e)
            return None
    finally:
        if fechar:
            c.close()


def enviar_tarefa(tarefa_id, c=None, a=None):
    """Copia uma tarefa do sistema para o Astrea (com prazo e responsavel). Devolve o id la (ou None)."""
    fechar = c is None
    c = c or con()
    try:
        if astrea_de(c, 'tarefa', tarefa_id):
            return astrea_de(c, 'tarefa', tarefa_id)
        t = c.execute('SELECT * FROM tarefas WHERE id=?', (tarefa_id,)).fetchone()
        if not t or (t['origem'] or '') in ('advbox', 'astrea', 'comentario') or t['status'] == 'cancelada':
            return None
        a = a or cliente()
        try:
            caso = None
            if t['processo_numero']:
                p = c.execute('SELECT id FROM jur_processos WHERE TRIM(numero)=?', (t['processo_numero'].strip(),)).fetchone()
                caso = caso_do_processo(c, p['id'], a) if p else None
                if not caso:
                    achado = a.buscar_processo(t['processo_numero'], usuarios=filtro_responsaveis(a)[0])
                    caso = str(achado['id']) if achado else None
            rs = c.execute('SELECT usuario_id, nome FROM tarefa_responsaveis WHERE tarefa_id=?', (tarefa_id,)).fetchall()
            resp = _responsavel_astrea(c, a, [x['usuario_id'] for x in rs if x['usuario_id']], [x['nome'] for x in rs])
            partes = ['[%s] %s' % (t['tipo'], t['titulo'])]
            if t['cliente']:
                partes.append('Cliente: %s' % t['cliente'])
            if t['prazo_fatal']:
                partes.append('Prazo fatal: %s' % t['prazo_fatal'])
            if t['descricao']:
                partes.append(t['descricao'][:3000])
            if rs:
                partes.append('Responsaveis no sistema: %s' % ', '.join(x['nome'] or '' for x in rs))
            prazo = t['prazo_interno'] or t['data'] or t['prazo_fatal']
            prio = {'urgente': 2, 'importante': 1}.get(t['prioridade'] or '', None)
            feito = a.criar_tarefa('\n'.join(partes), resp, prazo=prazo, caso_id=caso, prioridade=prio)
            info = (feito or {}).get('taskInfoDTO') or feito or {}
            aid = info.get('id') or (feito or {}).get('id')
            if aid:
                vincular(c, 'tarefa', tarefa_id, aid)
            _resolvida(c, 'tarefa', tarefa_id)
            c.commit()
            return aid
        except Exception as e:
            log.warning('astrea: envio da tarefa %s: %s', tarefa_id, e)
            _pendencia(c, 'tarefa', tarefa_id, e)
            return None
    finally:
        if fechar:
            c.close()


def em_segundo_plano(funcao, *args):
    """Dispara o envio sem segurar a resposta da tela. Nao faz nada se a integracao estiver desligada."""
    try:
        if not ligado():
            return
    except Exception:
        return
    threading.Thread(target=_seguro, args=(funcao,) + args, daemon=True).start()


def _seguro(funcao, *args):
    try:
        funcao(*args)
    except Exception as e:
        log.warning('astrea: %s%s falhou: %s', funcao.__name__, args, e)


def reenviar_pendencias(c=None, a=None, maximo_tentativas=10):
    """Tenta de novo o que nao subiu. Devolve {'ok': n, 'falhou': n}."""
    fechar = c is None
    c = c or con()
    a = a or cliente()
    out = {'ok': 0, 'falhou': 0}
    try:
        for p in c.execute('SELECT entidade, local_id FROM astrea_pendencias WHERE tentativas < ?',
                           (maximo_tentativas,)).fetchall():
            f = enviar_tarefa if p['entidade'] == 'tarefa' else enviar_andamento
            out['ok' if f(p['local_id'], c, a) else 'falhou'] += 1
        return out
    finally:
        if fechar:
            c.close()


# ------------------------------------------------------------------ agenda (le na hora)
def _dia(v):
    """'20261112' ou '2026-11-12...' -> '2026-11-12' (o Astrea usa os dois na agenda)."""
    s = str(v or '')
    if len(s) >= 8 and s[:8].isdigit():
        return '%s-%s-%s' % (s[:4], s[4:6], s[6:8])
    return s[:10]


def agenda(de, ate, tipos=None, a=None):
    """Agenda do Astrea no formato do sistema: [{tipo, titulo, data, hora_inicio, hora_fim, processo,...}]."""
    a = a or cliente()
    tipos = tipos or ('prazo', 'tarefa', 'atendimento', 'audiencia')
    permitidos, excluidos = filtro_responsaveis(a)
    out = []
    for x in a.agenda(de, ate, tipos=tipos, responsaveis=permitidos):
        if excluidos and (str(x.get('responsibleId') or '') in excluidos
                          or str(x.get('ownerId') or '') in excluidos):
            continue
        out.append({
            'astrea_id': str(x.get('id') or ''), 'tipo': TIPO_AGENDA.get(x.get('type'), (x.get('type') or '').lower()),
            'titulo': x.get('titleWithName') or x.get('title') or '', 'data': _dia(x.get('dateStart')),
            'data_fim': _dia(x.get('dateEnd')), 'hora_inicio': x.get('timeStart') or '',
            'hora_fim': x.get('timeEnd') or '', 'dia_todo': bool(x.get('allDay')),
            'processo': x.get('lawsuitNumber') or '', 'caso': x.get('caseTitle') or '',
            'astrea_caso_id': str(x.get('caseId') or '') or None,
            'status': 'concluida' if x.get('done') or x.get('status') == 'DONE' else 'aberta',
            'local': ' - '.join(v for v in (x.get('courthouse') or x.get('courtName'), x.get('courthouseRoom'),
                                            x.get('address')) if v),
            'obs': x.get('comments') or '', 'responsavel_astrea_id': str(x.get('responsibleId') or '') or None,
        })
    out.sort(key=lambda e: (e['data'], e['hora_inicio'] or ''))
    return out
