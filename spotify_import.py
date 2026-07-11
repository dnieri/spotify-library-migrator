"""
Spotify Library Migrator - migre musicas curtidas, playlists, albuns salvos e
artistas seguidos entre contas Spotify.

Tres formas de usar:
- Transferencia direta entre duas contas conectadas (sem arquivo intermediario)
- Importacao do CSV exportado pelo TuneMyMusic
- Exportacao da biblioteca para arquivos .txt ("Artista - Musica")

Uso:
    python spotify_import.py                      (menu interativo; wizard na 1a execucao)
    python spotify_import.py caminho/arquivo.csv  (importa o CSV direto, sem menu)

Flags: --yes (pula confirmacoes; com uma unica conta conectada, usa ela)
       --whoami (lista as contas conectadas)

Na primeira execucao o wizard pede o Client ID/Secret do seu app
(https://developer.spotify.com/dashboard) e grava tudo no .env automaticamente.
Varias contas podem ficar conectadas ao mesmo tempo (tokens em .accounts/).
"""

import csv
import json
import os
import re
import sys
from getpass import getpass

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

SCOPE = (
    "user-library-read user-library-modify "
    "playlist-read-private playlist-read-collaborative "
    "playlist-modify-private playlist-modify-public "
    "user-follow-read user-follow-modify"
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
ACCOUNTS_DIR = os.path.join(BASE_DIR, ".accounts")
INDEX_PATH = os.path.join(ACCOUNTS_DIR, "index.json")
LEGACY_CACHE = os.path.join(BASE_DIR, ".spotify_token_cache_import")
FAILED_LOG = os.path.join(BASE_DIR, "import_failures.txt")
ENV_VARS = ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI")
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"

# PUT /me/library aceita no maximo 40 uris por chamada
LIBRARY_BATCH = 40

failures = []


# ---------- entrada do usuario ----------

def read_input(prompt):
    try:
        # remove espacos e o BOM que pipes do PowerShell injetam na 1a linha
        return input(prompt).strip().strip("﻿ï»¿")
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def ask_yes(question):
    answer = read_input(f"{question} (s/n) ")
    return answer is not None and answer.lower() in ("s", "sim", "y", "yes")


# ---------- configuracao (.env) ----------

def env_configured():
    load_dotenv(ENV_PATH, override=True)
    return all(os.environ.get(v) for v in ENV_VARS)


def write_env(client_id, client_secret, redirect_uri):
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(f"SPOTIPY_CLIENT_ID={client_id}\n"
                f"SPOTIPY_CLIENT_SECRET={client_secret}\n"
                f"SPOTIPY_REDIRECT_URI={redirect_uri}\n")
    for var, value in zip(ENV_VARS, (client_id, client_secret, redirect_uri)):
        os.environ[var] = value


def wizard():
    print("\n=== Configuracao inicial ===")
    print("Voce precisa de um app na API do Spotify:")
    print("  1. Acesse https://developer.spotify.com/dashboard e crie um app")
    print("     (a conta dona do app precisa ter Premium ativo).")
    print(f"  2. Nas configuracoes do app, adicione a Redirect URI: {DEFAULT_REDIRECT_URI}")
    print("  3. Copie o Client ID e o Client Secret e informe abaixo.\n")

    client_id = ""
    while not client_id:
        client_id = input("Client ID: ").strip()
    client_secret = ""
    while not client_secret:
        client_secret = getpass("Client Secret (fica oculto ao digitar): ").strip()
    redirect_uri = input(f"Redirect URI [{DEFAULT_REDIRECT_URI}]: ").strip() or DEFAULT_REDIRECT_URI

    write_env(client_id, client_secret, redirect_uri)
    print(f"\nConfiguracao salva em {ENV_PATH}")

    if not list_accounts() and ask_yes("Conectar uma conta do Spotify agora?"):
        connect_new_account()


def edit_keys():
    load_dotenv(ENV_PATH, override=True)
    cur_id = os.environ.get("SPOTIPY_CLIENT_ID", "")
    cur_secret = os.environ.get("SPOTIPY_CLIENT_SECRET", "")
    cur_redirect = os.environ.get("SPOTIPY_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    masked = f"...{cur_secret[-4:]}" if cur_secret else "(vazio)"

    print("\nDeixe em branco para manter o valor atual.")
    client_id = input(f"Client ID [{cur_id or '(vazio)'}]: ").strip() or cur_id
    client_secret = getpass(f"Client Secret [{masked}]: ").strip() or cur_secret
    redirect_uri = input(f"Redirect URI [{cur_redirect}]: ").strip() or cur_redirect

    if (client_id, client_secret, redirect_uri) == (cur_id, cur_secret, cur_redirect):
        print("Nada alterado.")
        return
    write_env(client_id, client_secret, redirect_uri)
    # tokens emitidos para as chaves antigas deixam de valer
    remove_all_accounts()
    print("Chaves atualizadas no .env - as contas foram desconectadas, conecte novamente.")


# ---------- contas conectadas ----------

def load_index():
    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_index(index):
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def account_cache_path(user_id):
    return os.path.join(ACCOUNTS_DIR, f"{user_id}.json")


def list_accounts():
    """[(user_id, nome)] das contas conectadas, sem chamadas de rede."""
    index = load_index()
    accounts = []
    if os.path.isdir(ACCOUNTS_DIR):
        for filename in sorted(os.listdir(ACCOUNTS_DIR)):
            if filename.endswith(".json") and filename != "index.json":
                user_id = filename[:-5]
                accounts.append((user_id, index.get(user_id, user_id)))
    return accounts


def client_for(user_id):
    env_configured()  # garante o .env carregado quando usado como biblioteca
    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(scope=SCOPE, cache_path=account_cache_path(user_id)),
        retries=5,
    )


def connect_new_account():
    """Conecta uma conta e retorna (id, nome). show_dialog forca a tela de
    autorizacao, permitindo trocar de conta mesmo com sessao ativa no navegador."""
    if not env_configured():
        wizard()
        return None
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    pending = os.path.join(ACCOUNTS_DIR, ".pending.json")
    if os.path.exists(pending):
        os.remove(pending)

    print("Abrindo o navegador... Se aparecer a conta errada, use 'Nao e voce?' na tela do Spotify.")
    auth = SpotifyOAuth(scope=SCOPE, cache_path=pending, show_dialog=True)
    me = spotipy.Spotify(auth_manager=auth, retries=5).current_user()

    os.replace(pending, account_cache_path(me["id"]))
    index = load_index()
    index[me["id"]] = me.get("display_name") or me["id"]
    save_index(index)
    print(f"Conectada: {index[me['id']]} (id: {me['id']})")
    return me["id"], index[me["id"]]


def remove_account(user_id):
    path = account_cache_path(user_id)
    if os.path.exists(path):
        os.remove(path)
    index = load_index()
    index.pop(user_id, None)
    save_index(index)


def remove_all_accounts():
    for user_id, _ in list_accounts():
        remove_account(user_id)
    if os.path.exists(LEGACY_CACHE):
        os.remove(LEGACY_CACHE)


def migrate_legacy_cache():
    """Aproveita o login unico das versoes anteriores (arquivo de cache antigo)."""
    if not os.path.exists(LEGACY_CACHE) or not env_configured():
        return
    try:
        auth = SpotifyOAuth(scope=SCOPE, cache_path=LEGACY_CACHE)
        token = auth.validate_token(auth.cache_handler.get_cached_token())
        if token:
            me = spotipy.Spotify(auth=token["access_token"]).current_user()
            os.makedirs(ACCOUNTS_DIR, exist_ok=True)
            os.replace(LEGACY_CACHE, account_cache_path(me["id"]))
            index = load_index()
            index[me["id"]] = me.get("display_name") or me["id"]
            save_index(index)
            return
    except Exception:
        pass
    os.remove(LEGACY_CACHE)
    print("O login salvo pela versao anterior expirou - conecte a conta novamente.")


def choose_account(title, exclude=None):
    """Menu numerado de contas; retorna (id, nome) ou None se cancelado."""
    while True:
        accounts = [a for a in list_accounts() if a[0] != exclude]
        if not accounts:
            print("\nNenhuma conta conectada disponivel para esta etapa.")
            if ask_yes("Conectar uma conta agora?"):
                connect_new_account()
                continue
            return None
        print(f"\n{title}")
        for i, (user_id, name) in enumerate(accounts, 1):
            print(f"  {i}. {name} (id: {user_id})")
        print("  c. Conectar outra conta")
        choice = read_input("Escolha: ")
        if choice is None or choice == "":
            return None
        if choice.lower() == "c":
            connect_new_account()
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(accounts):
            return accounts[int(choice) - 1]
        print("Opcao invalida.")


def manage_accounts():
    while True:
        accounts = list_accounts()
        print("\n--- Contas conectadas ---")
        if accounts:
            for i, (user_id, name) in enumerate(accounts, 1):
                print(f"  {i}. {name} (id: {user_id})")
        else:
            print("  (nenhuma)")
        print("\n  c. Conectar nova conta")
        print("  r. Remover conta")
        print("  0. Voltar")
        choice = read_input("\nEscolha: ")
        if choice is None or choice == "0":
            return
        if choice.lower() == "c":
            connect_new_account()
        elif choice.lower() == "r" and accounts:
            number = read_input("Numero da conta a remover: ")
            if number and number.isdigit() and 1 <= int(number) <= len(accounts):
                user_id, name = accounts[int(number) - 1]
                remove_account(user_id)
                print(f"Removida: {name}. Para revogar o acesso de vez, use spotify.com/account/apps")
            else:
                print("Numero invalido.")
        else:
            print("Opcao invalida.")


# ---------- leitura da biblioteca de uma conta (API) ----------

def paginate(fetch_page):
    """Itera os itens de um endpoint paginado por offset."""
    offset = 0
    while True:
        page = fetch_page(offset)
        items = page.get("items", [])
        if not items:
            return
        yield from items
        offset += len(items)
        if page.get("next") is None:
            return


def playlist_item_node(item):
    # a API de fev/2026 renomeou o campo 'track' de cada item para 'item'
    return item.get("item") or item.get("track") or {}


def fetch_liked_track_ids(sp):
    ids = []
    for item in paginate(lambda o: sp.current_user_saved_tracks(limit=50, offset=o)):
        node = item.get("track") or item.get("item") or {}
        if node.get("id") and not node.get("is_local"):
            ids.append(node["id"])
    return ids  # mais recentes primeiro, como no CSV do TuneMyMusic


def fetch_playlist_track_ids(sp, playlist_id):
    ids = []
    for item in paginate(lambda o: sp.playlist_items(
            playlist_id, limit=100, offset=o, additional_types=["track"])):
        node = playlist_item_node(item)
        if node.get("id") and not node.get("is_local"):
            ids.append(node["id"])
    return ids


def fetch_playlists(sp, owner_id):
    """Separa playlists proprias (serao recriadas) das de terceiros (serao seguidas)."""
    own, followed = {}, []
    for pl in list(paginate(lambda o: sp.current_user_playlists(limit=50, offset=o))):
        if (pl.get("owner") or {}).get("id") == owner_id:
            try:
                own[pl["name"]] = fetch_playlist_track_ids(sp, pl["id"])
            except spotipy.SpotifyException as e:
                failures.append(f"[origem] falha ao ler playlist '{pl['name']}': {e}")
        else:
            followed.append((pl["id"], pl["name"]))
    return own, followed


def fetch_saved_album_ids(sp):
    ids = []
    for item in paginate(lambda o: sp.current_user_saved_albums(limit=50, offset=o)):
        node = item.get("album") or item.get("item") or {}
        if node.get("id"):
            ids.append(node["id"])
    return ids


def fetch_followed_artist_ids(sp):
    ids, after = [], None
    while True:
        page = sp.current_user_followed_artists(limit=50, after=after)["artists"]
        items = page.get("items", [])
        if not items:
            return ids
        ids.extend(a["id"] for a in items if a.get("id"))
        after = (page.get("cursors") or {}).get("after")
        if not after:
            return ids


# ---------- leitura do CSV (TuneMyMusic) ----------

def pick_csv_file():
    """Abre a janela do Explorador de Arquivos para o usuario escolher o CSV."""
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title="Selecione o CSV exportado pelo TuneMyMusic",
        filetypes=[("Arquivos CSV", "*.csv"), ("Todos os arquivos", "*.*")],
    )
    root.destroy()
    return path


