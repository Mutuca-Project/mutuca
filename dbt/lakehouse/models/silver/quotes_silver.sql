{{ config(
    materialized='table',
    properties={
        'format': "'PARQUET'",
        'partitioning': "ARRAY['author_name']", 
        'sorted_by': "ARRAY['quote_text']"
    }
) }}

WITH source_data AS (
    SELECT
        texto,
        autor,
        tags,
        url_origem,
        ingestion_at,
        -- Cria um "deduplicador" pegando a ingestão mais recente de cada frase
        ROW_NUMBER() OVER (PARTITION BY texto, autor ORDER BY ingestion_at DESC) as row_num
    FROM {{ source('lakehouse', 'quotes') }}
)

SELECT
    texto as quote_text,
    autor as author_name,
    tags,
    url_origem as source_url,
    ingestion_at
FROM source_data
WHERE row_num = 1 -- Mantém apenas a versão mais recente
