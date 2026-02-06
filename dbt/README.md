# 🧱 Módulo de Transformação: dbt (Data Build Tool)

> ** Dados brutos são apenas evidências potenciais. O dbt é onde transformamos esse potêncial em informação.**

Aqui reside a inteligência analítica da  **Plataforma Mutuca**. O dbt nos permite escrever transformações de dados usando SQL (com poderes de Jinja) e, crucialmente, testar se os dados fazem sentido.

## 📍 Papel na Arquitetura
Consulte a visão global em [../README.md](../README.md).

O dbt consome dados da camada **Bronze** (carregados pelo Scrapy/Nessie) e os refina:
* **Bronze → Silver:** Limpeza, deduplicação, padronização de nomes, tipagem de datas, etc.
* **Silver → Gold:** Agregações, somatórios, tabelas fatos/dimensões prontas para apuração.

## 🛡 Qualidade de Dados (Data Quality)
No jornalismo, publicar um dado errado destrói a reputação. O dbt no Mutuca aplica testes automáticos:
* `unique`: Garante que não duplicamos IDs de licitações públicas, por exemplo.
* `not_null`: Garante que campos críticos (ex: Valor da Licitação) existem.
* `relationships`: Garante integridade referencial entre tabelas.

Se um teste falha, o pipeline para e o editor de dados é avisado.

## 📂 Estrutura do Projeto

```
dbt/
├── dbt_project.yml    # Configuração do projeto
├── profiles.yml       # Conexão com o Trino (Configurada para Dev e Prod)
├── models/
│   ├── staging/       # (Bronze->Silver) Limpeza inicial
│   ├── marts/         # (Silver->Gold) Modelos de negócio/reportagem
│   └── schema.yml     # Documentação e Testes das colunas
└── macros/            # Funções SQL reutilizáveis
``` 

### ⚙️ Como Rodar

O dbt roda conectado ao Trino.

```bash
# Rodar todos os modelos
dbt run

# Rodar apenas a camada silver
dbt run --select staging

# Testar a integridade dos dados
dbt test
```
