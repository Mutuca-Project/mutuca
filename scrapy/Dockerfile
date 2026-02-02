FROM python:3.11-slim

# 1. Copia o binário do uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 2. Configurações de ambiente
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    # Adiciona o venv ao PATH imediatamente
    PATH="/app/.venv/bin:$PATH"

# 3. Copia apenas os arquivos de definição de dependência primeiro
# Se você não tiver o uv.lock, o Docker vai reclamar se tentarmos copiá-lo.
# Vamos copiar apenas o pyproject.toml por segurança, mas se tiver o lock, copie também.
COPY pyproject.toml ./

# 4. Instala as dependências
RUN uv sync --no-dev

# 5. Copia o código do projeto
# O .dockerignore que criamos vai impedir que a pasta .venv local venha junto
COPY . .

# Comando padrão
CMD ["scrapy", "list"]
