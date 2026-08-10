# Liber PHP 8.2 (Docker)

Stack local para `projetos/liberSitemas/Liber` **sem alterar** `menu.php` / `menu_cliente.php`.

## O que o Docker resolve

| Problema | Solução no compose/proxy |
|----------|---------------------------|
| MySQL `localhost` vs container | `.env` + `liber_db_constants.php` (`DB_OPER_HOST=proxy-db`) |
| `$contaCliente` = `XXX` no Docker | `CT_CLIENTE=DAT` em `infra/conexoes/liberSistemas/DAT/.env` |
| Menu DAT chama URL de produção | `extra_hosts` + vhost SSL `liber.dalilatextil.com.br` → Apache local |
| Warnings PHP (`<br />`) quebram JSON/JS | `php/99-liber-docker.ini`: `display_errors=Off`, `log_errors=On` |

## O que continua no Liber (repositório)

Correções de código aceitas apenas em:

- `index.php` (não incluir endpoint AJAX no login; conexão antes do LiberTV)
- `main/genericos/obter_ip_cliente.php` (JSON só quando chamado direto)
- `main/genericos/Uteis.php` (assinatura PHP 8.2)

## Variável obrigatória

Copie `infra/docker/php82-apache/.env.example` para `.env` nesta pasta e defina **`LIBER_WORKSPACE`**: raiz do workspace (pasta que contém `infra/` e `projetos/`).

## Subir

```bash
cd infra/docker/php82-apache
docker compose up -d --build
```

Acesso: http://localhost:8080

| Cliente | Comando |
|---------|---------|
| DAT (default) | `docker compose up -d --build` |
| MQP | `docker compose -f docker-compose.yml -f docker-compose.mqp.yml up -d --build` |
| LAS (Gestão) | `docker compose -f docker-compose.yml -f docker-compose.las.yml up -d --build` |

Conexões por cliente em `infra/conexoes/liberSistemas/<CLIENTE>/.env` (`CT_CLIENTE`, `REMOTE_*`, `DB_OPER_*`).

Após mudanças no entrypoint/vhost: `docker compose up -d --build`

## Validar menu

```bash
curl -sk "https://liber.dalilatextil.com.br/Liber/menu_cliente.php?contaCliente=DAT" | head -c 120
```

Deve começar com `[{` (JSON), sem `<br />` antes.

## Logs PHP

```bash
docker exec liber_php82 tail -f /var/log/apache2/error.log
```
