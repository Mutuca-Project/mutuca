# 🐘 Motor de Consulta: Trino

> **Arquivos soltos no disco são apenas arquivos. O Trino é a mágica que faz o computador tratá-los como um Banco de Dados SQL infinito.**

O **Trino** é o cérebro da nossa arquitetura Lakehouse. Ele é um motor de consulta SQL distribuído, desenhado para rodar análises rápidas sobre grandes volumes de dados (Big Data) sem precisar importar esses dados para dentro dele.

## 📍 Papel na Arquitetura
Consulte a visão global em [../../README.md](../../README.md).

No **Mutuca Platform**, o Trino ocupa o centro do palco:
1.  **Lê Metadados:** Consulta o **Nessie** para saber quais tabelas existem e qual é a versão mais recente (commit) de cada uma.
2.  **Lê Dados:** Vai até o **MinIO**, abre os arquivos `.parquet` ou `.json`, e extrai apenas as colunas necessárias.
3.  **Processa:** Executa filtros (`WHERE`), agregações (`GROUP BY`) e junções (`JOIN`) usando memória RAM.
4.  **Entrega:** Devolve o resultado via protocolo JDBC para o **dbt** (para transformação) ou para o **DBeaver** (para análise humana).

**Fluxo:** `Nessie (Mapa)` + `MinIO (Arquivos)` → **`Trino (Processamento)`** → `Analista/dbt`

## 🛠 Por que Trino e não Postgres?
Para jornalismo de dados massivo (ex: Folha de Pagamento do funcionalismo, Censo, CADSUS), bancos tradicionais como Postgres ficam caros e lentos.

1.  **Desacoplamento Computação/Armazenamento:**
    * Se o disco encher (muitos dados), aumentamos o MinIO (barato).
    * Se a consulta ficar lenta, aumentamos o Trino (CPU/RAM).
    * Isso economiza recursos preciosos em redações pequenas.
2.  **Federação de Dados:** O Trino consegue cruzar, em uma única query SQL, uma tabela do Data Lake com uma planilha Google Sheets e um banco MySQL legado.
3.  **Velocidade:** Projetado pelo Facebook para processar Petabytes, ele lida com Gigabytes de dados cívicos em segundos.

## 📂 Estrutura de Configuração

O Trino é configurado via arquivos `.properties`. No Mutuca, otimizamos essas configurações para rodar em hardware limitado (16GB RAM total).

```
infrastructure/trino/
├── Dockerfile           # Imagem customizada (se houver plugins extras)
├── etc/
│   ├── node.properties  # Identidade do nó (worker/coordinator)
│   ├── jvm.config       # Configuração da Java Virtual Machine (RAM)
│   ├── config.properties# Portas e limites de memória por query
│   └── catalog/         # Conectores (Onde a mágica acontece)
│       ├── iceberg.properties # Conexão com Nessie + MinIO
│       └── system.properties  # Configurações internas

```

Destaques da Configuração (Hardware Modesto)

- jvm.config: Limitamos o Heap do Java (-Xmx4G) para garantir que o container não seja morto pelo `OOM Killer` do Linux, deixando espaço para o Airflow e MinIO.
- iceberg.properties: Aqui definimos que o catálogo é do tipo REST (apontando para o Nessie) e habilitamos o `fs.native-s3.enabled=true` para performance máxima ao ler do MinIO.

### ⚙️ Como Usar

1. Conectando via SQL Client (DBeaver)

O Trino expõe uma interface JDBC padrão.

- Host: localhost
- Port: 8080
- User: admin (ou qualquer nome, não há senha configurada na POC)
- Driver: Trino JDBC

2. Comandos Essenciais (Jornalismo de Dados)

Verificar quais branches de investigação existem: (Nota: Devido ao conector REST, usamos o script Python do Nessie para criar branches, mas podemos consultá-las aqui)
SQL

```sql
-- Viajar no tempo para ver os dados como eram ontem
SELECT * FROM iceberg.silver.licitacoes FOR VERSION AS OF TIMESTAMP '2026-02-05 10:00:00';

Criar uma tabela nova a partir de um CSV (via dbt é preferível, mas via SQL é possível):
SQL

CREATE TABLE iceberg.bronze.eleicoes_2024 (
    candidato VARCHAR,
    votos BIGINT
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['candidato']
);
```

### ⚠️ Riscos e Limitações (Troubleshooting)
Erro: "Query exceeded per-node user memory limit"
- Causa: Você tentou carregar dados demais para a memória RAM (ex: um ORDER BY gigante numa tabela de 50GB).
- Solução: Otimize a query. Use LIMIT, filtre colunas desnecessárias ou aumente a RAM no jvm.config (se tiver hardware sobrando).

Erro: "Access Denied" (S3/MinIO)

- Causa: O Trino não conseguiu autenticar no MinIO.
- Solução: Verifique se as variáveis AWS_ACCESS_KEY_ID estão sendo passadas corretamente no docker-compose.yml ou se estão hardcoded no iceberg.properties.

Para ver como o dbt usa o Trino para transformar dados, veja o README do dbt.