def read_csv(path):
    favorites, albums, artists = [], [], []
    playlists = {}  # nome -> lista de track ids, na ordem do CSV
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            kind = (row.get("Type") or "").strip()
            spotify_id = (row.get("Spotify - id") or "").strip()
            # IDs validos do Spotify sao base62 com 22 caracteres; um ID invalido
            # (ex.: arquivo local) derruba o lote inteiro na API se nao for filtrado.
            if not re.fullmatch(r"[0-9A-Za-z]{22}", spotify_id):
                failures.append(f"[id invalido] {row.get('Artist name')} - {row.get('Track name')} "
                                f"({kind}, playlist: {row.get('Playlist name')}, id: {spotify_id!r})")
                continue
            if kind == "Favorite":
                favorites.append(spotify_id)
            elif kind == "Album":
                albums.append(spotify_id)
            elif kind == "Artist":
                artists.append(spotify_id)
            elif kind == "Playlist":
                name = (row.get("Playlist name") or "").strip() or "Sem nome"
                playlists.setdefault(name, []).append(spotify_id)
    return favorites, playlists, albums, artists


# ---------- gravacao na conta de destino ----------

def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def run_batches(items, size, action, label):
    done = 0
    for batch in chunks(items, size):
        try:
            action(batch)
            done += len(batch)
        except spotipy.SpotifyException as e:
            failures.append(f"[{label}] lote de {len(batch)} itens falhou: {e}")
        print(f"\r  {label}: {done}/{len(items)}", end="", flush=True)
    print()


