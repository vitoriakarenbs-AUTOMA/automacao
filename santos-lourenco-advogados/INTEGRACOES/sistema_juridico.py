# -*- coding: utf-8 -*-
"""Adaptador do SISTEMA JURIDICO externo do escritorio.

O banco do proprio sistema e a fonte da verdade (clientes, processos, tarefas, agenda). Um
sistema juridico externo, quando houver, so recebe copia. Escolha por .env:

    SISTEMA_JURIDICO=nenhum   (padrao) nada sai do sistema; cada chamada so registra no log
    SISTEMA_JURIDICO=astrea   Astrea pela API interna do app (ASTREA_USUARIO/ASTREA_SENHA de um
                              usuario SO da integracao). Ver INTEGRACOES/astrea_client.py

Interface unica para os robos:
    criar_tarefa(processo, tipo, responsavel, texto, data=None, **extra) -> dict
    lancar_andamento(processo, texto, data=None, **extra)              -> dict
    buscar_processo(numero)                                             -> dict | None

PUBLICACOES (entrada das intimacoes), tambem por .env:
    SL_FONTE_PUBLICACOES=djen        DJEN/Comunica PJe pela OAB (padrao; ja roda no SYNC)
    SL_FONTE_PUBLICACOES=snc         SNC: esqueleto, pendente de credencial (SNC_API_URL, SNC_TOKEN)
    SL_FONTE_PUBLICACOES=djen,snc    as duas
"""
import logging
import os

log = logging.getLogger('sistema_juridico')


def _escolha():
    v = os.getenv('SISTEMA_JURIDICO')
    if v is None:  # robos e backend nao exportam o config/.env: le de la
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import astrea_client
            v = astrea_client._env('SISTEMA_JURIDICO', 'nenhum')
        except Exception:
            v = 'nenhum'
    return (v or 'nenhum').strip().lower()


class _Nenhum:
    nome = 'nenhum'

    def criar_tarefa(self, processo, tipo, responsavel, texto, data=None, **extra):
        log.info('[sistema_juridico=nenhum] tarefa %s / %s / %s (fica so no sistema)', processo, tipo, responsavel)
        return {'ok': True, 'externo': None, 'motivo': 'SISTEMA_JURIDICO=nenhum'}

    def lancar_andamento(self, processo, texto, data=None, **extra):
        log.info('[sistema_juridico=nenhum] andamento %s (fica so no sistema)', processo)
        return {'ok': True, 'externo': None, 'motivo': 'SISTEMA_JURIDICO=nenhum'}

    def buscar_processo(self, numero):
        return None


class _Astrea(_Nenhum):
    """Astrea pela API interna do app (INTEGRACOES/astrea_client.py). `processo` e o numero CNJ
    (ou o id do caso no Astrea). `responsavel` e nome ou e-mail: casa com os usuarios do Astrea;
    se nao casar, fica com o usuario da integracao."""
    nome = 'astrea'

    def __init__(self):
        import sys
        aqui = os.path.dirname(os.path.abspath(__file__))
        if aqui not in sys.path:
            sys.path.insert(0, aqui)
        import astrea_client as AC
        self.AC = AC
        self.cli = AC.Astrea()
        self._usuarios = None

    def _caso_id(self, processo):
        p = str(processo or '').strip()
        if not p:
            return None
        if p.isdigit() and len(p) != 20:      # id do caso no Astrea (CNJ tem 20 digitos)
            return p
        c = self.cli.buscar_processo(p)
        return str(c['id']) if c else None

    def _responsavel_id(self, responsavel):
        if not responsavel:
            return None
        if self._usuarios is None:
            self._usuarios = self.AC.mapa_usuarios(self.cli)
        mapa, norm = self._usuarios
        r = str(responsavel).strip()
        return mapa.get(r.lower()) or mapa.get(norm(r)) or mapa.get(norm(r).split(' ')[0] if norm(r) else '')

    def criar_tarefa(self, processo, tipo, responsavel, texto, data=None, **extra):
        caso = self._caso_id(processo)
        desc = ('%s: %s' % (tipo, texto)) if tipo else texto
        r = self.cli.criar_tarefa(desc, self._responsavel_id(responsavel), prazo=data, caso_id=caso,
                                  prioridade=extra.get('prioridade'))
        tid = (r or {}).get('id') or ((r or {}).get('taskInfoDTO') or {}).get('id')
        return {'ok': True, 'externo': str(tid) if tid else None, 'caso': caso,
                'aviso': None if caso or not processo else 'processo %s nao achado no Astrea: tarefa sem vinculo'
                % processo}

    def lancar_andamento(self, processo, texto, data=None, **extra):
        caso = self._caso_id(processo)
        if not caso:
            return {'ok': False, 'externo': None, 'motivo': 'processo %s nao esta no Astrea' % processo}
        r = self.cli.lancar_andamento(caso, texto, data, self._responsavel_id(extra.get('responsavel')),
                                      instancia=extra.get('instancia', 1))
        return {'ok': True, 'externo': str((r or {}).get('id') or '') or None, 'caso': caso}

    def buscar_processo(self, numero):
        return self.cli.buscar_processo(numero)


def atual():
    return _Astrea() if _escolha() == 'astrea' else _Nenhum()


def criar_tarefa(processo, tipo, responsavel, texto, data=None, **extra):
    return atual().criar_tarefa(processo, tipo, responsavel, texto, data, **extra)


def lancar_andamento(processo, texto, data=None, **extra):
    return atual().lancar_andamento(processo, texto, data, **extra)


def buscar_processo(numero):
    return atual().buscar_processo(numero)


# ------------------------------------------------------------------ publicacoes
def fontes_publicacoes():
    return [f.strip().lower() for f in (os.getenv('SL_FONTE_PUBLICACOES') or 'djen').split(',') if f.strip()]


def buscar_publicacoes_snc(desde=None):
    """SNC (publicacoes e autos). Esqueleto: liga quando houver SNC_API_URL e SNC_TOKEN e o contrato da API."""
    url, tok = os.getenv('SNC_API_URL'), os.getenv('SNC_TOKEN')
    if not (url and tok):
        log.info('SNC sem credencial (SNC_API_URL/SNC_TOKEN): nada a buscar')
        return []
    raise NotImplementedError('SNC: credencial presente, mas o formato da API ainda nao foi mapeado '
                              '(pedir a documentacao ao SNC e implementar aqui).')


if __name__ == '__main__':
    os.environ['SISTEMA_JURIDICO'] = 'nenhum'
    assert criar_tarefa('1', 'PROTOCOLO', 'Vitoria', 'x')['ok'] and buscar_processo('1') is None
    os.environ.update(SISTEMA_JURIDICO='astrea', ASTREA_USUARIO='', ASTREA_SENHA='')
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import astrea_client
    try:
        criar_tarefa('1', 'PROTOCOLO', 'Vitoria', 'x')
        raise SystemExit('astrea sem credencial deveria recusar o login')
    except astrea_client.AstreaLoginErro as e:
        assert 'ASTREA_USUARIO' in str(e)
    os.environ.pop('SNC_TOKEN', None)
    assert buscar_publicacoes_snc() == [] and fontes_publicacoes() == ['djen']
    print('ok')
