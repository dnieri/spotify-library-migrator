"""
Exporta as musicas curtidas e as playlists de uma conta Spotify para arquivos .txt,
no formato "Artista - Musica" (um arquivo por playlist), prontos para importar
em outra conta de streaming usando o TuneMyMusic (opcao de importacao por arquivo/CSV/TXT).

Configuracao necessaria (uma vez):
1. Crie um app em https://developer.spotify.com/dashboard
2. Adicione uma Redirect URI no app, por exemplo: http://127.0.0.1:8888/callback
3. Preencha o arquivo .env (na mesma pasta deste script) com suas credenciais:
     SPOTIPY_CLIENT_ID=seu_client_id
     SPOTIPY_CLIENT_SECRET=seu_client_secret
     SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
4. Instale as dependencias: pip install -r requirements.txt
5. Rode: python spotify_export.py

Na primeira execucao vai abrir o navegador para voce autorizar o acesso a sua conta.
"""

import os
import re
import sys

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

SCOPE = "user-library-read playlist-read-private playlist-read-collaborative"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")


def get_client():
    load_dotenv()

    required = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("Faltam variaveis no arquivo .env: " + ", ".join(missing))
        print("Veja as instrucoes no topo de spotify_export.py.")
        sys.exit(1)

    auth_manager = SpotifyOAuth(scope=SCOPE, cache_path=".spotify_token_cache")
    return spotipy.Spotify(auth_manager=auth_manager)


def sanitize_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return name or "sem_nome"


def track_line(track):
    if track is None:
        return None
    artists = ", ".join(a["name"] for a in track.get("artists", []) if a.get("name"))
    title = track.get("name")
    if not artists or not title:
        return None
    return f"{artists} - {title}"


def write_lines(filename, lines):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  -> {len(lines)} musicas salvas em {path}")


def export_liked_songs(sp):
    print("Exportando musicas curtidas...")
    lines = []
    offset = 0
    while True:
        page = sp.current_user_saved_tracks(limit=50, offset=offset)
        items = page.get("items", [])
        if not items:
            break
        for item in items:
            line = track_line(item.get("track"))
            if line:
                lines.append(line)
        offset += len(items)
        if page.get("next") is None:
            break
    write_lines("Liked Songs.txt", lines)


def export_playlists(sp):
    print("Exportando playlists...")
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=50, offset=offset)
        playlists = page.get("items", [])
        if not playlists:
            break
        for playlist in playlists:
            export_single_playlist(sp, playlist)
        offset += len(playlists)
        if page.get("next") is None:
            break


def export_single_playlist(sp, playlist):
    name = playlist.get("name", "Playlist")
    playlist_id = playlist["id"]
    print(f"  Playlist: {name}")

    lines = []
    offset = 0
    while True:
        page = sp.playlist_items(
            playlist_id,
            limit=100,
            offset=offset,
            fields="items(track(name,artists(name))),next",
            additional_types=["track"],
        )
        items = page.get("items", [])
        if not items:
            break
        for item in items:
            line = track_line(item.get("track"))
            if line:
                lines.append(line)
        offset += len(items)
        if page.get("next") is None:
            break

    filename = f"{sanitize_filename(name)}.txt"
    write_lines(filename, lines)


def main():
    sp = get_client()
    export_liked_songs(sp)
    export_playlists(sp)
    print(f"\nConcluido. Arquivos gerados em: {OUTPUT_DIR}")
    print("Agora importe cada .txt no TuneMyMusic escolhendo a origem 'File'.")


if __name__ == "__main__":
    main()
