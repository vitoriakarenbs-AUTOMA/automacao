#!/usr/bin/env python3
"""Aplica o padrao unico da Dra. Vitoria (timbrado Vitoria Barbosa) a uma peca em Markdown ou texto.

Chamado pelo agente de pecas do servidor (SYNC/pecas_agente.py -> _timbrar):
    python scripts/aplicar_timbrado.py --in PECA.md --out PECA.docx
"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(RAIZ / 'SISTEMA' / 'backend'))
from app.juridico.padrao_vitoria import gerar_docx, pendencias  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--in', dest='entrada', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--check', action='store_true', help='so lista pendencias entre colchetes')
a = ap.parse_args()
texto = Path(a.entrada).read_text(encoding='utf-8-sig')
pend = pendencias(texto)
if pend:
    print('ATENCAO - pendencias no texto:')
    for p in pend:
        print('  ', p)
if not a.check:
    print('OK:', gerar_docx(texto, a.out))
