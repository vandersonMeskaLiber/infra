<?php
# Constantes de banco para Docker — lê DB_* do env (.env do compose)
# Carregado via auto_prepend antes de conexao/conexao.php

if (!defined('HOST_OPER')) {
    define('HOST_OPER', getenv('DB_OPER_HOST') ?: 'proxy-db');
}
if (!defined('USUARIO_OPER')) {
    define('USUARIO_OPER', getenv('DB_OPER_USER') ?: 'root');
}
if (!defined('SENHA_OPER')) {
    define('SENHA_OPER', getenv('DB_OPER_PASSWORD') ?: '');
}
if (!defined('BD_OPER')) {
    define('BD_OPER', getenv('DB_OPER_NAME') ?: 'dalila_appliber');
}

if (!defined('HOST_IOT')) {
    define('HOST_IOT', getenv('DB_IOT_HOST') ?: (getenv('DB_OPER_HOST') ?: 'proxy-db'));
}
if (!defined('USUARIO_IOT')) {
    define('USUARIO_IOT', getenv('DB_IOT_USER') ?: (getenv('DB_OPER_USER') ?: 'root'));
}
if (!defined('SENHA_IOT')) {
    define('SENHA_IOT', getenv('DB_IOT_PASSWORD') ?: (getenv('DB_OPER_PASSWORD') ?: ''));
}
if (!defined('BD_IOT')) {
    define('BD_IOT', getenv('DB_IOT_NAME') ?: (getenv('DB_OPER_NAME') ?: 'dalila_appliber'));
}
