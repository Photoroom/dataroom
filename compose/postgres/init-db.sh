#!/bin/bash
set -e

# Name of your desired database
DB_NAME=dataroom

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE $DB_NAME'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec

    \c $DB_NAME;
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL
