# -*- coding: utf-8 -*-
"""Cliente do ASTREA (Aurum) pela API interna do app web.

O Astrea nao tem API publica. Este modulo fala com as mesmas rotas que o app
em astrea.net.br usa, so com `requests` (sem navegador):

    login   POST {DOMINIO}/api/v2/session/login {username, password}
            -> userInfo (id, tenantId, session). `session` vira "Authorization: Bearer".
    REST    {DOMINIO}/api/v2/...          (case/query, contact/all, historical/..., calendar-pro/...)
    Endpts  {DOMINIO}/_ah/api/<api>/v1/... (workspace, folders, histories, users)
            contrato publico em /_ah/api/discovery/v1/apis/<api>/v1/rest

Regras que valem para nao derrubar a conta:
  * USUARIO DEDICADO para a integracao (ex.: integracao@escritorio). O Astrea
    mantem UMA sessao por usuario: se uma pessoa entrar com o mesmo login no
    navegador, uma derruba a outra.
  * Sem 2 fatores nesse usuario (o login por senha devolve 403 se pedir codigo).
  * A sessao fica em config/astrea_sessao.json e e reaproveitada por todos os
    processos (API, robos). Login novo so com sessao invalida, com trava de
    arquivo e no maximo ASTREA_LOGINS_HORA por hora (tempestade de login e o que
    o Astrea trata como uso indevido).

.env:
    SISTEMA_JURIDICO=astrea
    ASTREA_USUARIO=integracao@...      (e-mail de login)
    ASTREA_SENHA=...
    ASTREA_DOMINIO=https://app.astrea.net.br   (opcional)
    ASTREA_LOGINS_HORA=6                        (opcional)

Teste rapido, so leitura:  python INTEGRACOES/astrea_client.py diagnostico
"""
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

log = logging.getLogger('astrea')

PROJ = Path(__file__).resolve().parent.parent
ARQ_SESSAO = PROJ / 'config' / 'astrea_sessao.json'
ARQ_TRAVA = PROJ / 'config' / 'astrea_login.lock'
UA = 'Mozilla/5.0 (X11; Linux x86_64) SistemaEscritorio/1.0'


class AstreaErro(Exception):
    """Erro vindo do Astrea (status HTTP + mensagem)."""

    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


class AstreaLoginErro(AstreaErro):
    """Login recusado (senha, 2 fatores, conta) ou bloqueado pelo limite local."""


def _env(nome, padrao=''):
    v = os.getenv(nome)
    if v is None:
        _carregar_env()
        v = os.getenv(nome)
    return (v if v is not None else padrao).strip()


_env_lido = False


def _carregar_env():
    """Le config/.env uma vez (sem sobrescrever o que ja esta no ambiente)."""
    global _env_lido
    if _env_lido:
        return
    _env_lido = True
    arq = PROJ / 'config' / '.env'
    try:
        for linha in arq.read_text(encoding='utf-8').splitlines():
            linha = linha.strip()
            if not linha or linha.startswith('#') or '=' not in linha:
                continue
            k, v = linha.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def so_digitos(s):
    return re.sub(r'\D', '', str(s or ''))


def configurado():
    return bool(_env('ASTREA_USUARIO') and _env('ASTREA_SENHA'))


