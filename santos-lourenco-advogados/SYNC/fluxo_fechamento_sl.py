# -*- coding: utf-8 -*-
"""
FLUXO DE FECHAMENTO POS-REUNIAO - Santos Lourenço Leads (pipeline 10)

Projeto 2 do backlog fechado com a Vitória em 12/08/2026: regua de 12 contatos
para o lead que saiu da reuniao de fechamento sem assinar (estudo citado
pela Pam: 85% fecham entre o 8o e o 12o contato).

Regras:
  - Entra na regua: card na etapa "Pós-Reunião de Fechamento" com telefone
    (dedup por final do telefone, 8 digitos).
  - Cadencia: toques nos dias D+0,1,2,4,6,8,10,12,14,17,20,25 (12 toques),
    enviados 1x/dia dentro da janela 8h-20h.
  - Lead RESPONDEU (origem='contato' depois da inscricao): a regua PARA e o
    time e avisado para assumir a conversa (fechamento e humano).
  - Card SAIU da etapa: regua encerra sozinha. Se foi para Contrato /
    Assinatura, Elaboração de Contrato ou Ganho, o time recebe a boa noticia.
  - Compliance: nenhuma promessa de resultado; linguagem humana e simples
    (regra da Pam: sem travessoes); ultima mensagem se despede e para.

Uso:
    python SYNC/fluxo_fechamento_sl.py             # dry-run (modo sombra)
    python SYNC/fluxo_fechamento_sl.py --enviar    # envia de verdade
    python SYNC/fluxo_fechamento_sl.py --status    # mostra a fila
Cron VPS (sombra ate a Vitória aprovar as mensagens; depois adicionar --enviar):
    5 10 * * * cd /opt/santoslourenco && SL_CONFIG_ENV=/opt/santoslourenco/config/.env \
      /opt/santoslourenco/venv/bin/python /opt/santoslourenco/SYNC/fluxo_fechamento_sl.py \
      >> /var/log/sl-fechamento.log 2>&1
"""
import io
import json
import os
import sqlite3
import sys
from datetime import date, datetime

if (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "") != "utf8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from dotenv import load_dotenv
load_dotenv(os.getenv("SL_CONFIG_ENV", os.path.join(HERE, "..", "config", ".env")))
if os.path.exists("/opt/santoslourenco/config/.env"):
    load_dotenv("/opt/santoslourenco/config/.env")

import requests
import wa_dapi  # saida unica de WhatsApp: D-API (24/09/2026)

DB = os.getenv("SL_DB", "/opt/santoslourenco/SISTEMA/backend/sistema_sl.db")
FILA = os.path.join(HERE, "fechamento_fila.json")
PIPELINE = 10
ETAPA = "Pós-Reunião de Fechamento"
ETAPAS_GANHO = ("Contrato / Assinatura", "Elaboração de Contrato", "Ganho")
CADENCIA = (0, 1, 2, 4, 6, 8, 10, 12, 14, 17, 20, 25)
JANELA = (8, 20)
TEL_TIME = ""

# Só entra na régua quem foi QUALIFICADO pelo time (Pam, 12/08): a etiqueta
# do card na coluna Pós-Reunião precisa conter a palavra QUALIFICADO.
MARCA_QUALIFICADO = "QUALIFICADO"

# Pasta de depoimentos enviada no toque 3 (escolhida pela Vitória 12/08:
# VIDEOS/DEPOIMENTOS, ja compartilhada como 'qualquer pessoa com o link').
DEPO_LINK = "https://drive.google.com/drive/folders/18PCBQ-aac8wHJJoXshf8QkBIyF5GCBoK"

