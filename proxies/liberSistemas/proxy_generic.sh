#!/bin/sh

echo "Iniciando proxy..."

echo "Destino: $REMOTE_HOST:$REMOTE_PORT"

exec socat TCP-LISTEN:3306,fork,reuseaddr TCP:$REMOTE_HOST:$REMOTE_PORT