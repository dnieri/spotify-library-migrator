"""
Spotify Library Migrator - importa a biblioteca exportada pelo TuneMyMusic (CSV)
para a conta Spotify conectada:
- Musicas curtidas (Type=Favorite)  -> Liked Songs
- Playlists (Type=Playlist)         -> cria as playlists (privadas) e adiciona as faixas
- Albuns salvos (Type=Album)        -> Your Library > Albums
- Artistas seguidos (Type=Artist)   -> Following

Usa os IDs do Spotify presentes no CSV, entao nao ha busca por nome (sem erro de match).

Uso:
    python spotify_import.py                      (menu interativo; wizard na 1a execucao)
    python spotify_import.py caminho/arquivo.csv  (importa direto, sem menu)

Flags: --yes (pula a confirmacao de conta)  --whoami (so mostra a conta conectada)

Na primeira execucao o wizard pede o Client ID/Secret do seu app
(https://developer.spotify.com/dashboard) e grava tudo no .env automaticamente.
"""

import csv
import os
import re
import sys
from getpass import getpass

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

SCOPE = (
    "user-library-read user-library-modify "
    "playlist-read-private playlist-modify-private playlist-modify-public "
    "user-follow-modify"
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
CACHE_PATH = os.path.join(BASE_DIR, ".spotify_token_cache_import")
FAILED_LOG = os.path.join(BASE_DIR, "import_failures.txt")
ENV_VARS = ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI")
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"

failures = []


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
    disconnect_account()
    print(f"\nConfiguracao salva em {ENV_PATH}")

    if ask_yes("Conectar a conta do Spotify agora?"):
        connect_account()


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
    disconnect_account()  # o token da conta nao vale para chaves novas
    print("Chaves atualizadas no .env - conecte a conta novamente (opcao 3 do menu).")


def read_input(prompt):
    try:
        # remove espacos e o BOM que pipes do PowerShell injetam na 1a linha
        # (tanto como \ufeff quanto decodificado em cp1252: \xef\xbb\xbf)
        return input(prompt).strip().strip("\ufeff\u00ef\u00bb\u00bf")
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def ask_yes(question):
    answer = read_input(f"{question} (s/n) ")
    return answer is not None and answer.lower() in ("s", "sim", "y", "yes")


# ---------- conta conectada ----------

def auth_manager():
    return SpotifyOAuth(scope=SCOPE, cache_path=CACHE_PATH)


def get_client():
    if not env_configured():
        wizard()
    return spotipy.Spotify(auth_manager=auth_manager(), retries=5)


def connected_account():
    """Le a conta do token em cache, sem abrir o navegador. None se nao ha login."""
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        auth = auth_manager()
        token = auth.validate_token(auth.cache_handler.get_cached_token())
        if not token:
            return None
        return spotipy.Spotify(auth=token["access_token"]).current_user()
    except Exception:
        return None


def disconnect_account():
    if os.path.exists(CACHE_PATH):
        os.remove(CACHE_PATH)


def connect_account():
    disconnect_account()
    print("Abrindo o navegador para voce entrar na conta do Spotify...")
    me = get_client().current_user()
    print(f"Conectado como: {me.get('display_name')} (id: {me['id']})")
    return me


# ---------- leitura do CSV ----------

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


# ---------- importacao ----------

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


# PUT /me/library aceita no maximo 40 uris por chamada
LIBRARY_BATCH = 40


def import_favorites(sp, track_ids):
    print(f"Importando {len(track_ids)} musicas curtidas...")
    # Adiciona em ordem invertida: a primeira linha do CSV (mais recente na conta
    # antiga) e a ultima a ser adicionada, ficando no topo das Liked Songs.
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
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=50, offset=offset)
        items = page.get("items", [])
        if not items:
            break
        names.update(p["name"] for p in items)
        offset += len(items)
        if page.get("next") is None:
            break
    return names


def import_playlists(sp, playlists):
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
          f"({total_playlist_tracks} faixas), {len(albums)} albuns, {len(artists)} artistas.\n")

    sp = get_client()
    me = sp.current_user()
    print(f"Conta conectada: {me.get('display_name')} (id: {me['id']})")
    if not assume_yes and not ask_yes("Importar para ESTA conta?"):
        print("Cancelado. Use a opcao de trocar de conta se logou na conta errada.")
        return

    import_favorites(sp, favorites)
    import_playlists(sp, playlists)
    import_albums(sp, albums)
    import_artists(sp, artists)

    if failures:
        with open(FAILED_LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(failures))
        print(f"\nConcluido com {len(failures)} falhas - detalhes em {FAILED_LOG}")
    else:
        print("\nConcluido sem falhas!")


def run_export():
    import spotify_export
    sp = get_client()
    spotify_export.export_liked_songs(sp)
    spotify_export.export_playlists(sp)
    print(f"Arquivos .txt gerados em: {spotify_export.OUTPUT_DIR}")


# ---------- menu ----------

def menu():
    while True:
        me = connected_account()
        conta = f"{me.get('display_name')} (id: {me['id']})" if me else "nenhuma (use a opcao 3)"
        print("\n=== Spotify Library Migrator ===")
        print(f"Conta conectada: {conta}\n")
        print("  1. Importar biblioteca (CSV do TuneMyMusic)")
        print("  2. Exportar biblioteca da conta conectada (.txt)")
        print("  3. Conectar / trocar conta")
        print("  4. Alterar chaves da API (.env)")
        print("  0. Sair")
        choice = read_input("\nEscolha uma opcao: ")
        if choice is None or choice == "0":
            return
        if choice == "1":
            run_import()
        elif choice == "2":
            run_export()
        elif choice == "3":
            connect_account()
        elif choice == "4":
            edit_keys()
        else:
            print("Opcao invalida.")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    positional = [a for a in args if not a.startswith("--")]

    if "--whoami" in flags:
        me = get_client().current_user()
        print(f"Conta conectada: {me.get('display_name')} (id: {me['id']})")
        return

    if args:  # modo direto, sem menu (automacao / linha de comando)
        run_import(positional[0] if positional else None, assume_yes="--yes" in flags)
        return

    if not env_configured():
        wizard()  # primeira execucao: vai direto para a configuracao guiada
    menu()


if __name__ == "__main__":
    main()
