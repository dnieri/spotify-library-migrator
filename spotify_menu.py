"""
Menu principal do Spotify Library Migrator - orquestra os demais scripts:
- spotify_import.py  (transferencia direta entre contas e importacao de CSV)
- spotify_export.py  (exportacao da biblioteca para .txt)
- spotify_merge.py   (mesclagem de playlists duplicadas)

Uso:
    python spotify_menu.py

Na primeira execucao (sem .env configurado) vai direto para o wizard.
"""

import sys

import spotify_import
from spotify_import import (edit_keys, env_configured, list_accounts,
                            manage_accounts, migrate_legacy_cache, read_input,
                            wizard)
from spotify_merge import run_merge


def menu():
    actions = {
        "1": spotify_import.run_transfer,
        "2": spotify_import.run_import,
        "3": spotify_import.run_export,
        "4": run_merge,
        "5": manage_accounts,
        "6": edit_keys,
    }
    while True:
        accounts = list_accounts()
        names = ", ".join(name for _, name in accounts) if accounts else "nenhuma"
        print("\n=== Spotify Library Migrator ===")
        print(f"Contas conectadas: {names}\n")
        print("  1. Transferir biblioteca entre contas conectadas")
        print("  2. Importar CSV do TuneMyMusic")
        print("  3. Exportar biblioteca para .txt")
        print("  4. Mesclar playlists duplicadas")
        print("  5. Gerenciar contas (conectar / remover)")
        print("  6. Alterar chaves da API (.env)")
        print("  0. Sair")
        choice = read_input("\nEscolha uma opcao: ")
        if choice is None or choice == "0":
            return
        actions.get(choice, lambda: print("Opcao invalida."))()


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    if not env_configured():
        wizard()  # primeira execucao: vai direto para a configuracao guiada
    migrate_legacy_cache()
    menu()


if __name__ == "__main__":
    main()
