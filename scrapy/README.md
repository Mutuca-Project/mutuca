# 🕷 Módulo de Ingestão: Scrapy

> **A realidade é desestruturada. O Scrapy é a ferramenta para dar forma ao caos.**

Este diretório contém os *spiders* responsáveis por coletar dados da web. No contexto do **Mutuca**, o Scrapy é a principal porta de entrada dos dados brutos.

## 📍 Papel na Arquitetura
Consulte a visão global em [../README.md](../README.md).

O Scrapy é responsável pela etapa **Extract** (Extração). Ele não realiza limpezas nem transformações complexas; sua única missão é capturar o dado da fonte (HTML, API, PDF) e preservá-lo fielmente no Data Lake (MinIO) nos formatos JSON ou Parquet.

**Fluxo:** `Internet` → `Scrapy` → `MinIO (Bucket Bronze)`

## 🛠 Por que Scrapy?
Para jornalismo investigativo, ferramentas "no-code" de scraping raramente são suficientes. O Scrapy oferece:
1.  **Resiliência:** Lida bem com redes instáveis e portais governamentais lentos.
2.  **Assincronismo:** Alta performance para baixar milhares de dados.
3.  **Ecossistema Python:** Integração nativa com nossa stack de Engenharia de Dados.

## 📂 Estrutura do Diretório

```
scrapy/
├── scrapy.cfg          # Configuração do deploy
├── mutuca/
│   ├── items.py        # Definição dos campos (Schema on Read)
│   ├── middlewares.py  # Rotação de User-Agent, Proxies
│   ├── pipelines.py    # (Opcional) Processamento pré-upload
│   ├── settings.py     # Configurações globais (Throttling, MinIO keys)
│   └── spiders/        # Onde vivem os robôs
│       └── portal_transparencia.py

```

## ⚙️ Como Usar

### Desenvolvimento Local

Para criar ou testar um spider isoladamente:

```
# Instale as dependências
pip install -r requirements.txt

# Execute um spider e salve o output localmente para inspeção
scrapy crawl nome_do_spider -o teste.json
```

### Integração com o Lakehouse

Em produção (via Airflow), os spiders são configurados para usar o Feed Exporter do Scrapy, enviando os dados diretamente para o MinIO (S3 Compatible).
Certifique-se que o settings.py contém as credenciais corretas ou que elas sejam injetadas via variáveis de ambiente (AWS_ACCESS_KEY_ID, etc).
