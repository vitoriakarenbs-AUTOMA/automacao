# -*- coding: utf-8 -*-
"""
DONA DO LEAD NO CRM - cada vendedora com o seu lead (pedido do Joab, 23/10/2026).

A dona e o wa_conversas.atendente_email: o mesmo campo que o filtro "meus" do Chat, o comercial.py,
o painel comercial e a contratacao ja usam. Nada de campo novo; nenhum fluxo da Vitória foi alterado.

Regra (Joab, 23/10):
  1. Quem MANDA MENSAGEM para o lead e a dona (a primeira entre Rafaella e Marcella que escreveu).
  2. Lead novo que nenhuma das duas tocou segue a regra da Vitória (roteamento_vendedoras.py, 22/09):
     antes das 14h -> Rafaella; das 14h as 18h em dia util o primeiro da tarde -> Marcella e depois
     intercala; fora do horario -> Rafaella. A alternancia daqui tem estado PROPRIO
     (crm_dona_state.json) para nao mexer na vez do alarme e do fluxo "voce ja saiu?".
  3. Os que ja passaram sem contato: divididos igualmente, um para cada, por quadro (--estoque).
  4. Dona dada por este robo e PROVISORIA: se a outra vendedora mandar a primeira mensagem, o lead
     passa para ela (regra 1). Dona marcada por pessoa ou pelo sistema fica como esta.

Modos:
  (sem flag)            simula tudo, nao grava nada (relatorio em /opt/santoslourenco/producao/crm_dona/)
  --estoque --aplicar   uma vez: divide igualmente os que ja passaram sem dona
  --novos               cron a cada minuto: dona para lead novo + passa para quem escreveu primeiro
Quadros: Santos Lourenço Leads (10) e Santos Lourenço GR - Desbloqueio (24). Etapas encerradas ficam de fora.
"""
import argparse
import csv
import fcntl
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta

DB = "/opt/santoslourenco/SISTEMA/backend/sistema_sl.db"
SAIDA = "/opt/santoslourenco/producao/crm_dona"
ESTADO = "/opt/santoslourenco/SYNC/crm_dona_state.json"
QUADROS = (10, 24)
VENDEDORAS = {"rafaella@sladvogados.com.br": "Rafaella", "marcella@sladvogados.com.br": "Marcella"}
EMAIL = {v: k for k, v in VENDEDORAS.items()}
ENCERRADAS = ("perdido", "desqualificado", "fechou")
INICIO_TARDE, FIM_TARDE = 14, 18
JANELA_NOVOS_H = 48          # --novos olha leads que chegaram nas ultimas 48 h


def agora_br():
    return datetime.utcnow() - timedelta(hours=3)


def br(utc_txt):
    return datetime.fromisoformat(str(utc_txt)[:19].replace("T", " ")) - timedelta(hours=3)


def log(*a):
    print(agora_br().strftime("%d/%m %H:%M:%S"), *a, flush=True)


def regra_da_pam(quando_br, tarde):
    """Mesma regra do roteamento_vendedoras.quem_recebe_demitido; 'tarde' = {dia: ultima_da_tarde}."""
    na_tarde = quando_br.weekday() < 5 and INICIO_TARDE <= quando_br.hour < FIM_TARDE
    if not na_tarde:
        return "Rafaella"
    dia = quando_br.strftime("%Y-%m-%d")
    vez = "Marcella" if tarde.get(dia) in (None, "Rafaella") else "Rafaella"
    tarde[dia] = vez
    return vez


def primeira_vendedora(c, cid):
    r = c.execute("select lower(autor) from wa_mensagens where conversa_id=? and origem='atendente' "
                  "and lower(autor) in (%s) order by id limit 1" % ",".join("?" * len(VENDEDORAS)),
                  (cid, *VENDEDORAS)).fetchone()
    return VENDEDORAS[r[0]] if r else None


def aberto(etapa):
    return not any(e in (etapa or "").lower() for e in ENCERRADAS)


def carregar_estado():
    try:
        with open(ESTADO, encoding="utf-8") as f:
            est = json.load(f)
    except Exception:
        est = {}
    est.setdefault("tarde", {})
    est.setdefault("auto", {})          # conversa_id -> dona dada pelo robo (provisoria)
    return est


def salvar_estado(est):
    hoje = agora_br().date()
    est["tarde"] = {d: v for d, v in est["tarde"].items()
                    if (hoje - datetime.strptime(d, "%Y-%m-%d").date()).days < 7}
    tmp = ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(est, f, ensure_ascii=False)
    os.replace(tmp, ESTADO)


def marcar(c, cid, dona, so_se_vazio=True):
    cond = " and coalesce(atendente_email,'')=''" if so_se_vazio else ""
    return c.execute("update wa_conversas set atendente_email=? where id=?" + cond, (EMAIL[dona], cid)).rowcount


