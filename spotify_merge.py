"""
Mescla playlists parecidas/duplicadas de uma conta: copia para a playlist de
DESTINO (a mais nova) as faixas da playlist de ORIGEM (a antiga) que ainda nao
estao la. A playlist antiga e mantida intacta - nada e removido.

Rode pelo menu (python spotify_menu.py, opcao 4) ou direto:
    python spotify_merge.py
"""

from spotify_import import (ask_yes, choose_account, client_for, failures,
                            fetch_playlist_track_ids, paginate, read_input,
                            report_failures, run_batches)


def own_playlists(sp, owner_id):
    """[(id, nome, total de faixas)] das playlists proprias da conta."""
    result = []
    for pl in paginate(lambda o: sp.current_user_playlists(limit=50, offset=o)):
        if (pl.get("owner") or {}).get("id") == owner_id:
            total = (pl.get("items") or pl.get("tracks") or {}).get("total", 0)
            result.append((pl["id"], pl["name"], total))
    return result


def pick_playlist(playlists, title):
    print(f"\n{title}")
    for i, (_, name, total) in enumerate(playlists, 1):
        print(f"  {i:3d}. {name} ({total} faixas)")
    choice = read_input("Numero: ")
    if choice and choice.isdigit() and 1 <= int(choice) <= len(playlists):
        return playlists[int(choice) - 1]
    print("Opcao invalida.")
    return None


def merge_into(sp, source_id, target_id):
    """Adiciona ao destino as faixas da origem que ainda nao estao la,
    preservando a ordem da origem. Retorna quantas foram adicionadas."""
    source_ids = dict.fromkeys(fetch_playlist_track_ids(sp, source_id))
    target_ids = set(fetch_playlist_track_ids(sp, target_id))
    missing = [tid for tid in source_ids if tid not in target_ids]
    if missing:
        uris = [f"spotify:track:{tid}" for tid in missing]
        run_batches(uris, 100,
                    lambda batch: sp.playlist_add_items(target_id, batch),
                    "mescladas")
    return len(missing)


def run_merge():
    account = choose_account("Conta onde estao as playlists a mesclar:")
    if not account:
        return
    sp = client_for(account[0])
    print("\nLendo as playlists da conta...")
    playlists = own_playlists(sp, account[0])
    if len(playlists) < 2:
        print("A conta precisa ter pelo menos duas playlists proprias.")
        return

    source = pick_playlist(playlists, "Playlist ANTIGA (origem - sera mantida como esta):")
    if not source:
        return
    remaining = [p for p in playlists if p[0] != source[0]]
    target = pick_playlist(remaining, "Playlist NOVA (destino - recebe as faixas que faltam):")
    if not target:
        return

    if not ask_yes(f"Copiar para '{target[1]}' as faixas de '{source[1]}' que faltam la?"):
        print("Cancelado.")
        return

    failures.clear()
    added = merge_into(sp, source[0], target[0])
    if added:
        print(f"{added} faixas adicionadas em '{target[1]}'. '{source[1]}' foi mantida intacta.")
    else:
        print(f"Nada a fazer: '{target[1]}' ja contem todas as faixas de '{source[1]}'.")
    report_failures()


if __name__ == "__main__":
    from spotify_import import bootstrap_cli
    bootstrap_cli(run_merge)
