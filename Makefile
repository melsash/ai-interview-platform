# ============================================================
# AI Interview Platform — Makefile
# ============================================================

.PHONY: help up down build logs ps shell-auth shell-assessment \
        migrate-auth migrate-assessment migrate-ai test lint clean

# Default target
help:
	@echo ""
	@echo "  AI Interview Platform — available commands"
	@echo ""
	@echo "  Infrastructure:"
	@echo "    make up              Start all services"
	@echo "    make up-infra        Start only DB/Redis/RabbitMQ"
	@echo "    make down            Stop all services"
	@echo "    make build           Rebuild all images"
	@echo "    make ps              Show running containers"
	@echo "    make logs            Tail all logs"
	@echo "    make logs s=auth     Tail specific service logs"
	@echo ""
	@echo "  Database:"
	@echo "    make migrate         Run all migrations"
	@echo "    make migrate-auth    Run auth service migrations"
	@echo "    make migrate-assess  Run assessment service migrations"
	@echo "    make migrate-ai      Run ai_worker migrations"
	@echo ""
	@echo "  Development:"
	@echo "    make shell s=auth    Open shell in service container"
	@echo "    make test            Run all tests"
	@echo "    make test s=auth     Run tests for specific service"
	@echo "    make lint            Run ruff linter on all services"
	@echo ""
	@echo "  Cleanup:"
	@echo "    make clean           Remove containers and volumes"
	@echo ""

# ------ Infrastructure ------

up:
	docker compose up -d
	@echo "✓ All services started"
	@echo "  Auth:        http://localhost:8001/docs"
	@echo "  Assessment:  http://localhost:8002/docs"
	@echo "  Notification:http://localhost:8003/docs"
	@echo "  RabbitMQ UI: http://localhost:15672"
	@echo "  Grafana:     http://localhost:3000"
	@echo "  Prometheus:  http://localhost:9090"

up-infra:
	docker compose up -d postgres_auth postgres_assessment postgres_ai redis rabbitmq
	@echo "✓ Infrastructure started"

down:
	docker compose down

build:
	docker compose build --no-cache

ps:
	docker compose ps

logs:
	@if [ -n "$(s)" ]; then \
		docker compose logs -f $(s); \
	else \
		docker compose logs -f; \
	fi

# ------ Migrations ------

migrate: migrate-auth migrate-assessment migrate-ai
	@echo "✓ All migrations applied"

migrate-auth:
	docker compose exec auth alembic upgrade head

migrate-assessment:
	docker compose exec assessment alembic upgrade head

migrate-ai:
	docker compose exec ai_worker alembic upgrade head

# Create new migration (usage: make migration s=auth msg="add users table")
migration:
	docker compose exec $(s) alembic revision --autogenerate -m "$(msg)"

# ------ Development ------

shell:
	docker compose exec $(s) /bin/bash

test:
	@if [ -n "$(s)" ]; then \
		docker compose exec $(s) pytest tests/ -v --tb=short; \
	else \
		docker compose exec auth pytest tests/ -v --tb=short; \
		docker compose exec assessment pytest tests/ -v --tb=short; \
		docker compose exec ai_worker pytest tests/ -v --tb=short; \
	fi

lint:
	@for svc in auth assessment ai_worker notification; do \
		echo "Linting $$svc..."; \
		docker compose exec $$svc ruff check app/ || true; \
	done

# ------ Cleanup ------

clean:
	docker compose down -v --remove-orphans
	@echo "✓ Containers and volumes removed"
