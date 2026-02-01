up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

status:
	docker compose ps --format "table {{.Name}}\t{{.State}}\t{{.Status}}\t{{.Ports}}"

clean-volumes:
	docker compose down -v
	@echo "⚠️ Volumes de dados removidos!"
