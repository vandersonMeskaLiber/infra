# Build context: raiz do workspace — LIBER_WORKSPACE (ver docker-compose.yml)
FROM php:8.2-apache

RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Drivers Cache/IRIS (reutiliza os do repositório Liber, sem alterar projetos/liberSitemas)
RUN mkdir -p /usr/cachesys/bin /usr/irisodbc/bin
COPY projetos/liberSitemas/Liber/drivers/libcacheodbc35.so /usr/cachesys/bin/libcacheodbc35.so
COPY projetos/liberSitemas/Liber/drivers/libirisodbc35.so /usr/irisodbc/bin/libirisodbc35.so
RUN chmod 755 /usr/cachesys/bin/libcacheodbc35.so /usr/irisodbc/bin/libirisodbc35.so

RUN printf '%s\n' \
    '[InterSystems ODBC]' \
    'Description=InterSystems Cache ODBC Driver' \
    'Driver=/usr/cachesys/bin/libcacheodbc35.so' \
    'FileUsage=1' \
    '' \
    '[InterSystems IRIS ODBC]' \
    'Description=InterSystems IRIS ODBC Driver' \
    'Driver=/usr/irisodbc/bin/libirisodbc35.so' \
    'FileUsage=1' \
    > /etc/odbcinst.ini

# odbc: PHP_ALWAYS_SHARED quebra build em imagens oficiais (php#103)
RUN docker-php-source extract \
    && { \
    echo 'AC_DEFUN([PHP_ALWAYS_SHARED],[])dnl'; \
    echo; \
    cat /usr/src/php/ext/odbc/config.m4; \
    } > /tmp/odbc_config.m4 \
    && mv /tmp/odbc_config.m4 /usr/src/php/ext/odbc/config.m4
RUN docker-php-ext-configure odbc --with-unixODBC=shared,/usr \
    && docker-php-ext-configure pdo_odbc --with-pdo-odbc=unixODBC,/usr \
    && docker-php-ext-install -j$(nproc) mysqli pdo pdo_mysql odbc pdo_odbc \
    && docker-php-source delete

RUN a2enmod rewrite ssl

# Logging de erros PHP no stderr (aparece em `docker logs`)
RUN { \
    echo 'log_errors=On'; \
    echo 'error_log=/proc/self/fd/2'; \
    echo 'display_errors=On'; \
    echo 'display_startup_errors=On'; \
    echo 'html_errors=On'; \
    echo 'error_reporting=E_ALL'; \
  } > /usr/local/etc/php/conf.d/99-liber-errors.ini

# Limites de upload (chat GESTAO / anexos MP4 etc. — alinhado ao upload.php 200MB)
RUN { \
    echo 'upload_max_filesize=200M'; \
    echo 'post_max_size=220M'; \
    echo 'max_file_uploads=50'; \
    echo 'memory_limit=256M'; \
    echo 'max_execution_time=300'; \
    echo 'max_input_time=300'; \
  } > /usr/local/etc/php/conf.d/98-liber-uploads.ini

WORKDIR /var/www/html
EXPOSE 80
