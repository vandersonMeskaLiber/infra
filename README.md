# infra

Configuração de ambiente local LIBER: Docker, proxies e templates de conexão.

## Estrutura

| Pasta | Conteúdo |
|-------|----------|
| `docker/php82-apache/` | Imagem PHP 8.2 + Apache e `docker-compose` |
| `proxies/liberSistemas/` | Scripts de proxy (MySQL, ODBC) |
| `conexoes/liberSistemas/` | Templates `.env.example` por cliente (`DAT`, `MQP`, …) |

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

3. Suba os containers a partir de `docker/php82-apache/` (ver README da pasta).

## Git e arquivos ocultos

Pastas como `conexoes` usam arquivos `.env*`. O Git versiona normalmente; a interface web do GitHub **não** envia bem esses arquivos — use `git push` na linha de comando.

Arquivos `.env` e `.env.odbc` (sem `.example`) ficam fora do repositório por segurança.
