# =============================================================================
# Mutuca — Comandos principais
#
# Modos de armazenamento do MinIO:
#   make up      → armazenamento local (volume Docker gerenciado) — padrão
#   make up-hd   → armazenamento no HD externo (bind mount via MINIO_DATA_PATH)
#
# Para usar o modo HD, configure MINIO_DATA_PATH no .env e crie o diretório:
#   mkdir -p /media/seu-usuario/HD-externo/MINIO
# =============================================================================

up:
	docker compose up -d

up-hd:
	docker compose -f docker-compose.yml -f docker-compose.hd.yml up -d

down:
	docker compose down

logs:
	docker compose logs -f

status:
	docker compose ps --format "table {{.Name}}\t{{.State}}\t{{.Status}}\t{{.Ports}}"

clean-volumes:
	docker compose down -v
	@echo "Volumes de dados removidos."
