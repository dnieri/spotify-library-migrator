"""
Importa a biblioteca exportada pelo TuneMyMusic (CSV) para a conta Spotify logada:
- Musicas curtidas (Type=Favorite)  -> Liked Songs
- Playlists (Type=Playlist)         -> cria as playlists (privadas) e adiciona as faixas
- Albuns salvos (Type=Album)        -> Your Library > Albums
- Artistas seguidos (Type=Artist)   -> Following

Usa os IDs do Spotify presentes no CSV, entao nao ha busca por nome (sem erro de match).

Uso:
    python spotify_import.py                      (abre janela para escolher o CSV)
    python spotify_import.py caminho/arquivo.csv

IMPORTANTE: na tela de autorizacao do navegador, entre com a CONTA NOVA (destino).
O script mostra qual conta esta logada e pede confirmacao antes de importar.
"""

import csv
import os
import re
import sys

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

SCOPE = (
    "user-library-read user-library-modify "
    "playlist-read-private playlist-modify-private playlist-modify-public "
    "user-follow-modify"
)
CACHE_PATH = ".spotify_token_cache_import"
FAILED_LOG = "import_failures.txt"

failures = []


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


def get_client():
    load_dotenv()
    required = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("Faltam variaveis no arquivo .env: " + ", ".join(missing))
        sys.exit(1)
    auth_manager = SpotifyOAuth(scope=SCOPE, cache_path=CACHE_PATH)
    return spotipy.Spotify(auth_manager=auth_manager, retries=5)


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


def main():
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    positional = [a for a in args if not a.startswith("--")]

    if "--whoami" in flags:
        sp = get_client()
        me = sp.current_user()
        print(f"Conta logada: {me.get('display_name')} (id: {me['id']})")
        return

    csv_path = positional[0] if positional else pick_csv_file()
    if not csv_path:
        print("Nenhum arquivo selecionado - cancelado.")
        sys.exit(0)
    if not os.path.isfile(csv_path):
        print(f"Arquivo nao encontrado: {csv_path}")
        sys.exit(1)

    favorites, playlists, albums, artists = read_csv(csv_path)
    total_playlist_tracks = sum(len(v) for v in playlists.values())
    print(f"CSV lido: {len(favorites)} curtidas, {len(playlists)} playlists "
          f"({total_playlist_tracks} faixas), {len(albums)} albuns, {len(artists)} artistas.\n")

    sp = get_client()
    me = sp.current_user()
    print(f"Conta logada: {me.get('display_name')} (id: {me['id']})")
    if "--yes" not in flags:
        answer = input("Importar para ESTA conta? (s/n) ").strip().lower()
        if answer not in ("s", "sim", "y", "yes"):
            print("Cancelado. Se logou na conta errada, apague o arquivo "
                  f"{CACHE_PATH} e rode de novo para refazer o login.")
            sys.exit(0)

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


if __name__ == "__main__":
    main()
