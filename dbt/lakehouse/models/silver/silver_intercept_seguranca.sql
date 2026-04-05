{{ config(
    materialized='table',
    properties={
        "format": "'PARQUET'",
        "partitioning": "ARRAY['day(data_publicacao)']" 
    }
) }}

WITH source_data AS (
    SELECT * FROM {{ source('bronze', 'intercept_seguranca') }}
),

-- 1. Deduplicação: Garante que, se o robô raspar a mesma URL em dias diferentes
-- devido à paginação, manteremos apenas a versão mais recente.
deduplicated AS (
    SELECT 
        *,
        ROW_NUMBER() OVER (
            PARTITION BY url 
            ORDER BY data_extracao DESC
        ) AS rn
    FROM source_data
    WHERE url IS NOT NULL
),

-- 2. Limpeza e Tipagem: Usando funções nativas do Trino
cleaned AS (
    SELECT
        url,
        
        -- Limpeza de espaços em branco e quebras de linha nas extremidades
        trim(manchete) AS manchete,
        trim(lide) AS lide,
        
        -- Garante que autores nunca retorne nulo. Se for nulo, devolve um array vazio.
        COALESCE(autores, ARRAY[]) AS autores,
        
        -- Tenta converter a string ISO para o tipo Timestamp com Time Zone nativo.
        -- O try_cast evita que o pipeline quebre se uma matéria vier com a data corrompida.
        try_cast(data_publicacao AS TIMESTAMP WITH TIME ZONE) AS data_publicacao,
        
        trim(corpo_materia) AS corpo_materia,
        
        data_extracao
        
    FROM deduplicated
    WHERE rn = 1
)

SELECT * FROM cleaned
