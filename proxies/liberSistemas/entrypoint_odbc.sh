#!/bin/bash
set -e

# Gera /etc/odbc.ini a partir de ODBC_1_*, ODBC_2_* no env (.env.odbc)
odbc_ini="/etc/odbc.ini"
first=1
for n in 1 2 3 4 5; do
  eval "dsn_name=\$ODBC_${n}_DSN_NAME"
  eval "driver=\$ODBC_${n}_DRIVER"
  eval "server=\$ODBC_${n}_SERVER"
  eval "database=\$ODBC_${n}_DATABASE"
  eval "uid=\$ODBC_${n}_UID"
  eval "pwd=\$ODBC_${n}_PWD"
  eval "port=\$ODBC_${n}_PORT"
  eval "namespace=\$ODBC_${n}_NAMESPACE"
  eval "protocol=\$ODBC_${n}_PROTOCOL"
  eval "query_timeout=\$ODBC_${n}_QUERY_TIMEOUT"
  eval "static_cursors=\$ODBC_${n}_STATIC_CURSORS"
  eval "trace=\$ODBC_${n}_TRACE"
  eval "tracefile=\$ODBC_${n}_TRACEFILE"
  eval "auth_method=\$ODBC_${n}_AUTH_METHOD"
  eval "security_level=\$ODBC_${n}_SECURITY_LEVEL"
  eval "spn=\$ODBC_${n}_SPN"
  eval "description=\$ODBC_${n}_DESCRIPTION"
  eval "tds_version=\$ODBC_${n}_TDS_VERSION"
  eval "encrypt=\$ODBC_${n}_ENCRYPT"
  eval "trust_server_cert=\$ODBC_${n}_TRUST_SERVER_CERT"
  [ -z "$dsn_name" ] && continue
  [ -n "$driver" ] || continue
  if [ "$first" -eq 1 ]; then
    first=0
    echo "[${dsn_name}]" > "$odbc_ini"
  else
    echo "" >> "$odbc_ini"
    echo "[${dsn_name}]" >> "$odbc_ini"
  fi
  echo "Driver = ${driver}" >> "$odbc_ini"

  if [ "$dsn_name" = "cache" ] || [ "$dsn_name" = "cacheiris" ]; then
    [ -n "$description" ] && echo "Description = ${description}" >> "$odbc_ini"
    [ -n "$server" ] && echo "Host = ${server}" >> "$odbc_ini"
    [ -n "$namespace" ] && echo "Namespace = ${namespace}" >> "$odbc_ini"
    [ -n "$uid" ] && echo "UID = ${uid}" >> "$odbc_ini"
    [ -n "$pwd" ] && echo "Password = ${pwd}" >> "$odbc_ini"
    [ -n "$port" ] && echo "Port = ${port}" >> "$odbc_ini"
  else
    echo "Server = ${server}" >> "$odbc_ini"
    [ -n "$port" ] && echo "Port = ${port}" >> "$odbc_ini"
    [ -n "$database" ] && echo "Database = ${database}" >> "$odbc_ini"
    [ -n "$uid" ] && echo "Uid = ${uid}" >> "$odbc_ini"
    [ -n "$pwd" ] && echo "Pwd = ${pwd}" >> "$odbc_ini"
    [ -n "$description" ] && echo "Description = ${description}" >> "$odbc_ini"
  fi

  [ -n "$protocol" ]       && echo "Protocol = ${protocol}" >> "$odbc_ini"
  [ -n "$query_timeout" ]  && echo "Query Timeout = ${query_timeout}" >> "$odbc_ini"
  [ -n "$static_cursors" ] && echo "Static Cursors = ${static_cursors}" >> "$odbc_ini"
  [ -n "$trace" ]          && echo "Trace = ${trace}" >> "$odbc_ini"
  [ -n "$tracefile" ]      && echo "TraceFile = ${tracefile}" >> "$odbc_ini"
  [ -n "$auth_method" ]    && echo "Authentication Method = ${auth_method}" >> "$odbc_ini"
  [ -n "$security_level" ] && echo "Security Level = ${security_level}" >> "$odbc_ini"
  [ -n "$spn" ]            && echo "Service Principal Name = ${spn}" >> "$odbc_ini"
  [ -n "$tds_version" ]    && echo "TDS_Version = ${tds_version}" >> "$odbc_ini"
  [ -n "$encrypt" ]        && echo "Encrypt = ${encrypt}" >> "$odbc_ini"
  [ -n "$trust_server_cert" ] && echo "TrustServerCertificate=${trust_server_cert}" >> "$odbc_ini"
done
[ -f "$odbc_ini" ] && chmod 644 "$odbc_ini"

if [ -f /proxy/apache/000-liber-docker.conf ]; then
  if [ ! -f /etc/ssl/certs/liber-docker.crt ]; then
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
      -keyout /etc/ssl/private/liber-docker.key \
      -out /etc/ssl/certs/liber-docker.crt \
      -subj "/CN=liber.dalilatextil.com.br" 2>/dev/null
    chmod 644 /etc/ssl/certs/liber-docker.crt
    chmod 600 /etc/ssl/private/liber-docker.key
  fi
  a2enmod rewrite alias headers >/dev/null 2>&1 || true
  cp /proxy/apache/000-liber-docker.conf /etc/apache2/sites-available/000-liber-docker.conf
  a2dissite 000-default >/dev/null 2>&1 || true
  a2ensite 000-liber-docker.conf >/dev/null 2>&1 || true
fi

exec apache2-foreground
