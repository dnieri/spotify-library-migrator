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

## Passo 3 — Rodar

```bash
pip install -r requirements.txt
python spotify_import.py
```

**Na primeira execução**, um assistente (wizard) pede o Client ID/Secret e **cria o `.env` automaticamente** — não precisa editar arquivo na mão. Nas execuções seguintes, abre um menu interativo:

```
=== Spotify Library Migrator ===
Conta conectada: Fulano (id: ...)

  1. Importar biblioteca (CSV do TuneMyMusic)
  2. Exportar biblioteca da conta conectada (.txt)
  3. Conectar / trocar conta
  4. Alterar chaves da API (.env)
  0. Sair
```

- Na importação, uma **janela do Explorador de Arquivos** abre para você escolher o CSV.
- O navegador abre para você autorizar o acesso — **entre com a conta de destino** (a nova).
- O script mostra qual conta está conectada e pede confirmação antes de importar.

Também dá para usar direto pela linha de comando, sem menu:

```bash
python spotify_import.py "My Spotify Library.csv" --yes   # importa sem perguntar
python spotify_import.py --whoami                          # só mostra a conta conectada
```

Se preferir configurar manualmente, copie `.env.example` para `.env` e preencha.

## O que é importado

| Tipo no CSV | Destino na conta nova |
|---|---|
| `Favorite` | Músicas Curtidas (na mesma ordem) |
| `Playlist` | Playlists recriadas como privadas |
| `Album` | Álbuns salvos na biblioteca |
| `Artist` | Artistas seguidos |

Proteções: re-executar não duplica nada (curtidas são idempotentes e playlists existentes são puladas); IDs inválidos (ex.: arquivos locais) são filtrados; falhas ficam registradas em `import_failures.txt` sem interromper o processo.

## Extra: exportar via API (sem TuneMyMusic)

A opção 2 do menu (ou o script `spotify_export.py`) gera arquivos `.txt` (`Artista - Música`) das curtidas e playlists direto pela API — úteis para importar em outros serviços que aceitam texto.

## Notas técnicas

- Compatível com a Web API do Spotify **pós-migração de fevereiro/2026** (spotipy ≥ 2.26): endpoint unificado `PUT /me/library` (máx. 40 URIs por chamada), criação de playlist via `POST /me/playlists`.
- Nunca commite seu `.env` — ele está no `.gitignore`.

## Licença

[MIT](LICENSE)
