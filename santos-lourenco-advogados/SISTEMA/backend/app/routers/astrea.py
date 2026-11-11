"""ASTREA - status, agenda e sincronizacao manual (10/11/2026). A ponte fica em app/astrea_sync.py.

GET  /api/astrea/status                 integracao ligada? login ok? pendencias de envio
GET  /api/astrea/agenda?de=&ate=&tipos= prazos, tarefas, audiencias e atendimentos do Astrea (lidos na hora)
POST /api/astrea/sincronizar            (admin) traz a carteira e reenvia o que ficou pendente
POST /api/astrea/tarefas/{id}/enviar    copia de novo uma tarefa do sistema para o Astrea
POST /api/astrea/andamentos/{id}/enviar copia de novo um andamento do sistema para o Astrea
"""
import asyncio
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from .. import astrea_sync as AS
from ..deps import usuario_atual, requer_admin

router = APIRouter(prefix='/api/astrea', tags=['astrea'])


def _exigir():
    if not AS.ligado():
        raise HTTPException(400, 'Integracao com o Astrea desligada: SISTEMA_JURIDICO=astrea e '
                                 'ASTREA_USUARIO/ASTREA_SENHA no config/.env')


def _erro(e):
    return HTTPException(502, 'Astrea nao respondeu: %s' % str(e)[:240])


@router.get('/status')
async def status(user=Depends(usuario_atual)):
    def _ver():
        out = {'ligado': AS.ligado()}
        c = AS.con()
        try:
            out['vinculos'] = {r[0]: r[1] for r in c.execute(
                'SELECT entidade, COUNT(*) FROM astrea_vinculos GROUP BY entidade')}
            out['pendencias'] = [dict(r) for r in c.execute(
                'SELECT entidade, local_id, erro, tentativas, em FROM astrea_pendencias ORDER BY em DESC LIMIT 50')]
        finally:
            c.close()
        if out['ligado']:
            try:
                a = AS.cliente()
                out['login'] = {'ok': True, 'usuario_id': a.user_id, 'tenant_id': a.tenant_id}
            except Exception as e:
                out['login'] = {'ok': False, 'erro': str(e)[:240]}
        return out
    return await asyncio.to_thread(_ver)


@router.get('/agenda')
async def agenda(de: str = '', ate: str = '', tipos: str = '', user=Depends(usuario_atual)):
    _exigir()
    de = de or date.today().isoformat()
    ate = ate or (date.fromisoformat(de[:10]) + timedelta(days=7)).isoformat()
    try:
        if (date.fromisoformat(ate[:10]) - date.fromisoformat(de[:10])).days > 92:
            raise HTTPException(400, 'Periodo maximo: 92 dias')
    except ValueError:
        raise HTTPException(400, 'Datas no formato AAAA-MM-DD')
    lista = tuple(t.strip() for t in tipos.split(',') if t.strip()) or None
    try:
        return {'de': de, 'ate': ate, 'itens': await asyncio.to_thread(AS.agenda, de, ate, lista)}
    except HTTPException:
        raise
    except Exception as e:
        raise _erro(e)


@router.post('/sincronizar')
async def sincronizar(user=Depends(requer_admin)):
    _exigir()

    def _rodar():
        a = AS.cliente()
        c = AS.con()
        try:
            return {'carteira': AS.importar_carteira(c, a), 'pendencias': AS.reenviar_pendencias(c, a)}
        finally:
            c.close()
    try:
        return {'ok': True, **await asyncio.to_thread(_rodar)}
    except Exception as e:
        raise _erro(e)


@router.post('/tarefas/{tarefa_id}/enviar')
async def enviar_tarefa(tarefa_id: int, user=Depends(usuario_atual)):
    _exigir()
    aid = await asyncio.to_thread(AS.enviar_tarefa, tarefa_id)
    if not aid:
        raise HTTPException(502, 'Nao subiu para o Astrea (veja /api/astrea/status, pendencias)')
    return {'ok': True, 'astrea_id': str(aid)}


@router.post('/andamentos/{andamento_id}/enviar')
async def enviar_andamento(andamento_id: int, user=Depends(usuario_atual)):
    _exigir()
    aid = await asyncio.to_thread(AS.enviar_andamento, andamento_id)
    if not aid:
        raise HTTPException(502, 'Nao subiu para o Astrea (veja /api/astrea/status, pendencias)')
    return {'ok': True, 'astrea_id': str(aid)}
