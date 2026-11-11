# -*- coding: utf-8 -*-
"""Cadencia nova dos vigias da assinatura (Pam, 26/10/2026: "cadastrar os vigias para varrer com
menos tempo e mover os cards, para traduzir mais agilidade no nosso processo").

O que muda:
  * vigia_assinatura: de duas vezes por hora (15 e 45) para SEIS vezes por hora, nos minutos
    2, 12, 22, 32, 42 e 52, das 9h as 19h, de segunda a sexta;
  * vigia_coluna_fantasma entra novo, seis vezes por hora, nos minutos 7, 17, 27, 37, 47 e 57,
    o dia inteiro: ele nao fala com cliente nenhum, so devolve card invisivel para a coluna de
    onde veio, entao pode rodar de madrugada e no fim de semana.

Os minutos quebrados sao de proposito: as esteiras pesadas rodam em :00 e :30, e disputa de escrita
no SQLite foi o que matou o alarme do lead quente oito vezes ("database is locked").

A janela de envio e o dia util continuam conferidos DENTRO do vigia da assinatura, entao a
cadencia do cron nunca faz ele falar com cliente fora de hora.
"""
import argparse
import re
import subprocess

LINHA_ASSIN = ('2,12,22,32,42,52 9-19 * * 1-5 cd /opt/santoslourenco/SYNC && '
               'SL_CONFIG_ENV=/opt/santoslourenco/config/.env flock -n '
               '/tmp/sl-vigia-assinatura.lock /opt/santoslourenco/venv/bin/python -W ignore '
               '/opt/santoslourenco/SYNC/vigia_assinatura.py --aplicar '
               '>> /var/log/sl-vigia-assinatura.log 2>&1')

LINHAS_FANTASMA = [
    '# --- Vigia da coluna fantasma (Pam, 26/10/2026): card em coluna que nao existe desaparece do',
    '# board E sai do alcance das esteiras (Robinson assinou e ficou tres dias invisivel). Devolve',
    '# para a coluna de onde veio, pela trilha do board. Nao fala com cliente, roda o dia inteiro ---',
    '7,17,27,37,47,57 * * * * cd /opt/santoslourenco/SYNC && SL_CONFIG_ENV=/opt/santoslourenco/config/.env '
    'flock -n /tmp/sl-coluna-fantasma.lock /opt/santoslourenco/venv/bin/python -W ignore '
    '/opt/santoslourenco/SYNC/vigia_coluna_fantasma.py --aplicar >> /var/log/sl-coluna-fantasma.log 2>&1',
]

ap = argparse.ArgumentParser()
ap.add_argument('--aplicar', action='store_true')
a = ap.parse_args()

atual = subprocess.run(['crontab', '-l'], capture_output=True, text=True).stdout
linhas = atual.split('\n')

trocadas = 0
for i, l in enumerate(linhas):
    if 'vigia_assinatura.py' in l and not l.strip().startswith('#'):
        print('antes:  ' + l[:120])
        linhas[i] = LINHA_ASSIN
        print('depois: ' + LINHA_ASSIN[:120])
        trocadas += 1
if trocadas != 1:
    raise SystemExit('esperava uma linha do vigia da assinatura, achei %d' % trocadas)

if 'vigia_coluna_fantasma.py' in atual:
    print('o vigia da coluna fantasma ja esta no cron, nao duplico')
else:
    linhas = [l for l in linhas]
    while linhas and not linhas[-1].strip():
        linhas.pop()
    linhas += [''] + LINHAS_FANTASMA
    print('entra: ' + LINHAS_FANTASMA[-1][:120])

novo = '\n'.join(linhas).rstrip('\n') + '\n'
if not a.aplicar:
    print('(simulacao: nada instalado)')
    raise SystemExit(0)

open('/opt/santoslourenco/SYNC/crontab.bak_antes_cadencia_vigias_20261026', 'w', encoding='utf-8').write(atual)
p = subprocess.run(['crontab', '-'], input=novo, capture_output=True, text=True)
print('crontab -: %s %s' % (p.returncode, (p.stderr or '').strip()[:120]))
conf = subprocess.run(['crontab', '-l'], capture_output=True, text=True).stdout
print('conferindo:')
for l in conf.split('\n'):
    if re.search(r'vigia_assinatura\.py|vigia_coluna_fantasma\.py', l) and not l.strip().startswith('#'):
        print('   ' + l[:130])