# 12 toques persuasivos (direcao da Pam, 12/08): tocar na dor, orgulho de quem
# movimenta o Brasil, nao levar calado, depoimentos de quem ja passou, e a
# certeza de estar tomando a melhor decisao. Sem travessao, simples cognicao,
# SEM promessa de resultado (Provimento OAB 205/2021). {nome} = primeiro nome.
MENSAGENS = (
    "Oi, {nome}! Aqui é do Santos Lourenço Advogados. Foi muito bom te ouvir na reunião. "
    "Deixa eu te falar uma coisa que a gente acredita de verdade: é o "
    "caminhoneiro que segura esse país nas costas. Comida, remédio, "
    "combustível: nada chega sem você. E quem movimenta o Brasil merece "
    "respeito também na hora de receber o que é seu. Qualquer dúvida da "
    "reunião, me chama aqui. 🚛🇧🇷",

    "{nome}, pensa comigo: quantas madrugadas você virou no volante? Quantos "
    "feriados longe da família? Quanta hora parada em pátio esperando carga, "
    "sem ver um centavo por isso? Isso tem nome e tem valor na Justiça. Você "
    "não precisa levar calado.",

    "{nome}, você não precisa acreditar só na gente. Escuta quem já viveu "
    "isso:\n{depoimentos}\nSão motoristas como você, que decidiram não deixar "
    "barato. Hoje contam a história de cabeça erguida.",

    "{nome}, tem empresa que conta com o silêncio do motorista. Acha que você "
    "vai deixar pra lá porque sempre foi assim. Mostrar que você conhece os "
    "seus direitos muda a conversa. E nessa briga você não entra sozinho: a "
    "gente vai junto, do começo ao fim.",

    "Preciso ser honesta com você, {nome}: a Justiça tem prazo. Depois de 2 "
    "anos da saída da empresa, o direito morre e ninguém devolve. Cada semana "
    "que passa pode ser dinheiro seu escorrendo pelo ralo. Não deixa o "
    "relógio decidir a sua vida.",

    "{nome}, sei o que trava muita gente: e quanto custa isso? Foi explicado "
    "na reunião, sem pegadinha e sem surpresa. E tirar dúvida comigo aqui não "
    "custa nada. Manda um oi que eu te explico de novo, no seu tempo.",

    "{nome}, fecha o olho e pensa: o que essa causa pode representar pra sua "
    "família? Respirar aliviado, quitar uma dívida, dar um futuro melhor pra "
    "quem você ama. Buscar o que é seu por direito não é aventura. É justiça.",

    "A sua análise está pronta, {nome}. A equipe da Dra. Vitória olhou o seu "
    "caso com lupa e encontrou pontos sérios. A parte difícil você já fez: "
    "contou a sua história. Agora falta uma palavra sua pra gente entrar em "
    "campo por você.",

    "{nome}, começar é mais simples do que parece: CNH e comprovante de "
    "residência, tudo pelo WhatsApp. Assinatura digital no celular, sem "
    "cartório, sem burocracia. Da boleia mesmo você resolve em minutos. O "
    "resto é com a gente.",

    "{nome}, a Dra. Vitória dedica a carreira a defender quem vive da "
    "estrada. Estuda, escreve e briga por caminhoneiro todos os dias. Conhece "
    "o trabalho dela: www.sladvogados.com.br e "
    "https://vitorialourenco.jusbrasil.com.br/",

    "Vou te falar de coração, {nome}: já vi muito motorista deixar pra depois "
    "e perder o prazo. Dói ver isso. Não quero que aconteça com você. A sua "
    "análise segue pronta aqui. Uma resposta sua e a gente arranca hoje mesmo.",

    "{nome}, essa é minha última mensagem, prometo. Só te deixo uma pergunta: "
    "daqui a um ano, você quer olhar pra trás e ver que lutou pelo que é seu, "
    "ou que deixou passar? Você movimenta o Brasil. Deixa a gente movimentar "
    "a sua causa. A porta do Santos Lourenço segue aberta. Forte abraço e estrada boa! 🚛",
)

MSG3_SEM_LINK = (
    "{nome}, motorista que a gente atendeu conta de cabeça erguida a história "
    "de quem decidiu não deixar barato. Se quiser ouvir esses depoimentos, me "
    "manda um oi que eu te envio. São pessoas como você."
)


def _json(path, padrao):
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return padrao


def _salvar(path, dados):
    open(path, "w", encoding="utf-8").write(json.dumps(dados, ensure_ascii=False, indent=1))


def _tel8(tel):
    d = "".join(ch for ch in str(tel or "") if ch.isdigit())
    return d[-8:] if len(d) >= 8 else d


def _ddi(tel):
    d = "".join(ch for ch in str(tel) if ch.isdigit())
    return d if d.startswith("55") else "55" + d


def zapi_enviar_texto(telefone, texto):
    # Canal: D-API pelo numero oficial (wa_dapi); o nome da funcao ficou so para nao mexer nos chamadores.
    # ok so quando a D-API confirmou o envio (com id da mensagem).
    try:
        ok, info = wa_dapi.enviar_texto(_ddi(telefone), texto)
        if not ok:
            print(f"  (d-api falhou: {str(info)[:120]})")
        return ok
    except Exception as e:
        print(f"  (d-api erro: {str(e)[:120]})")
        return False


def _con():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=15)
    con.execute("pragma busy_timeout=8000")
    return con


def _cards_na_etapa():
    con = _con()
    rows = con.execute(
        "select id, contato_nome, contato_telefone, etapa, tag from wa_conversas "
        "where pipeline_id=?", (PIPELINE,)).fetchall()
    con.close()
    return rows


def _qualificado(tag):
    return MARCA_QUALIFICADO in (tag or "").upper()


def _respondeu_depois(conversa_id, desde_iso):
    con = _con()
    n = con.execute(
        "select count(*) from wa_mensagens where conversa_id=? and origem='contato' "
        "and criado_em > ?", (conversa_id, desde_iso)).fetchone()[0]
    con.close()
    return n > 0


def _primeiro_nome(nome):
    p = (nome or "").strip().split()
    return p[0].title() if p else "amigo"