def import_favorites(sp, track_ids):
    print(f"Importando {len(track_ids)} musicas curtidas...")
    # Adiciona em ordem invertida: o primeiro item (mais recente na origem)
    # e o ultimo a ser adicionado, ficando no topo das Liked Songs.
    run_batches(list(reversed(track_ids)), LIBRARY_BATCH,
                sp.current_user_saved_tracks_add, "curtidas")


def import_albums(sp, album_ids):
    print(f"Importando {len(album_ids)} albuns salvos...")
    run_batches(album_ids, LIBRARY_BATCH, sp.current_user_saved_albums_add, "albuns")


def import_artists(sp, artist_ids):
    print(f"Seguindo {len(artist_ids)} artistas...")
    run_batches(artist_ids, LIBRARY_BATCH, sp.user_follow_artists, "artistas")


def existing_playlist_names(sp):
    names = set()
    for pl in paginate(lambda o: sp.current_user_playlists(limit=50, offset=o)):
        names.add(pl["name"])
    return names


def import_playlists(sp, playlists):
    if not playlists:
        return
    print(f"Importando {len(playlists)} playlists...")
    existing = existing_playlist_names(sp)
    for name, track_ids in playlists.items():
        if name in existing:
            print(f"  Playlist '{name}' ja existe na conta - pulando (evita duplicar em re-execucoes).")
            continue
        try:
            playlist = sp.current_user_playlist_create(name, public=False)
        except spotipy.SpotifyException as e:
            failures.append(f"[playlist] falha ao criar '{name}': {e}")
            print(f"  Falha ao criar '{name}' - registrada e seguindo em frente.")
            continue
        uris = [f"spotify:track:{tid}" for tid in track_ids]
        run_batches(
            uris, 100,
            lambda batch, pid=playlist["id"]: sp.playlist_add_items(pid, batch),
            f"'{name}'",
        )