def simular_ou_estoque(aplicar, estoque):
    c = sqlite3.connect(DB, timeout=60) if aplicar else sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    est = carregar_estado()
    leads = c.execute(
        "select id, coalesce(contato_nome,''), contato_telefone, pipeline_id, coalesce(etapa,''), "
        "coalesce(atendente_email,''), criado_em from wa_conversas where pipeline_id in (%s) and status='aberto' "
        "order by criado_em" % ",".join(map(str, QUADROS))).fetchall()
    tarde, vez, linhas, motivo_ct, dona_ct = {}, {}, [], Counter(), Counter()
    for cid, nome, tel, pip, etapa, atual, criado in leads:
        if not aberto(etapa):
            continue
        if atual:
            dona, motivo = VENDEDORAS.get(atual.lower(), atual), "ja tinha dona"
        else:
            p = primeira_vendedora(c, cid)
            if p:
                dona, motivo = p, "mandou mensagem primeiro"
            elif estoque:
                vez[pip] = "Marcella" if vez.get(pip) == "Rafaella" else "Rafaella"
                dona, motivo = vez[pip], "estoque sem contato: dividido igualmente"
            else:
                dona, motivo = regra_da_pam(br(criado), tarde), "lead sem contato: regra da Pam"
        motivo_ct[motivo] += 1
        dona_ct[(pip, dona)] += 1
        linhas.append((cid, nome, tel, pip, etapa, atual, dona, motivo, br(criado).strftime("%d/%m %H:%M")))
    os.makedirs(SAIDA, exist_ok=True)
    arq = os.path.join(SAIDA, f"{'aplicado' if aplicar else 'simulacao'}_{datetime.now():%Y%m%d_%H%M}.csv")
    with open(arq, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["conversa", "nome", "telefone", "quadro", "etapa", "dona_antes", "dona", "motivo", "chegou"])
        w.writerows(linhas)
    print(f"leads abertos analisados: {len(linhas)}  (relatorio: {arq})")
    for m, n in motivo_ct.most_common():
        print(f"  {m}: {n}")
    for pip in QUADROS:
        print(f"  quadro {pip}: " + ", ".join(f"{d} {n}" for (p, d), n in sorted(dona_ct.items()) if p == pip))
    if not aplicar:
        print("SIMULACAO: nada foi gravado.")
        return
    mudou = 0
    with c:
        for cid, _, _, _, _, atual, dona, motivo, _ in linhas:
            if not atual and dona in EMAIL and marcar(c, cid, dona):
                mudou += 1
                if not motivo.startswith("mandou"):
                    est["auto"][str(cid)] = dona       # provisoria: passa para quem escrever primeiro
    salvar_estado(est)
    print(f"APLICADO: {mudou} leads ganharam dona")


def novos():
    """Cron: dona para lead novo (regra da Pam, na hora em que ele aparece) e troca a dona provisoria
    para quem mandou a primeira mensagem."""
    with open(ESTADO + ".lock", "w") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)
        est = carregar_estado()
        c = sqlite3.connect(DB, timeout=60)
        feitos = []
        with c:
            desde = (datetime.utcnow() - timedelta(hours=JANELA_NOVOS_H)).strftime("%Y-%m-%d %H:%M:%S")
            for cid, pip, etapa in c.execute(
                    "select id, pipeline_id, coalesce(etapa,'') from wa_conversas where pipeline_id in (%s) "
                    "and status='aberto' and coalesce(atendente_email,'')='' and criado_em>=?"
                    % ",".join(map(str, QUADROS)), (desde,)).fetchall():
                if not aberto(etapa):
                    continue
                p = primeira_vendedora(c, cid)
                dona = p or regra_da_pam(agora_br(), est["tarde"])
                if marcar(c, cid, dona):
                    if not p:
                        est["auto"][str(cid)] = dona
                    feitos.append(f"#{cid}->{dona}{'' if p else ' (regra da Pam)'}")
            # dona provisoria: se a outra vendedora escreveu primeiro, o lead e dela
            for scid, dona in list(est["auto"].items()):
                row = c.execute("select coalesce(atendente_email,''), pipeline_id from wa_conversas where id=?",
                                (int(scid),)).fetchone()
                if not row or row[0].lower() != EMAIL.get(dona) or row[1] not in QUADROS:
                    est["auto"].pop(scid, None)        # alguem mudou na mao ou saiu do quadro: nao mexo mais
                    continue
                p = primeira_vendedora(c, int(scid))
                if p:
                    if p != dona:
                        marcar(c, int(scid), p, so_se_vazio=False)
                        feitos.append(f"#{scid} {dona}->{p} (escreveu primeiro)")
                    est["auto"].pop(scid, None)
        salvar_estado(est)
        if feitos:
            log("; ".join(feitos))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="grava (com --estoque)")
    ap.add_argument("--estoque", action="store_true", help="os que ja passaram sem contato: dividir igualmente")
    ap.add_argument("--novos", action="store_true", help="cron: dona para lead novo")
    a = ap.parse_args()
    if a.novos:
        novos()
    else:
        simular_ou_estoque(a.aplicar, a.estoque)


if __name__ == "__main__":
    main()
