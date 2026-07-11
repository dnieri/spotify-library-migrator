"""
Exporta a biblioteca de uma conta Spotify para arquivos .txt no formato
"Artista - Musica" (um arquivo por playlist + um para as curtidas) - util para
importar em servicos que aceitam texto, como o TuneMyMusic (origem "File").

Os arquivos ficam em exports/<nome da conta>/.

Rode pelo menu do app (python spotify_import.py, opcao 3) ou direto:
    python spotify_export.py
"""

import os
import re

import spotipy


EXPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")


def sanitize_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return name or "sem_nome"


def track_line(node):
    if not node:
        return None
    artists = ", ".join(a["name"] for a in node.get("artists", []) if a.get("name"))
    title = node.get("name")
    if not artists or not title:
        return None
    return f"{artists} - {title}"


def write_lines(out_dir, filename, lines):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  -> {len(lines)} musicas salvas em {path}")


def export_liked_songs(sp, out_dir):
    from spotify_import import paginate

    print("Exportando musicas curtidas...")
    lines = []
    for item in paginate(lambda o: sp.current_user_saved_tracks(limit=50, offset=o)):
        line = track_line(item.get("track") or item.get("item"))
        if line:
            lines.append(line)
    write_lines(out_dir, "Liked Songs.txt", lines)


def export_playlists(sp, out_dir):
    from spotify_import import paginate, playlist_item_node

    print("Exportando playlists...")
    for playlist in list(paginate(lambda o: sp.current_user_playlists(limit=50, offset=o))):
        print(f"  Playlist: {playlist['name']}")
        lines = []
        try:
            for item in paginate(lambda o: sp.playlist_items(
                    playlist["id"], limit=100, offset=o, additional_types=["track"])):
                line = track_line(playlist_item_node(item))
                if line:
                    lines.append(line)
        except spotipy.SpotifyException as e:
            # playlists editoriais do Spotify nao sao legiveis por apps em dev mode
            print(f"  (pulada: a API nao permite ler esta playlist - HTTP {e.http_status})")
            continue
        write_lines(out_dir, f"{sanitize_filename(playlist['name'])}.txt", lines)


def export_all(sp, account_label):
    out_dir = os.path.join(EXPORTS_DIR, sanitize_filename(account_label))
    export_liked_songs(sp, out_dir)
    export_playlists(sp, out_dir)
    print(f"\nArquivos gerados em: {out_dir}")


if __name__ == "__main__":
    from spotify_import import bootstrap_cli, run_export
    bootstrap_cli(run_export)
