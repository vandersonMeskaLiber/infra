# Worklog — controle de presença + assuntos Cursor

Sistema local para presença Wi‑Fi, assuntos do Cursor e rascunho de apontamentos LAS.

## Duas pastas (importante no macOS)

| Pasta | Papel |
|-------|--------|
| `infra/worklog` (este repo) | Código versionado — **commitar aqui** |
| `~/.worklog` | Runtime (launchd, logs, `config.json`) — **fora de Documents** |

O `install.sh` publica o código do repo em `~/.worklog` e registra os agents.  
Atalho: `~/Documents/worklog` → `~/.worklog`.

> Por que não rodar direto de `Documents`? O launchd do macOS costuma falhar (`EX_CONFIG`) ao usar WorkingDirectory em pastas protegidas.

## Instalação

```bash
cd /Users/vandersonmeska/Documents/workspace/infra/worklog
cp -n config.example.json ~/.worklog/config.json 2>/dev/null || true
# ou deixe o install criar a partir do example
bash bin/install.sh
```

Painel: http://127.0.0.1:8765/

Depois de alterar código neste repo, rode de novo `bash bin/install.sh`.

## O que vai para o Git

Versionar:
- `bin/`, `launchd/`, `config.example.json`, `README.md`, `.gitignore`

Não versionar:
- `config.json` (senha/DB)
- `logs/`, `diario/`, `dashboard.html`

## O que faz

1. **Wi‑Fi** — presença na rede do escritório (em sleep o Mac não faz poll; ao acordar fora da rede, o `out` usa o último `last_office_seen`, não o horário do wake)  
2. **Presença manual** — chegada/saída editáveis no painel  
3. **Assuntos manuais** — reunião e outros blocos fora do Cursor (formulário no painel → `logs/assuntos_manuais.json`). Em sobreposição com o monitorado, **o manual prevalece** e o restante do assunto automático é ajustado (antes/depois).  
4. **Cursor** — hooks gravam prompts/sessões  
5. **Apontamentos** — rascunho → confirmar → LAS  
6. **Resumo diário** — `diario/YYYY-MM-DD.md` no runtime  

## Configuração

Edite `~/.worklog/config.json` (copie de `config.example.json`).

| Campo | Significado |
|-------|-------------|
| `office_ssids` / `office_gateways` | Detecção do escritório |
| `match_mode` | `any`, `ssid`, `gateway`, `all` |
| `apontamento.*` | Usuário LAS, chamado padrão, DB |
| `almoco` | Janela padrão de almoço |

## Comandos

```bash
bash bin/install.sh
bash bin/uninstall.sh
python3 ~/.worklog/bin/wifi_watch.py --once
python3 ~/.worklog/bin/daily_summary.py
```
