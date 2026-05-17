{{ config(
    materialized='table',
    properties={
      "format": "'PARQUET'",
      "sorted_by": "ARRAY['author_name']"
    }
) }}

WITH source_data AS (
    -- Lê da tabela Bronze definida no sources.yml
    SELECT 
        texto as quote_text,
        autor as author_name,
        tags,
        url_origem,
        ingestion_at
    FROM {{ source('lakehouse', 'quotes') }}
),

deduplicated AS (
    SELECT 
        *,
        -- Cria um ranking para identificar duplicatas baseadas no texto e autor
        -- Se houver duplicata, pegamos a mais recente (ingestion_at desc)
        ROW_NUMBER() OVER (
            PARTITION BY quote_text, author_name 
            ORDER BY ingestion_at DESC
        ) as row_num
    FROM source_data
)

SELECT 
    quote_text,
    author_name,
    tags,
    url_origem,
    ingestion_at
FROM deduplicated
WHERE row_num = 1 -- Filtra apenas a primeira ocorrência (remove duplicatas)
