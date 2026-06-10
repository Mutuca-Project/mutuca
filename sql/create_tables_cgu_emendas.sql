-- =============================================================================
-- DDL — Tabela Bronze: Emendas Parlamentares (CGU / Portal da Transparência)
-- Catálogo: iceberg | Schema: bronze
--
-- EXECUTAR NO TRINO antes da primeira execução do DAG ingestao_cgu_emendas.
-- O iceberg_loader não cria tabelas automaticamente.
--
-- Convenções Bronze:
--   - Todas as colunas de negócio são VARCHAR — dado preservado exatamente
--     como veio da fonte. Coerção de tipos ocorre na camada Silver (dbt).
--   - data_extracao é TIMESTAMP WITH TIME ZONE, adicionada pelo iceberg_loader
--     no momento da carga (padrão uniforme em todos os pipelines do projeto).
--
-- Granularidade: um registro por documento (OB/NE/NS) por emenda parlamentar.
-- Fonte: endpoints A1 + A2 do Portal da Transparência da CGU.
--   A1: https://portaldatransparencia.gov.br/emendas/consulta/resultado
--   A2: https://portaldatransparencia.gov.br/emendas/documentos-relacionados/resultado
-- =============================================================================

CREATE TABLE IF NOT EXISTS iceberg.bronze.cgu_emendas_parlamentares (

    -- Metadados de carga (adicionado pelo iceberg_loader, não pelo spider)
    data_extracao               TIMESTAMP WITH TIME ZONE,

    -- -------------------------------------------------------------------------
    -- Campos do Endpoint A1 — /emendas/consulta/resultado
    -- Granularidade: uma emenda por linha no A1
    -- -------------------------------------------------------------------------
    autor                       VARCHAR,  -- código + nome do parlamentar autor
    codigo_emenda               VARCHAR,  -- chave primária da emenda (12 dígitos numéricos)
    tipo_emenda                 VARCHAR,  -- ex: "Emenda Individual - Transferência Especial"
    sk_tipo_emenda              VARCHAR,  -- código numérico do tipo (2=individual, 4=comissão, 5=relator)
    localidade_do_gasto         VARCHAR,  -- município, UF, "MÚLTIPLO" ou "Nacional"
    codigo_funcao               VARCHAR,  -- código de 2 dígitos da função orçamentária
    funcao                      VARCHAR,  -- ex: "Saúde", "Educação", "Assistência Social"
    codigo_subfuncao            VARCHAR,  -- código de 3 dígitos da subfunção
    subfuncao                   VARCHAR,  -- ex: "Atenção Básica", "Assistência Comunitária"
    programa                    VARCHAR,  -- código + nome do programa orçamentário
    acao                        VARCHAR,  -- código + nome da ação orçamentária
    plano_orcamentario          VARCHAR,  -- nome do plano orçamentário
    numero_emenda               VARCHAR,  -- número sequencial da emenda (ex: "0008")
    ano                         VARCHAR,  -- ano de exercício orçamentário
    valor_total_a1              VARCHAR,  -- valor pago total da emenda (formato BR: "1.234,56")
    valor_empenhado             VARCHAR,
    valor_liquidado             VARCHAR,
    valor_resto_inscrito        VARCHAR,
    valor_resto_cancelado       VARCHAR,
    valor_resto_pago            VARCHAR,
    possui_apoio_solicitante    VARCHAR,  -- "Sim", "Não" ou "Não se aplica"

    -- -------------------------------------------------------------------------
    -- Campos do Endpoint A2 — /emendas/documentos-relacionados/resultado
    -- Granularidade: um documento por linha (a emenda se repete por documento)
    -- -------------------------------------------------------------------------
    codigo_documento            VARCHAR,  -- código resumido do documento (ex: "2026NE456110")
    fase_documento              VARCHAR,  -- "Empenho" (NE) | "Liquidação" (NS) | "Pagamento" (OB)
    data_documento              VARCHAR,  -- data do documento no formato DD/MM/AAAA
    favorecido                  VARCHAR,  -- "CNPJ - NOME DO BENEFICIÁRIO" (destino final do recurso)
    valor_documento             VARCHAR   -- valor do documento (formato BR: "500.000,00")

)
WITH (
    format   = 'PARQUET',
    location = 's3://warehouse/bronze/cgu_emendas_parlamentares/'
);
