# Spotify Library Migrator

Migre suas **músicas curtidas, playlists, álbuns salvos e artistas seguidos** de uma conta Spotify para outra, usando o CSV exportado pelo [TuneMyMusic](https://www.tunemymusic.com) e a Web API do Spotify.

Como o CSV do TuneMyMusic já traz o **ID do Spotify** de cada item, a importação é exata — sem busca por nome e sem risco de importar a versão errada de uma música.

## Passo 1 — Exportar a biblioteca da conta antiga (TuneMyMusic)

1. Acesse [tunemymusic.com](https://www.tunemymusic.com) e clique em **Transferir**.
2. Em **Selecione a origem**, escolha **Spotify** e faça login com a **conta antiga**.
3. Marque tudo o que quiser migrar: playlists, **Músicas Curtidas** (Favorite Songs), álbuns e artistas.
4. Em **Selecione o destino**, escolha **Exportar para arquivo** → **CSV**.
5. Baixe o arquivo (ex.: `My Spotify Library.csv`). A exportação para arquivo é gratuita e sem limite de faixas.

## Passo 2 — Criar um app na API do Spotify

1. Acesse o [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) e crie um app.
   > ⚠️ Desde 2025, a conta **dona do app** precisa ter **assinatura Premium ativa**. A conta que recebe a biblioteca pode ser gratuita.
2. Nas configurações do app, adicione a Redirect URI: `http://127.0.0.1:8888/callback`
3. Se a conta de destino for diferente da dona do app, adicione o e-mail dela em **Settings → User Management**.
4. Copie o **Client ID** e o **Client Secret**.

## Passo 3 — Configurar e rodar

```bash
# 1. Instale as dependências
pip install -r requirements.txt

# 2. Crie o .env com suas credenciais
cp .env.example .env   # e preencha com Client ID/Secret

# 3. Rode a importação
python spotify_import.py
```

- Uma **janela do Explorador de Arquivos** abre para você escolher o CSV (ou passe o caminho direto: `python spotify_import.py "My Spotify Library.csv"`).
- O navegador abre para você autorizar o acesso — **entre com a conta de destino** (a nova).
- O script mostra qual conta está logada e pede confirmação antes de importar (use `--yes` para pular, e `--whoami` para só conferir a conta).

## O que é importado

| Tipo no CSV | Destino na conta nova |
|---|---|
| `Favorite` | Músicas Curtidas (na mesma ordem) |
| `Playlist` | Playlists recriadas como privadas |
| `Album` | Álbuns salvos na biblioteca |
| `Artist` | Artistas seguidos |

Proteções: re-executar não duplica nada (curtidas são idempotentes e playlists existentes são puladas); IDs inválidos (ex.: arquivos locais) são filtrados; falhas ficam registradas em `import_failures.txt` sem interromper o processo.

## Extra: exportar via API (sem TuneMyMusic)

O repositório também inclui `spotify_export.py`, que gera arquivos `.txt` (`Artista - Música`) das curtidas e playlists direto pela API — úteis para importar em outros serviços que aceitam texto.

## Notas técnicas

- Compatível com a Web API do Spotify **pós-migração de fevereiro/2026** (spotipy ≥ 2.26): endpoint unificado `PUT /me/library` (máx. 40 URIs por chamada), criação de playlist via `POST /me/playlists`.
- Nunca commite seu `.env` — ele está no `.gitignore`.

## Licença

[MIT](LICENSE)
