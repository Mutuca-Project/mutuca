# 🐙 Versionamento de Dados: Project Nessie

> **Se o Git permite versionar o código da reportagem, o Nessie permite versionar os fatos (dados) que a sustentam.**

O Nessie é o componente que diferencia o **Mutuca** de um Data Lake tradicional. Ele transforma o Data Lake em um repositório versionado, trazendo a semântica do Git para os dados.

## 📍 Papel na Arquitetura
Consulte a visão global em [../../README.md](../../README.md).

O Nessie atua como o **Catálogo** para o Apache Iceberg. Nenhuma leitura ou escrita acontece no Lake sem que o Nessie saiba. Isso garante consistência ACID e histórico imutável.

## 🕵️‍♂️ Contexto Jornalístico: Por que isso importa?

1.  **Proteção contra "Gaslighting" de Dados:** Se um portal apaga um registro de doação eleitoral, nós temos o *commit* anterior provando que ele existia.
2.  **Investigação Segura (Branches):** Um jornalista pode criar uma branch `investigacao-milicias` a partir dos dados principais, cruzar informações, deletar ruído e testar hipóteses sem afetar os dados de produção que alimentam os dashboards de análise ou interferir no desenvolvimento de outro membro da equipe.
3.  **Congelamento para Publicação (Tags):** Ao publicar uma matéria, estudo ou relatório, criamos uma Tag (ex: `feminicídios-2026`). Daqui a 10 anos, qualquer um pode restaurar o estado exato dos dados daquele dia.

## ⚙️ Operação Básica

Utilizamos um cliente Python customizado (localizado em `infrastructure/nessie/nessie_client.py`) para interagir com o Nessie, garantindo compatibilidade e estabilidade.

### Criando uma Branch para Investigação
```bash
# Cria uma cópia virtual dos dados chamada 'feature/analise-saude' baseada na 'main'
python infrastructure/nessie/nessie_client.py feature/analise-saude main
```

### Consultando via SQL (Trino)

No SQL, basta definir a sessão para navegar entre as realidades:
SQL

```sql
-- Viajar para a branch da investigação
SET SESSION iceberg.query_branch = 'feature/analise-saude';

-- Viajar no tempo (Time Travel)
SELECT * FROM iceberg.silver.contratos FOR VERSION AS OF TIMESTAMP '2026-01-01 12:00:00';
```

### Trabalho em progresso

Atualmente estou trabalhando em uma ferramenta de linha de comando que facilitará a interação e o fluxo de trabalho com Nessie.
