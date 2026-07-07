#!/bin/bash
# Runs once on first postgres startup (docker-entrypoint-initdb.d).
# Creates the pgvector extension in the app database and a separate
# database for Langfuse v3 in the same instance.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE DATABASE ${LANGFUSE_DB:-langfuse} OWNER $POSTGRES_USER;
EOSQL