def follow_playlists(sp, playlists):
    """Segue na conta de destino as playlists de terceiros da origem."""
    if not playlists:
        return
    print(f"Seguindo {len(playlists)} playlists de terceiros...")
    for playlist_id, name in playlists:
        try:
            sp.current_user_follow_playlist(playlist_id)
            print(f"  seguindo: {name}")
        except spotipy.SpotifyException as e:
            failures.append(f"[seguir playlist] '{name}': {e}")


def report_failures():
    if failures:
        with open(FAILED_LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(failures))
        print(f"\nConcluido com {len(failures)} falhas - detalhes em {FAILED_LOG}")
    else:
        print("\nConcluido sem falhas!")


# ---------- fluxos ----------

def run_transfer():
    print("\nTransfere a biblioteca inteira de uma conta conectada para outra, direto pela API.")
    source = choose_account("Conta de ORIGEM (dona da biblioteca):")
    if not source:
        return
    dest = choose_account("Conta de DESTINO (recebe a biblioteca):", exclude=source[0])
    if not dest:
        return
    if not ask_yes(f"Transferir TUDO de '{source[1]}' para '{dest[1]}'?"):
        print("Cancelado.")
        return

    failures.clear()
    sp_source = client_for(source[0])
    print("\nLendo a biblioteca da origem (pode levar um tempo)...")
    favorites = fetch_liked_track_ids(sp_source)
    own_playlists, followed_playlists = fetch_playlists(sp_source, source[0])
    albums = fetch_saved_album_ids(sp_source)
    artists = fetch_followed_artist_ids(sp_source)
    playlist_tracks = sum(len(v) for v in own_playlists.values())
    print(f"Origem: {len(favorites)} curtidas, {len(own_playlists)} playlists proprias "
          f"({playlist_tracks} faixas), {len(followed_playlists)} playlists seguidas, "
          f"{len(albums)} albuns, {len(artists)} artistas.\n")

    sp_dest = client_for(dest[0])
    import_favorites(sp_dest, favorites)
    import_playlists(sp_dest, own_playlists)
    follow_playlists(sp_dest, followed_playlists)
    import_albums(sp_dest, albums)
    import_artists(sp_dest, artists)
    report_failures()


