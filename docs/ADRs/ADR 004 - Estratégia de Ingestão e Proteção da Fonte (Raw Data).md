## Context

A obtenção de dados no jornalismo investigativo frequentemente envolve raspagem (scraping) de
portais governamentais ou de empresas instáveis ou opacos. Há dois imperativos operacionais:

1. **Preservação da Prova:** O dado bruto (HTML, JSON original) deve ser salvo intocado para provar
   a origem da informação caso o site saia do ar ou altere os dados.
2. **Resiliência:** Scripts de raspagem falham frequentemente. Uma falha na coleta não pode derrubar
   o sistema de análise.

## Decision

Adotei o padrão **DooD (Docker-outside-of-Docker)** via Airflow para execução de Scrapers, salvando
dados crus em uma **Landing Zone (MinIO)**.

O Airflow orquestra containers efêmeros do Scrapy e do DBT acessando o socket do Docker do host
(`/var/run/docker.sock`). Os containers efêmeros rodam **fora** do container do Airflow — não dentro
dele. Cada container de coleta e transformação deposita o dado imediatamente no MinIO em seu formato
original antes de qualquer processamento, e é destruído em seguida (`auto_remove=True`).

No contexto do Mutuca, o DooD foi escolhido por três razões alinhadas aos princípios do projeto:

1. **Estabilidade operacional:** O DooD oferece isolamento de processo entre coleta e orquestração:
   o Scrapy roda em containers efêmeros e independentes, de forma que falhas ou picos de consumo na
   extração não afetam o Airflow nem o restante da stack. Além do mais, esse padrão é uma
   alternativa leve ao `KubernetesExecutor` do Airflow, que em produção em nuvem faria algo
   conceitualmente similar, mas com escalonamento real entre nós. No Mutuca, o DooD entrega o
   isolamento sem a complexidade e o consumo de memória do K8s, o que é exatamente o que o hardware
   de 16GB permite.

2. **Cadeia de custódia:** O isolamento entre o container do Airflow e os containers efêmeros do
   Scrapy/DBT garante que uma falha na coleta — travamento de memória, timeout, erro de rede — não
   contamina o ambiente de análise. O dado bruto é depositado no MinIO antes de qualquer
   processamento, preservando a prova original independentemente do que aconteça depois.

3. **Reprodutibilidade:** O socket `/var/run/docker.sock` é um recurso nativo de qualquer instalação
   Docker padrão. Qualquer jornalista que execute `make up` em sua máquina terá exatamente o mesmo
   comportamento, sem configurações adicionais de daemon ou permissões especiais.

> **Nota técnica:** DooD difere de um outro padrão conhecido como DinD (Docker-in-Docker). No DinD,
> um daemon Docker roda dentro de um container, o que introduz complexidade de permissões e riscos
> de segurança. No DooD, o container do Airflow apenas delega ao daemon Docker do host via socket,
> mantendo o controle centralizado no sistema operacional hospedeiro.

## Alternatives Considered

**Execução Local (PythonOperator):**

- **Pros:** Simples.
- **Cons:** Mistura o ambiente de coleta com o de análise. Se o scraper travar a memória, a análise
  para.
- **Rejeitado por:** Risco à estabilidade operacional.

**Processamento em Stream (Kafka):**

- **Pros:** Tempo real.
- **Cons:** Complexidade técnica excessiva para dados que geralmente são atualizados em batch
  (mensal, semanal, etc).
- **Rejeitado por:** Sobrecarga de engenharia desnecessária.

## Consequences

**Positivos:**

- **Cadeia de Custódia:** A separação clara entre "Landing Zone" (dado bruto/prova) e "Warehouse"
  (dado tratado) protege jornalistas e redações contra acusações de adulteração de dados.
- **Estabilidade:** Scrapers rodam em containers isolados; se um falhar, não afeta o restante do
  pipeline.
- **Auditoria:** O arquivo original baixado permanece disponível para verificação futura, mesmo que
  a metodologia de limpeza mude.

**Negativos:**

- Exige gerenciamento de imagens Docker para os scrapers.

## Notes

Esta decisão suporta o princípios jornalísticos da transparência, cuidado com fonte, armazenamento
de documentos originais e rastreabilidade.
