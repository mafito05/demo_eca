-- Se ejecuta una única vez, al inicializar el volumen de Postgres.
-- pgvector viene compilado en la imagen pgvector/pgvector, pero la extensión
-- hay que habilitarla explícitamente por base de datos.
CREATE EXTENSION IF NOT EXISTS vector;

-- Búsqueda por similitud de texto para el buscador del panel (no para RAG).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