def run_import(csv_path=None, assume_yes=False):
    failures.clear()

    if csv_path is None:
        csv_path = pick_csv_file()
        if not csv_path:
            print("Nenhum arquivo selecionado - cancelado.")
            return
    if not os.path.isfile(csv_path):
        print(f"Arquivo nao encontrado: {csv_path}")
        return

    favorites, playlists, albums, artists = read_csv(csv_path)
    total_playlist_tracks = sum(len(v) for v in playlists.values())
    print(f"CSV lido: {len(favorites)} curtidas, {len(playlists)} playlists "
          f"({total_playlist_tracks} faixas), {len(albums)} albuns, {len(artists)} artistas.")

    accounts = list_accounts()
    if assume_yes and len(accounts) == 1:
        dest = accounts[0]
    else:
        dest = choose_account("Conta de DESTINO da importacao:")
    if not dest:
        return
    if not assume_yes and not ask_yes(f"Importar para '{dest[1]}' (id: {dest[0]})?"):
        print("Cancelado.")
        return

    sp = client_for(dest[0])
    import_favorites(sp, favorites)
    import_playlists(sp, playlists)
    import_albums(sp, albums)
    import_artists(sp, artists)
    report_failures()


def run_export():
    account = choose_account("Conta para exportar a biblioteca (.txt):")
    if not account:
        return
    import spotify_export
    spotify_export.export_all(client_for(account[0]), account[1])


def bootstrap_cli(flow):
    """Prepara o ambiente e roda um fluxo quando um script e executado direto
    (ex.: python spotify_export.py, python spotify_merge.py)."""
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    if not env_configured():
        wizard()
    migrate_legacy_cache()
    flow()


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    if env_configured():
        migrate_legacy_cache()

    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    positional = [a for a in args if not a.startswith("--")]

    if "--whoami" in flags:
        accounts = list_accounts()
        if not accounts:
            print("Nenhuma conta conectada.")
        for user_id, name in accounts:
            print(f"Conta conectada: {name} (id: {user_id})")
        return

    if args:  # modo direto, sem menu (automacao / linha de comando)
        if not env_configured():
            wizard()
        run_import(positional[0] if positional else None, assume_yes="--yes" in flags)
        return

    # sem argumentos: abre o menu (mantem `python spotify_import.py` funcionando)
    from spotify_menu import main as menu_main
    menu_main()


if __name__ == "__main__":
    main()