# ------------------------------------------------------------------ sessao
class _Trava:
    """Trava de arquivo entre processos (so para o login). Trava velha (>2 min) e ignorada."""

    def __init__(self, arq, espera=90):
        self.arq, self.espera, self.fd = arq, espera, None

    def __enter__(self):
        fim = time.time() + self.espera
        self.arq.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.fd = os.open(str(self.arq), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - self.arq.stat().st_mtime > 120:
                        self.arq.unlink()
                        continue
                except OSError:
                    continue
                if time.time() > fim:
                    raise AstreaLoginErro('Outro processo esta fazendo login no Astrea; tente de novo.')
                time.sleep(1)

    def __exit__(self, *a):
        try:
            os.close(self.fd)
            self.arq.unlink()
        except OSError:
            pass


def _ler_sessao():
    try:
        return json.loads(ARQ_SESSAO.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _gravar_sessao(d):
    ARQ_SESSAO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ARQ_SESSAO.with_suffix('.tmp')
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, ARQ_SESSAO)
    try:
        os.chmod(ARQ_SESSAO, 0o600)
    except OSError:
        pass


class Astrea:
    """Uma conexao com o Astrea. Barata de criar: a sessao vem do arquivo compartilhado."""

    def __init__(self, usuario=None, senha=None, dominio=None, timeout=60):
        import requests
        self.usuario = usuario or _env('ASTREA_USUARIO')
        self.senha = senha or _env('ASTREA_SENHA')
        self.dominio = (dominio or _env('ASTREA_DOMINIO', 'https://app.astrea.net.br')).rstrip('/')
        self.timeout = timeout
        self.http = requests.Session()
        self.http.headers.update({'User-Agent': UA, 'Accept': 'application/json',
                                  'Origin': 'https://astrea.net.br', 'Referer': 'https://astrea.net.br/'})
        self.info = {}
        s = _ler_sessao()
        if s.get('session') and s.get('usuario') == self.usuario:
            self.info = s

    # ---- login
    @property
    def user_id(self):
        self._garantir_sessao()
        return str(self.info.get('id'))

    @property
    def tenant_id(self):
        self._garantir_sessao()
        return str(self.info.get('tenantId'))

    def _garantir_sessao(self):
        if not self.info.get('session'):
            self.login()

    def login(self, sessao_velha=None):
        """Login com trava e limite por hora. Se outro processo ja renovou, so reaproveita."""
        if not (self.usuario and self.senha):
            raise AstreaLoginErro('Faltam ASTREA_USUARIO e ASTREA_SENHA no config/.env')
        with _Trava(ARQ_TRAVA):
            s = _ler_sessao()
            if s.get('session') and s.get('usuario') == self.usuario and s.get('session') != sessao_velha:
                self.info = s
                return self.info
            limite = int(_env('ASTREA_LOGINS_HORA', '6') or 6)
            recentes = [t for t in s.get('logins', []) if time.time() - t < 3600]
            if len(recentes) >= limite:
                raise AstreaLoginErro('Limite de %d logins/hora no Astrea atingido: outra sessao pode estar usando '
                                      'o mesmo usuario (o Astrea aceita 1 por usuario). Use um usuario so da '
                                      'integracao.' % limite)
            r = self.http.post(self.dominio + '/api/v2/session/login', timeout=self.timeout,
                               json={'username': self.usuario, 'password': self.senha})
            try:
                d = r.json()
            except ValueError:
                d = {}
            err = (d or {}).get('error') if isinstance(d, dict) else None
            if r.status_code >= 400 or err or not (d or {}).get('session'):
                err = err or {}
                code = str(err.get('code') or '')
                msg = err.get('errorMessage') or err.get('message') or r.text[:200]
                if r.status_code == 403 or 'TWO_FACTOR' in code.upper():
                    msg = ('o Astrea pediu verificacao em 2 fatores para este usuario. Desligue o 2FA do usuario '
                           'da integracao (ou peca ao admin para isentar). Detalhe: %s' % msg)
                s['logins'] = recentes + [time.time()]
                _gravar_sessao(dict(s, session=None))
                raise AstreaLoginErro('Login no Astrea recusado (%s): %s' % (r.status_code, msg), r.status_code)
            self.info = {'usuario': self.usuario, 'session': d['session'], 'id': d.get('id'),
                         'tenantId': d.get('tenantId'), 'nome': d.get('name'), 'email': d.get('email'),
                         'logins': recentes + [time.time()], 'em': datetime.now().isoformat(timespec='seconds')}
            _gravar_sessao(self.info)
            log.info('astrea: login ok (usuario %s, tenant %s)', self.info.get('id'), self.info.get('tenantId'))
            return self.info

    # ---- chamadas
    def _req(self, metodo, url, params=None, corpo=None, _de_novo=True):
        self._garantir_sessao()
        h = {'Authorization': 'Bearer ' + self.info['session']}
        if corpo is not None:
            h['Content-Type'] = 'application/json'
        for tentativa in range(3):
            try:
                r = self.http.request(metodo, url, params=params, headers=h, timeout=self.timeout,
                                      data=None if corpo is None else json.dumps(corpo, default=str))
            except Exception as e:  # rede
                if tentativa == 2:
                    raise AstreaErro('Astrea fora do ar: %s' % e)
                time.sleep(3 * (tentativa + 1))
                continue
            if r.status_code in (429, 502, 503, 504) and tentativa < 2:
                time.sleep(5 * (tentativa + 1))
                continue
            break
        texto = r.text or ''
        expirou = r.status_code == 401 or 'INVALID_SESSION' in texto or 'non-existent user session' in texto
        if expirou and _de_novo:
            self.login(sessao_velha=self.info.get('session'))
            return self._req(metodo, url, params, corpo, _de_novo=False)
        if r.status_code >= 400:
            raise AstreaErro('%s %s -> %s: %s' % (metodo, url.replace(self.dominio, ''), r.status_code,
                                                  texto[:300]), r.status_code)
        if not texto.strip():
            return {}
        try:
            return r.json()
        except ValueError:
            return {'_texto': texto}

    def api(self, metodo, rota, corpo=None, params=None):
        """REST /api/v2."""
        return self._req(metodo, self.dominio + '/api/v2' + rota, params, corpo)

    def endpoint(self, api, metodo_http, caminho, params=None, corpo=None):
        """Cloud Endpoints /_ah/api/<api>/v1/<caminho>."""
        return self._req(metodo_http, '%s/_ah/api/%s/v1/%s' % (self.dominio, api, caminho), params, corpo)

    # ================================================================ LEITURA
    def usuarios(self):
        """Usuarios ativos do escritorio: [{id, name, email, ...}]."""
        d = self.endpoint('users', 'GET', 'getActiveUsersSimple', {'tenantId': self.tenant_id})
        return d.get('items') or d.get('users') or (d if isinstance(d, list) else [])

    def processos(self, status='Active', tipos=None, numeros=None, por_pagina=100, maximo=None, usuarios=None):
        """Gera os casos/processos (case/query, paginado por cursor).
        status: 'Active' | 'Inactive' | None (todos). tipos: ['CTE_LAWSUIT'], ['CTE_CASE'] ou [] (todos).
        usuarios: ids de responsaveis (filtro do proprio Astrea); None = sem filtro."""
        if usuarios is not None and not usuarios:
            return                      # filtro pedido, mas ninguem permitido: nao traz nada
        uid = int(self.user_id)
        dto = {'contacts': [], 'lawsuitTypes': [], 'titles': [], 'folders': [], 'courts': [],
               'stakeholderRoles': [], 'divisionNames': [], 'numbers': list(numeros or []), 'userId': uid,
               'order': '-lastMovement', 'types': list(tipos or []), 'instances': [], 'status': status,
               'tagIds': [], 'treeView': False, 'onlyImportant': None, 'notUpdated': None,
               'isFromContactScreen': False, 'treeMode': False, 'historiesMovement': None,
               'createddate': None, 'shareddate': None, 'endeddate': None,
               'users': [int(u) for u in (usuarios or [])], 'team': None}
        cursor, n = '', 0
        while True:
            d = self.api('POST', '/case/query', {'userId': uid, 'limit': por_pagina, 'queryCursor': cursor,
                                                 'queryDTO': dto, 'currentOrder': '-lastMovement'})
            casos = d.get('cases') or []
            nomes = d.get('userNames') or {}
            for c in casos:
                if nomes:
                    c.setdefault('_userNames', nomes)
                yield c
                n += 1
                if maximo and n >= maximo:
                    return
            cursor = d.get('cursor')
            if len(casos) < por_pagina or not cursor:
                return

    def buscar_processo(self, numero, usuarios=None):
        """Processo pelo numero CNJ (compara so os digitos). None se nao achar.
        usuarios: so entre os processos desses responsaveis (ver processos())."""
        alvo = so_digitos(numero)
        if not alvo:
            return None
        for status in ('Active', None):
            for c in self.processos(status=status, numeros=[numero], maximo=50, usuarios=usuarios):
                if so_digitos(c.get('number')) == alvo:
                    return c
        return None

    def caso(self, caso_id):
        """Ficha completa do caso/processo (folders.getCaseById)."""
        return self.endpoint('folders', 'GET', 'getCaseById', {'id': caso_id, 'userId': self.user_id})

    def clientes(self, texto='', por_pagina=100, maximo=None):
        """Gera os contatos (contact/all, paginado por pagina)."""
        pagina, n = 0, 0
        while True:
            dto = {'type': '', 'text': texto or '', 'order': 'nameUpperCase', 'selectedTagsIds': [],
                   'startsWith': [], 'onlyWithEmail': False, 'searchInCompany': False,
                   'customerNotificationTypeFilter': 'ALL',
                   'customerNotification': ['CLIPPING', 'AUTOMATIC_HISTORIES'],
                   'customerNotificationArtificialIntelligenceFilter': 'ALL', 'birthMonth': 0, 'state': ''}
            d = self.api('POST', '/contact/all', {'queryDTO': dto, 'page': pagina, 'limit': por_pagina})
            itens = d.get('contacts') or []
            for c in itens:
                yield c
                n += 1
                if maximo and n >= maximo:
                    return
            if len(itens) < por_pagina:
                return
            pagina += 1

    def cliente(self, contato_id):
        """Ficha do contato (CPF/CNPJ em taxDocumentNumber, telefones, e-mails, enderecos)."""
        return self.api('GET', '/contact/%s/details' % contato_id)

    def andamentos(self, caso_id=None, desde=None, ate=None, tipo='ALL', limite=200):
        """Andamentos (historicos) de um caso, ou de todos se caso_id=None. Mais novos primeiro."""
        corpo = {'type': tipo, 'instance': None, 'beginDate': desde, 'endDate': ate,
                 'caseId': str(caso_id) if caso_id else None, 'description': None, 'tagIds': [],
                 'order': '-date', 'limit': limite, 'currentUserId': self.user_id, 'cursor': ''}
        d = self.api('POST', '/historical/query-history', corpo)
        return d.get('historicals') or []

    def agenda(self, de, ate, tipos=('prazo', 'tarefa', 'atendimento', 'audiencia'), status='ALL',
               responsaveis=None):
        """Agenda do periodo (calendar-pro/complete). de/ate: 'YYYY-MM-DD'. status: ALL|IN_PROGRESS|DONE.
        responsaveis: ids de usuarios. O Astrea devolve VAZIO sem ninguem selecionado (conferido em
        10/11/2026), entao None = todos os usuarios ativos."""
        if responsaveis is None:
            responsaveis = [u.get('id') for u in self.usuarios() if u.get('id')]
        if not responsaveis:
            return []
        de, ate = str(de)[:10], str(ate)[:10]
        fim = (date.fromisoformat(ate) + timedelta(days=1)).isoformat()
        flags = {'deadlineSelected': 'prazo' in tipos, 'taskSelected': 'tarefa' in tipos,
                 'appointmentSelected': 'atendimento' in tipos, 'hearingSelected': 'audiencia' in tipos}
        uid = self.user_id
        corpo = {'from': de.replace('-', ''), 'to': ate.replace('-', ''), 'userId': uid,
                 'cursors': {'deadlineCursor': '', 'eventCursor': '', 'hearingCursor': '', 'taskCursor': ''},
                 'query': dict({'cases': [], 'customers': [], 'tasks': [], 'appointments': [], 'deadlines': [],
                                'hearings': []}, **flags,
                               status=status,
                               userFilter={'selected': [str(x) for x in (responsaveis or [])], 'type': 'CF_ALL',
                                           'users': []},
                               tagIds=[], date=de + 'T03:00:00.000Z', start=de + 'T03:00:00.000Z',
                               end=fim + 'T02:59:59.999Z', dateFilterPeriod='MANUAL', userId=uid)}
        return self.api('POST', '/calendar-pro/complete', corpo).get('activities') or []

    def listas_de_tarefas(self):
        d = self.endpoint('workspace', 'GET', 'getAllTaskLists', {'userId': self.user_id})
        if isinstance(d, list):
            return d
        return d.get('items') or d.get('taskLists') or []

    def tarefas_do_caso(self, caso_id):
        d = self.endpoint('workspace', 'POST', 'getTasksByCase', {'caseId': caso_id, 'userId': self.user_id})
        return d.get('items') or d.get('tasks') or (d if isinstance(d, list) else [])

    # ================================================================ ESCRITA
    def criar_tarefa(self, descricao, responsavel_id=None, prazo=None, caso_id=None, prioridade=None,
                     lista_id=None):
        """Cria tarefa (workspace.saveTaskWithList). prazo 'YYYY-MM-DD'. Devolve o TaskDTO do Astrea."""
        uid = self.user_id
        if not lista_id:
            listas = self.listas_de_tarefas()
            atual = next((x for x in listas if x.get('current')), None) or (listas[0] if listas else None)
            if not atual:
                raise AstreaErro('Nenhuma lista de tarefas no Astrea para o usuario da integracao')
            lista_id = atual.get('id') or atual.get('taskListId')
        resp = str(responsavel_id or uid)
        info = {'description': (descricao or '')[:5000], 'responsibleId': resp, 'ownerId': uid,
                'createDate': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')}
        if prazo:
            info['dueDate'] = str(prazo)[:10]
        if prioridade is not None:
            info['priority'] = int(prioridade)
        if caso_id:
            info['caseId'] = str(caso_id)
        corpo = {'taskInfoDTO': info, 'idCurrentTaskList': str(lista_id), 'idUser': uid, 'responsibleId': resp}
        return self.endpoint('workspace', 'POST', 'saveTaskWithList', corpo=corpo)

    def lancar_andamento(self, caso_id, texto, quando=None, responsavel_id=None, instancia=1):
        """Andamento manual no caso/processo (histories.saveHistoricalByCase), igual ao botao do app.
        instancia: 1 para processo, None para caso (sem instancia)."""
        quando = quando or datetime.now()
        if isinstance(quando, str):
            quando = datetime.fromisoformat(quando[:19]) if len(quando) > 10 else datetime.fromisoformat(quando + 'T09:00:00')
        corpo = {'instanceNumber': instancia, 'dateStr': quando.strftime('%Y-%m-%d %H:%M:%S'),
                 'description': texto, 'responsible': str(responsavel_id or self.user_id),
                 'caseId': str(caso_id), 'type': 'MANUALLY', 'userId': self.user_id, 'tagIds': []}
        return self.endpoint('histories', 'POST', 'saveHistoricalByCase', corpo=corpo)


# ------------------------------------------------------------------ util
def mapa_usuarios(cli):
    """{email_minusculo: id, nome_normalizado: id} dos usuarios do Astrea."""
    import unicodedata

    def norm(s):
        s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
        return re.sub(r'[^a-z ]', '', s).strip()
    out = {}
    for u in cli.usuarios():
        uid = u.get('id') or u.get('userId')
        if not uid:
            continue
        if u.get('email'):
            out[u['email'].strip().lower()] = str(uid)
        for campo in ('name', 'nickname', 'nickName'):
            n = norm(u.get(campo))
            if n:
                out.setdefault(n, str(uid))
                out.setdefault(n.split(' ')[0], str(uid))   # primeiro nome, se nao colidir
    return out, norm


def _diagnostico():
    """So leitura: confere login, usuarios, processos, clientes, andamentos e agenda."""
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if not configurado():
        print('Faltam ASTREA_USUARIO e ASTREA_SENHA no config/.env')
        return 2
    a = Astrea()
    print('login ............', 'ok' if a.user_id else 'falhou', '(usuario %s, tenant %s)' % (a.user_id, a.tenant_id))
    passos = [
        ('usuarios', lambda: len(a.usuarios())),
        ('processos ativos', lambda: sum(1 for _ in a.processos(maximo=300))),
        ('clientes', lambda: sum(1 for _ in a.clientes(maximo=300))),
        ('andamentos (30d)', lambda: len(a.andamentos(desde=(date.today() - timedelta(days=30)).isoformat(),
                                                     limite=50))),
        ('agenda (7d)', lambda: len(a.agenda(date.today().isoformat(),
                                             (date.today() + timedelta(days=7)).isoformat()))),
        ('listas de tarefa', lambda: len(a.listas_de_tarefas())),
    ]
    ok = True
    for nome, f in passos:
        try:
            print('%-17s %s' % (nome, f()))
        except Exception as e:
            ok = False
            print('%-17s ERRO %s' % (nome, str(e)[:200]))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(_diagnostico() if (sys.argv[1:] or ['diagnostico'])[0] == 'diagnostico' else 2)
