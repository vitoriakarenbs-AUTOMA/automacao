"""Seed OPCIONAL da equipe inicial do escritorio (Dr. Joab e Dra. Vitoria).

Nenhuma senha fica no codigo: cada uma e gerada na hora e impressa UMA vez.
Os e-mails de login vem do config/.env (EQUIPE_EMAIL_JOAB / EQUIPE_EMAIL_VITORIA)
ou dos argumentos:

    python seed_equipe.py
    python seed_equipe.py joab@dominio vitoria@dominio
"""
import asyncio
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv  # noqa: E402

from app.config import ENV_CENTRAL, ENV_LOCAL  # noqa: E402
from seed_admin import criar_ou_atualizar  # noqa: E402

for _env in (ENV_CENTRAL, ENV_LOCAL):
    if _env.exists():
        load_dotenv(_env, override=False)


def main():
    email_joab = sys.argv[1] if len(sys.argv) > 1 else os.getenv('EQUIPE_EMAIL_JOAB', '')
    email_vit = sys.argv[2] if len(sys.argv) > 2 else os.getenv('EQUIPE_EMAIL_VITORIA', '')
    if not email_joab or not email_vit:
        print('Informe os e-mails (argumentos ou EQUIPE_EMAIL_JOAB/EQUIPE_EMAIL_VITORIA no config/.env).')
        sys.exit(1)
    equipe = [
        ('Joab da Silva Lourenço', email_joab, 'admin', True),
        ('Vitória Karen Barbosa dos Santos Lourenço', email_vit, 'advogado', True),
    ]
    print('Guarde as senhas abaixo. Elas NAO ficam salvas em lugar nenhum.\n')
    for nome, email, papel, fin in equipe:
        senha = secrets.token_urlsafe(12)
        acao = asyncio.run(criar_ou_atualizar(nome, email, senha, papel=papel, financeiro=fin))
        print(f'{acao:10} {papel:9} {email:40} senha: {senha}')


if __name__ == '__main__':
    main()
