# Spotify Library Migrator

Migre suas **músicas curtidas, playlists, álbuns salvos e artistas seguidos** de uma conta Spotify para outra.

Dois caminhos:

- **Transferência direta** entre duas contas conectadas ao app — sem arquivo intermediário.
- **Importação do CSV** exportado pelo [TuneMyMusic](https://www.tunemymusic.com) — útil quando a conta de origem não pode ser conectada. Como o CSV traz o **ID do Spotify** de cada item, a importação é exata, sem busca por nome.

## Passo 1 — Criar um app na API do Spotify

1. Acesse o [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) e crie um app.
   > ⚠️ Desde 2025, a conta **dona do app** precisa ter **assinatura Premium ativa**. As contas de origem/destino podem ser gratuitas.
2. Nas configurações do app, adicione a Redirect URI: `http://127.0.0.1:8888/callback`
3. Adicione o e-mail das contas que vão se conectar (origem e destino) em **Settings → User Management**, caso sejam diferentes da dona do app.
4. Copie o **Client ID** e o **Client Secret**.

## Passo 2 — Rodar

```bash
pip install -r requirements.txt
python spotify_menu.py
```

**Na primeira execução**, um assistente (wizard) pede o Client ID/Secret e **cria o `.env` automaticamente** — não precisa editar arquivo na mão. Nas execuções seguintes, abre o menu:

```
=== Spotify Library Migrator ===
Contas conectadas: Conta Antiga, Conta Nova

  1. Transferir biblioteca entre contas conectadas
  2. Importar CSV do TuneMyMusic
  3. Exportar biblioteca para .txt
  4. Mesclar playlists duplicadas
  5. Gerenciar contas (conectar / remover)
  6. Alterar chaves da API (.env)
  0. Sair
```

O menu (`spotify_menu.py`) é só o orquestrador — cada função vive no próprio script e também roda sozinha: `spotify_import.py` (transferência/importação), `spotify_export.py` (exportação .txt) e `spotify_merge.py` (mesclagem).

Você pode conectar **quantas contas quiser** (opção 4): cada login abre o navegador na tela de autorização do Spotify — use "Não é você?" para entrar com outra conta. Os tokens ficam guardados em `.accounts/`, um por conta.

### Transferência direta (opção 1)

Escolha a conta de **origem** e a de **destino** na lista de contas conectadas e confirme. O app lê tudo da origem pela API e grava no destino:

- Músicas curtidas (preservando a ordem)
- Playlists **suas** → recriadas como privadas no destino
- Playlists **de terceiros que você segue** → o destino passa a segui-las
- Álbuns salvos e artistas seguidos

### Importação por CSV (opção 2)

1. No [tunemymusic.com](https://www.tunemymusic.com): **Transferir** → origem **Spotify** (login na conta antiga) → marque playlists, Músicas Curtidas, álbuns e artistas → destino **Exportar para arquivo** → **CSV**. A exportação para arquivo é gratuita e sem limite de faixas.
2. No menu, escolha a opção 2 — uma **janela do Explorador de Arquivos** abre para você selecionar o CSV — e depois a conta de destino.

Também funciona pela linha de comando, sem menu:

```bash
python spotify_import.py "My Spotify Library.csv" --yes   # importa sem perguntar
python spotify_import.py --whoami                          # lista as contas conectadas
python spotify_import.py                                   # sem argumentos, abre o menu
```

### Exportação para .txt (opção 3)

Gera arquivos `Artista - Música` (um por playlist + um para as curtidas) em `exports/<conta>/` — úteis para importar em serviços que aceitam texto, como o próprio TuneMyMusic (origem "File"). Playlists editoriais do Spotify não são legíveis pela API em development mode e são puladas com aviso.

### Mesclagem de playlists duplicadas (opção 4)

Ficou com pares quase idênticos depois de uma migração (ex.: `Só Pagodão!` antiga e `Só Pagodão! :D` importada)? Escolha a playlist **antiga** (origem) e a **nova** (destino): as faixas que faltam são copiadas para a nova, preservando a ordem, e **a antiga é mantida intacta** — nada é apagado. Rodar de novo não duplica nada.

## O que é importado do CSV

| Tipo no CSV | Destino na conta nova |
|---|---|
| `Favorite` | Músicas Curtidas (na mesma ordem) |
| `Playlist` | Playlists recriadas como privadas |
| `Album` | Álbuns salvos na biblioteca |
| `Artist` | Artistas seguidos |

Proteções (valem para transferência e CSV): re-executar não duplica nada (curtidas são idempotentes e playlists existentes são puladas); IDs inválidos e arquivos locais são filtrados; falhas ficam registradas em `import_failures.txt` sem interromper o processo.

## Notas técnicas

- Compatível com a Web API do Spotify **pós-migração de fevereiro/2026** (spotipy ≥ 2.26): endpoint unificado `PUT /me/library` (máx. 40 URIs por chamada), criação de playlist via `POST /me/playlists`, campo `item` nos itens de playlist (antes `track`).
- Se preferir configurar manualmente, copie `.env.example` para `.env` e preencha. Nunca commite o `.env` nem a pasta `.accounts/` — ambos estão no `.gitignore`.

## Licença

[MIT](LICENSE)
