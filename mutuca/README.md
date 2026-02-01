# Mutuca

Mutuca é uma plataforma open source dedicada à coleta, tratamento e disponibilização de dados
públicos de municípios do interior do Nordeste brasileiro.

Nosso objetivo é facilitar o acesso à informação pública por meio da automação e padronização de
dados que, embora disponíveis em portais oficiais, muitas vezes estão em formatos fragmentados,
inconsistentes ou de difícil análise. A Mutuca busca tornar esses dados mais acessíveis,
compreensíveis e úteis para jornalistas, pesquisadores, organizações da sociedade civil e cidadãos
interessados em acompanhar e fiscalizar a gestão pública local.

**O que a Mutuca faz**:

- Coleta dados de fontes públicas e oficiais;

- Realiza limpeza, transformação e padronização dos dados;

- Disponibiliza os conjuntos de dados em formatos reutilizáveis;

- Documenta metodologias e processos para facilitar a reprodutibilidade.

Nos alinhamos aos princípios da
[Lei de Acesso à Informação (Lei nº 12.527/2011)](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm)
e da
[Lei da Transparência (Lei Complementar nº 131/2009)](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp131.htm),
reforçando o papel da sociedade civil no monitoramento das políticas públicas e no fortalecimento da
democracia.

## Código aberto

A Mutuca é um projeto inteiramente open source. Todo o código, pipelines, metodologias e
documentações estão disponíveis neste repositório para consulta, reutilização e colaboração.
Acreditamos que a abertura do conhecimento é essencial para criar soluções mais robustas,
sustentáveis e conectadas com as necessidades reais de cada território.

---

## Requisitos

- [Python 3.10+](https://www.python.org/downloads/)
- [Poetry](https://python-poetry.org/docs/)
- Git
- (Opcional) Docker, para execução via containers

---

## Instalação

1. Clone o repositório:

```bash
git clone https://github.com/seu-usuario/mutuca.git
cd mutuca
```

2. Instale as dependencia com poetry:

```bash
poetry install
```

3. Ative o ambiente virtual:

```bash
poetry shell
```

4. Configure as variáveis de ambiente:

```bash
cp .env_example .env
```

---

## Estrutura do projeto

```
TODO
```

---

## Acessando a documentação localmente

```bash
# Na raiz do projeto:
mkdocs serve
```

---

## Como Contribuir

- Faça um fork deste repositório;

- Crie uma branch para sua feature ou correção (git checkout -b minha-feature);

- Faça commit das suas alterações (git commit -m 'Adiciona minha feature');

- Envie sua branch (git push origin minha-feature);

- Abra um Pull Request.

Siga as boas práticas de codificação, adicione testes sempre que necessário e descreva claramente o
que está sendo proposto.
