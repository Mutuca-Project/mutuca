---
id: 069f1f67-3015-44b7-86ca-119016eec7b5
aliases:
tags:
  - mutuca/docs/arquitetura/runtime
created_at: 2026-01-06
status: aceito
description: Definição do runtime de infraestrutura
---
%%
last_modified:: `=dateformat(this.file.mtime, "dd-MM-yyyy")`
%%
___
## Context

O Projeto Mutuca visa equipar jornalistas de dados e redações independentes com um ambiente de Data Lakehouse funcional. O perfil operacional deste público envolve trabalho em hardware não-servidor (notebooks pessoais ou da redação), necessidade de trabalho offline (em campo) e colaboração ágil entre repórteres com diferentes níveis técnicos.

A infraestrutura precisa suportar a execução simultânea de ferramentas de engenharia (Trino, Airflow) sem exigir que o jornalista atue como administrador de sistemas (DevOps). Além disso, a **portabilidade** é essencial: um jornalista deve ser capaz de passar uma investigação inteira (código + infra) para um colega verificar ou continuar o trabalho em outra máquina sem configurações complexas ("works on my machine problem").

## Decision

### Monorepo

No jornalismo de dados e em investigações OSINT, a prova da origem do dado é tão importante quanto a manchete. Se um dado sobre segurança pública ou gastos cívicos for questionado, o jornalista precisa provar exatamente como o dado foi obtido e calculado.

Portanto, a decisão de arquitetural de adotar um monorepo impacta diretamente na velocidade, segurança e confiabilidade das investigações justificado aqui em 4 pontos:

#### 1. Reprodutibilidade e a "Trilha de Auditoria" Jornalística

Em um monorepo, um único **commit** no Git congela o estado de todo o  ecossistema naquele milissegundo. Se precisar reavaliar os dados de uma investigação de meses atrás, eu saberei exatamente:

- Qual era a lógica de extração.
- Quais eram as regras de transformação.
- Como a orquestração estava configurada. 

Tudo isso amarrado em um único histórico unificado. **Em repositórios separados, garantir que a versão X do extração estava rodando com a versão Y da transformação pode se tornar um pesadelo de rastreabilidade**.
    
#### 2. Mudanças Atômicas (Atomic Commits)

Sistemas de dados são altamente acoplados. Se a estrutura de um portal de transparência muda, o pipeline inteiro sente o impacto.

Imagine que um site público mudou o nome do campo de `valor_licitacao` para `vlr_final`.

- **Em múltiplos repositórios:** Precisaria abrir um Pull Request (PR) no repositório do extrator para ajustar o script, e _outro_ PR no repositório da ferramenta de transformação para ajustar o modelo da camada Silver. Se um for aprovado antes do outro, o pipeline quebra.
    
- **No Monorepo:** Eu ajusto o script do extrator e o `modelo_silver.sql` na mesma branch e faço um único PR. A mudança flui pela plataforma de ponta a ponta de forma atômica e segura. Essa é uma experiência que vivi na pele operando pipelines gigantes numa das maiores fintechs do país, a redução desse atrito de deploy é um alívio imenso nesse contexto.
    

#### 3. Fricção Zero para Colaboração Open-Source

Acredito que sistemas open-source focados em jornalismo e análise cívica dependem de adoção e colaboração ágil. Se outro desenvolvedor ou jornalista investigativo quiser rodar a plataforma na máquina dele, a barreira de entrada precisa ser mínima.

Com o monorepo, a instrução de onboarding se resume basicamente a dois passos:
1. `git clone URL`
2. `make up`
    
Não é necessário caçar dependências espalhadas por vários repositórios ou configurar acessos cruzados. Toda a infraestrutura e o código de negócio vivem sob o mesmo "teto", mas em seus próprios "quartos".

#### 4. Visão Sistêmica e Quebra de Silos

Ao abrir a pasta do projeto no VSCode, por exemplo, a pessoa usuária tem uma visão panóptica do fluxo de dados. Ela consegue pesquisar por um termo genérico, como "autor", e ver onde ele é extraído, onde ele é limpo e como o funciona o fluxo de orquestração. Isso facilita a documentação e diminui drasticamente o tempo necessário para depurar erros estruturais.

## Runtime local com Docker Compose  

Adotei o **Docker Compose** como runtime de infraestrutura para a fase POC.

O Docker Compose permite a definição declarativa de serviços interligados, oferecendo:

- **Baixíssimo Overhead:** Elimina a camada de virtualização de nós do Kubernetes, liberando RAM vital para processar bases de dados maiores (ex: folhas de pagamento, diários oficiais) em notebooks padrão.
- **Portabilidade de Investigação:** O arquivo `docker-compose.yml` atua como um "container" do ambiente de investigação. Basta compartilhar o repositório, e qualquer jornalista com Docker instalado pode replicar o ambiente exato da apuração.
- **Setup Rápido:** Um único comando (`docker compose up -d`) sobe toda a plataforma, **permitindo que o foco permaneça na apuração e não na infraestrutura**.

## Alternatives Considered

**Kind / Minikube (Kubernetes Local):**

- **Pros:** Aproximação real de produção Cloud-Native.
- **Cons:** Alto consumo de memória e complexidade de manutenção.
- **Rejeitado por:** A curva de aprendizado e o consumo de recursos criariam uma barreira de entrada para redações menores e jornalistas independentes.

**Instalação Bare-Metal (Local):**

- **Pros:** Performance nativa.
- **Cons:** Difícil de replicar em outras máquinas para _fact-checking_ ou colaboração.
- **Rejeitado por:** Viola o princípio de reprodutibilidade científica da investigação de dados.

## Consequences

**Positivos:**

- **Otimização de Hardware:** 16GB RAM suportam toda a stack, viabilizando o uso em computadores comuns de redação.
- **Reprodutibilidade:** Garante que o ambiente de análise de um repórter seja idêntico ao do editor ou checador de fatos.
- **Isolamento:** As ferramentas rodam isoladas do sistema operacional do jornalista, evitando conflitos com outras ferramentas de trabalho diário.

**Negativos:**
- Não suporta Alta Disponibilidade (HA), o que é aceitável para investigações assíncronas, mas limita o uso como servidor de aplicação pública em tempo real.

## Notes

Esta decisão prioriza a experiência do desenvolvedor/jornalista (DX) e a viabilidade econômica sobre a paridade com ambientes de produção em nuvem massiva.