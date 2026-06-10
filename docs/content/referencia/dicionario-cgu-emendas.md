# Dicionário de dados — Emendas Parlamentares (CGU)

Descrição de todos os campos da tabela `bronze.cgu_emendas_parlamentares`.

**Tabela:** `iceberg.bronze.cgu_emendas_parlamentares`
**Granularidade:** um registro por documento de execução (OB, NE ou NS) por emenda parlamentar.

Uma mesma emenda gera múltiplos registros — um para cada documento do seu ciclo orçamentário: Empenho → Liquidação → Pagamento. Para analisar no nível da emenda, agrupe por `codigo_emenda`. Para rastrear recursos ao beneficiário final, filtre `fase_documento = 'Pagamento'` e use o campo `favorecido`.

---

## Metadados de carga

| Campo | Tipo | Descrição |
|---|---|---|
| `data_extracao` | `TIMESTAMP WITH TIME ZONE` | Momento em que a linha foi carregada no Lakehouse. Gerado automaticamente pelo pipeline — não vem da fonte. |

---

## Campos da emenda (Endpoint A1)

Informações sobre a emenda em si. Esses campos se repetem para cada documento de execução.

| Campo | Tipo | Descrição |
|---|---|---|
| `autor` | `VARCHAR` | Código e nome do parlamentar. Ex: `3900 - ADRIANO DO BALDY`. Chave para cruzamento com dados eleitorais do TSE. |
| `codigo_emenda` | `VARCHAR` | Identificador numérico único da emenda (12 dígitos). Formato: ano(4) + código do parlamentar(5) + sequencial(3). Ex: `202639000008`. |
| `tipo_emenda` | `VARCHAR` | Descrição do tipo. Ex: `Emenda Individual - Transferência Especial`. |
| `sk_tipo_emenda` | `VARCHAR` | Código numérico do tipo. `2` = Individual, `3` = Bancada, `4` = Comissão, `5` = Relator. As do tipo `5` correspondem ao chamado "orçamento secreto". |
| `localidade_do_gasto` | `VARCHAR` | Destino declarado. Pode ser um município específico, uma UF, `MÚLTIPLO` ou `Nacional`. |
| `codigo_funcao` | `VARCHAR` | Código da função orçamentária. Ex: `10` (Saúde), `08` (Assistência Social), `12` (Educação). |
| `funcao` | `VARCHAR` | Nome da função orçamentária. |
| `codigo_subfuncao` | `VARCHAR` | Código da subfunção (3 dígitos). |
| `subfuncao` | `VARCHAR` | Nome da subfunção. Pode estar ausente em alguns registros da API. |
| `programa` | `VARCHAR` | Código e nome do programa orçamentário. |
| `acao` | `VARCHAR` | Código e nome da ação orçamentária. |
| `plano_orcamentario` | `VARCHAR` | Nome do plano orçamentário. |
| `numero_emenda` | `VARCHAR` | Número sequencial da emenda no exercício do parlamentar. Ex: `0008`. |
| `ano` | `VARCHAR` | Ano de exercício orçamentário. Ex: `2026`. |
| `valor_total_a1` | `VARCHAR` | Valor pago total consolidado da emenda. Formato brasileiro: `1.653.375,00`. |
| `valor_empenhado` | `VARCHAR` | Total empenhado. Formato brasileiro. |
| `valor_liquidado` | `VARCHAR` | Total liquidado. Formato brasileiro. |
| `valor_resto_inscrito` | `VARCHAR` | Restos a pagar inscritos. Formato brasileiro. |
| `valor_resto_cancelado` | `VARCHAR` | Restos a pagar cancelados. Formato brasileiro. |
| `valor_resto_pago` | `VARCHAR` | Restos a pagar efetivamente pagos. Formato brasileiro. |
| `possui_apoio_solicitante` | `VARCHAR` | Indica se a emenda tem apoiador ou solicitante registrado. Valores: `Sim`, `Não`, `Não se aplica`. |

---

## Campos do documento de execução (Endpoint A2)

Informações sobre cada documento individual do ciclo orçamentário.

| Campo | Tipo | Descrição |
|---|---|---|
| `codigo_documento` | `VARCHAR` | Código resumido do documento. O prefixo indica o tipo: `NE` (Nota de Empenho), `NS` (Nota de Liquidação/Subempenho), `OB` (Ordem Bancária — pagamento efetivo). Ex: `2026OB456110`. |
| `fase_documento` | `VARCHAR` | Fase da execução: `Empenho`, `Liquidação` ou `Pagamento`. |
| `data_documento` | `VARCHAR` | Data de emissão do documento. Formato `DD/MM/AAAA`. |
| `favorecido` | `VARCHAR` | Beneficiário final no formato `CNPJ - NOME`. Ex: `04.786.328/0001-36 - FUNDO MUNICIPAL DE SAUDE`. Este é o campo central para o cruzamento com o Quadro de Sócios da Receita Federal e com os dados da ANATEL. |
| `valor_documento` | `VARCHAR` | Valor do documento específico. Formato brasileiro. |

---

## Observações para análise

**Sobre os valores monetários:** todos os campos de valor estão em formato brasileiro (ponto como separador de milhar, vírgula como separador decimal). Para operações matemáticas na camada Silver, converter removendo os pontos e substituindo a vírgula por ponto.

**Sobre o campo `favorecido`:** cerca de 9,4% dos registros do dump histórico 2018–2026 não seguem o padrão `CNPJ - NOME`. Nesses casos, o conteúdo pode ser um texto livre, um CPF ou uma indicação de favorecido coletivo. Tratar esses casos na camada Silver com uma coluna `favorecido_tipo` (`CNPJ`, `CPF`, `outro`).

**Sobre `sk_tipo_emenda = 5`:** emendas de relator têm rastreabilidade significativamente menor e podem ter centenas de beneficiários por emenda. O pipeline pagina completamente o endpoint A2 para esses casos, garantindo que todos os documentos sejam capturados.

**Para o match societário:** use documentos com `fase_documento = 'Pagamento'`, extraia os 14 dígitos numéricos de `favorecido` e cruze com a tabela `bronze.rfb_cnpj_estabelecimentos` pelo campo `cnpj_basico` (primeiros 8 dígitos) ou `cnpj_completo`.
