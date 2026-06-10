# Dicionários de Dados

Documentação de todos os campos das tabelas da camada Bronze do Lakehouse.

---

## `bronze.cgu_emendas_parlamentares`

**Pipeline:** [Emendas Parlamentares (CGU)](../pipelines/cgu_emendas.md)
**Tabela Iceberg:** `iceberg.bronze.cgu_emendas_parlamentares`
**Storage:** `s3://warehouse/bronze/cgu_emendas_parlamentares/`
**DDL:** `sql/create_tables_cgu_emendas.sql`

Granularidade: **um registro por documento de execução (OB/NE/NS) por emenda parlamentar**.

Uma mesma emenda aparece repetida em múltiplos registros — uma vez para cada documento gerado em seu ciclo de execução orçamentária (Empenho → Liquidação → Pagamento). Para análises no nível de emenda, agrupe por `codigo_emenda`.

---

### Metadados de carga

| Campo | Tipo | Descrição |
|---|---|---|
| `data_extracao` | `TIMESTAMP WITH TIME ZONE` | Timestamp UTC de quando a linha foi carregada pelo `iceberg_loader`. Adicionado automaticamente — não vem do spider. |

---

### Campos do Endpoint A1 — `/emendas/consulta/resultado`

Representam a emenda em si. Repetidos para cada documento do A2.

| Campo | Tipo | Descrição | Observações |
|---|---|---|---|
| `autor` | `VARCHAR` | Código + nome do parlamentar autor da emenda. Ex: `"3900 - ADRIANO DO BALDY"` | Chave para cruzamento com candidaturas TSE |
| `codigo_emenda` | `VARCHAR` | Código numérico de 12 dígitos que identifica a emenda. Ex: `"202639000008"` | Formato: AAAA + código_parlamentar(5) + sequencial(3). Valores não-numéricos (`S/I`, `REL. GERAL`) são filtrados pelo spider |
| `tipo_emenda` | `VARCHAR` | Descrição textual do tipo. Ex: `"Emenda Individual - Transferência Especial"` | Ver `sk_tipo_emenda` para o código numérico |
| `sk_tipo_emenda` | `VARCHAR` | Código numérico do tipo de emenda | `2` = Individual, `3` = Bancada, `4` = Comissão, `5` = Relator ("orçamento secreto") |
| `localidade_do_gasto` | `VARCHAR` | Município, UF, `"MÚLTIPLO"` ou `"Nacional"` | Usado como filtro no endpoint A2 |
| `codigo_funcao` | `VARCHAR` | Código de 2 dígitos da função orçamentária | Ex: `"10"` (Saúde), `"08"` (Assistência Social), `"12"` (Educação) |
| `funcao` | `VARCHAR` | Nome da função orçamentária | Ex: `"Saúde"`, `"Educação"`, `"Assistência Social"` |
| `codigo_subfuncao` | `VARCHAR` | Código de 3 dígitos da subfunção | Ex: `"302"` (Assistência hospitalar), `"244"` (Assistência Comunitária) |
| `subfuncao` | `VARCHAR` | Nome da subfunção orçamentária | Pode ser `NULL` em alguns registros da API |
| `programa` | `VARCHAR` | Código + nome do programa orçamentário | Ex: `"5118 - ATENCAO ESPECIALIZADA A SAUDE"` |
| `acao` | `VARCHAR` | Código + nome da ação orçamentária | Ex: `"2E90 - INCREMENTO TEMPORARIO AO CUSTEIO..."` |
| `plano_orcamentario` | `VARCHAR` | Nome do plano orçamentário | Geralmente repetição do nome da ação |
| `numero_emenda` | `VARCHAR` | Número sequencial da emenda dentro do exercício do parlamentar | Ex: `"0008"` |
| `ano` | `VARCHAR` | Ano de exercício orçamentário | Ex: `"2026"`. Converter para `INTEGER` na Silver |
| `valor_total_a1` | `VARCHAR` | Valor pago total da emenda no A1 | Formato BR: `"1.653.375,00"`. Converter para `DECIMAL` na Silver |
| `valor_empenhado` | `VARCHAR` | Valor total empenhado | Formato BR |
| `valor_liquidado` | `VARCHAR` | Valor total liquidado | Formato BR |
| `valor_resto_inscrito` | `VARCHAR` | Restos a pagar inscritos | Formato BR |
| `valor_resto_cancelado` | `VARCHAR` | Restos a pagar cancelados | Formato BR |
| `valor_resto_pago` | `VARCHAR` | Restos a pagar efetivamente pagos | Formato BR |
| `possui_apoio_solicitante` | `VARCHAR` | Se a emenda possui apoiador/solicitante | `"Sim"`, `"Não"` ou `"Não se aplica"` |

---

### Campos do Endpoint A2 — `/emendas/documentos-relacionados/resultado`

Representam cada documento de execução orçamentária vinculado à emenda.

| Campo | Tipo | Descrição | Relevância investigativa |
|---|---|---|---|
| `codigo_documento` | `VARCHAR` | Código resumido do documento. Ex: `"2026NE456110"`, `"2026OB123456"` | Prefixo indica o tipo: `NE` (Nota de Empenho), `NS` (Nota de Liquidação), `OB` (Ordem Bancária) |
| `fase_documento` | `VARCHAR` | Fase de execução orçamentária | `"Empenho"` → `"Liquidação"` → `"Pagamento"`. Documentos `OB` são o elo final do rastreamento |
| `data_documento` | `VARCHAR` | Data de emissão do documento | Formato `DD/MM/AAAA`. Converter para `DATE` na Silver |
| `favorecido` | `VARCHAR` | Beneficiário final no formato `"CNPJ - NOME"`. Ex: `"04.786.328/0001-36 - FUNDO MUNICIPAL DE SAUDE"` | **Campo central da investigação.** O CNPJ é a chave para o match societário com QSA da Receita Federal e dados da ANATEL. ~9,4% dos registros históricos não seguem o padrão CNPJ/CPF |
| `valor_documento` | `VARCHAR` | Valor do documento específico | Formato BR: `"500.000,00"`. Converter para `DECIMAL` na Silver |

---

### Notas para a camada Silver

Transformações necessárias ao promover Bronze → Silver:

- **Valores monetários** (`valor_*`): remover pontos, trocar vírgula por ponto, converter para `DECIMAL(18,2)`
- **`ano`**: converter para `INTEGER`
- **`data_documento`**: converter de `DD/MM/AAAA` para `DATE`
- **`sk_tipo_emenda`**: converter para `INTEGER`
- **`favorecido`**: separar CNPJ (primeiros 18 caracteres) do nome, normalizar para CNPJ sem formatação
- **`codigo_emenda`**: manter como `VARCHAR` também na Silver — chave de junção com outras tabelas
