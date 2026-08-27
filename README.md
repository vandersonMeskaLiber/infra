# infra

Configuração de ambiente local LIBER: Docker, proxies e templates de conexão.

## Estrutura

| Pasta | Conteúdo |
|-------|----------|
| `docker/php82-apache/` | Imagem PHP 8.2 + Apache e `docker-compose` |
| `proxies/liberSistemas/` | Scripts de proxy (MySQL, ODBC) |
| `conexoes/liberSistemas/` | Templates `.env.example` por cliente (`DAT`, `MQP`, `APT`, …) |
| `worklog/` | Código do Worklog (presença Wi‑Fi + Cursor + apontamentos). Runtime em `~/.worklog` via `bash worklog/bin/install.sh` |

## Primeiro uso

1. **Docker** — copie o exemplo e ajuste o caminho do workspace:

   ```bash
   cp docker/php82-apache/.env.example docker/php82-apache/.env
   ```

2. **Conexões** — para cada cliente, copie os exemplos (arquivos começam com `.`):

   ```bash
   cp conexoes/liberSistemas/DAT/.env.example conexoes/liberSistemas/DAT/.env
   cp conexoes/liberSistemas/DAT/.env.odbc.example conexoes/liberSistemas/DAT/.env.odbc
   ```

   Repita em `MQP/` ou outros diretórios de cliente.

3. **MySQL remoto** — no `.env` do cliente, troque os placeholders:

   - `REMOTE_HOST` — host/IP do MySQL (não use `seu-host-remoto`)
   - `REMOTE_PORT` — porta real no servidor (ex.: `53306` para DAT)
   - `DB_OPER_PASSWORD` — senha do MySQL, se houver

   MySQL na própria máquina (fora do Docker): `REMOTE_HOST=host.docker.internal`

4. Suba os containers a partir de `docker/php82-apache/` (ver README da pasta).

## Git e arquivos ocultos

Pastas como `conexoes` usam arquivos `.env*`. O Git versiona normalmente; a interface web do GitHub **não** envia bem esses arquivos — use `git push` na linha de comando.

Arquivos `.env` e `.env.odbc` (sem `.example`) ficam fora do repositório por segurança.

No `worklog/`, versionar `config.example.json`; manter `config.json` e `logs/` locais (ver `worklog/.gitignore`).
