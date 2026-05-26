#!/bin/sh

echo "Iniciando proxy..."

if [ -z "$REMOTE_HOST" ] || [ "$REMOTE_HOST" = "seu-host-remoto" ]; then
  echo "ERRO: defina REMOTE_HOST em infra/conexoes/liberSistemas/<CLIENTE>/.env"
  echo "      (IP/hostname do MySQL acessível a partir do container; Mac local: host.docker.internal)"
  exit 1
fi

if [ -z "$REMOTE_PORT" ]; then
  echo "ERRO: defina REMOTE_PORT no mesmo .env"
  exit 1
fi

echo "Destino: $REMOTE_HOST:$REMOTE_PORT"

exec socat TCP-LISTEN:3306,fork,reuseaddr TCP:$REMOTE_HOST:$REMOTE_PORT