def rodar(enviar=False):
    agora = datetime.now()
    print(f"=== FLUXO FECHAMENTO POS-REUNIAO | {agora:%d/%m/%Y %H:%M} | "
          + ("ENVIAR" if enviar else "SOMBRA (dry-run)") + " ===")
    fila = _json(FILA, {})
    cards = _cards_na_etapa()
    na_etapa = {}      # tel8 -> card QUALIFICADO na etapa
    etapa_por_tel = {}
    for cid, nome, tel, etapa, tag in cards:
        t8 = _tel8(tel)
        if not t8:
            continue
        etapa_por_tel[t8] = (cid, nome, tel, etapa)
        if etapa == ETAPA:
            if _qualificado(tag):
                na_etapa[t8] = (cid, nome, tel)
            elif t8 not in fila:
                print(f"  [AGUARDA QUALIFICACAO] {nome} (etiqueta: {tag or 'sem'})")

    # 1) inscreve quem chegou na etapa JA qualificado pelo time
    for t8, (cid, nome, tel) in na_etapa.items():
        if t8 not in fila:
            fila[t8] = {"conversa_id": cid, "nome": nome, "telefone": tel,
                        "d0": date.today().isoformat(),
                        "inscrito_em": agora.strftime("%Y-%m-%d %H:%M:%S"),
                        "toques": [], "respondeu": False, "encerrado": False}
            print(f"  [INSCREVER] {nome} (tel final {t8}) | QUALIFICADO | D0 hoje")

    # 2) encerra quem saiu da etapa / avisa fechamento
    for t8, c in fila.items():
        if c.get("encerrado"):
            continue
        if t8 not in na_etapa:
            info = etapa_por_tel.get(t8)
            nova = info[3] if info else "(fora do pipeline)"
            c["encerrado"] = True
            c["motivo"] = ("etiqueta QUALIFICADO removida (regua parada pelo time)"
                           if nova == ETAPA else f"saiu da etapa -> {nova}")
            print(f"  [ENCERRAR] {c['nome']} | {c['motivo']}")
            if nova in ETAPAS_GANHO:
                aviso = (f"🎉 Fluxo de fechamento: *{c['nome']}* avançou para "
                         f"'{nova}' após {len(c['toques'])} toque(s) da régua!")
                if enviar:
                    zapi_enviar_texto(TEL_TIME, aviso)
                else:
                    print(f"    (sombra: avisaria o time: {aviso})")

    # 3) respondeu? para a regua e chama humano
    for t8, c in fila.items():
        if c.get("encerrado") or c.get("respondeu"):
            continue
        desde = c.get("ultimo_toque_em") or c.get("inscrito_em")
        if _respondeu_depois(c["conversa_id"], desde):
            c["respondeu"] = True
            aviso = (f"🗣️ Fluxo de fechamento: *{c['nome']}* RESPONDEU no WhatsApp. "
                     f"Régua pausada no toque {len(c['toques'])}/12. "
                     "Hora do humano assumir e fechar! 💛")
            print(f"  [RESPONDEU] {c['nome']} | regua pausada")
            if enviar:
                zapi_enviar_texto(TEL_TIME, aviso)
            else:
                print(f"    (sombra: avisaria o time: {aviso})")

    # 4) toques do dia
    h = agora.hour
    if not (JANELA[0] <= h < JANELA[1]):
        print(f"  (fora da janela {JANELA[0]}h-{JANELA[1]}h: sem toques)")
    else:
        for t8, c in fila.items():
            if c.get("encerrado") or c.get("respondeu"):
                continue
            dias = (date.today() - date.fromisoformat(c["d0"])).days
            devidos = [i for i, d in enumerate(CADENCIA) if d <= dias]
            if not devidos:
                continue
            prox = devidos[-1]           # so o toque mais recente devido
            if prox in c["toques"]:
                continue
            if c.get("ultimo_toque_dia") == date.today().isoformat():
                continue                 # no maximo 1 toque por dia
            if prox == 2 and not DEPO_LINK:
                msg = MSG3_SEM_LINK.format(nome=_primeiro_nome(c["nome"]))
            else:
                msg = MENSAGENS[prox].format(nome=_primeiro_nome(c["nome"]),
                                             depoimentos=DEPO_LINK)
            print(f"  [TOQUE {prox + 1}/12] {c['nome']} (D+{dias})")
            if enviar:
                if zapi_enviar_texto(c["telefone"], msg):
                    c["toques"].append(prox)
                    c["ultimo_toque_dia"] = date.today().isoformat()
                    c["ultimo_toque_em"] = agora.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    print("    envio FALHOU, tenta amanha")
            else:
                print(f"    (sombra: enviaria: {msg[:90]}...)")

    if enviar:  # dry-run NUNCA salva estado (licao da varredura, 12/08)
        _salvar(FILA, fila)
    ativos = sum(1 for c in fila.values() if not c.get("encerrado"))
    print(f"=== fim | {ativos} na regua ===")


def status():
    fila = _json(FILA, {})
    if not fila:
        print("Fila vazia.")
        return
    for t8, c in fila.items():
        flag = ("ENCERRADO: " + c.get("motivo", "")) if c.get("encerrado") else (
            "RESPONDEU (humano)" if c.get("respondeu") else "ativo")
        print(f"- {c['nome']} | D0 {c['d0']} | toques {len(c['toques'])}/12 | {flag}")


if __name__ == "__main__":
    if "--status" in sys.argv:
        status()
    else:
        rodar(enviar="--enviar" in sys.argv)
