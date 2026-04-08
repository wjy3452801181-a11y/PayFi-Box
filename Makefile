.PHONY: install install-web install-api install-contracts dev web web-start web-stop web-status web-logs api api-start api-stop api-status api-logs db db-down db-docker db-docker-down dev-db migrate seed reset-db lint test verify-api verify-seed verify-step7b verify-step7b-reset verify-execution-modes contract-compile contract-deploy-hashkey contract-test-idempotency

PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYTHON_BIN := $(VENV)/bin/python
WEB_PORT ?= 3000
WEB_LOG ?= /tmp/payfi_web.log
WEB_PID ?= /tmp/payfi_web.pid
WEB_START_TIMEOUT ?= 20
API_PORT ?= 8000
API_LOG ?= /tmp/payfi_api.log
API_PID ?= /tmp/payfi_api.pid
API_START_TIMEOUT ?= 20

install: install-api install-web

install-contracts:
	cd apps/contracts && npm install

install-web:
	npm install

install-api:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r apps/api/requirements.txt

dev: db
	npm run dev:all

web:
	npm run dev:web

web-start:
	@if lsof -i :$(WEB_PORT) >/dev/null 2>&1; then \
		echo "web already running on :$(WEB_PORT)"; \
	else \
		echo "starting web on :$(WEB_PORT)"; \
		cd '$(CURDIR)' && ./scripts/start_web_once.sh '$(CURDIR)' '$(WEB_LOG)' '$(WEB_PID)' '$(WEB_PORT)'; \
		sleep 2; \
		ok=1; \
		for attempt in $$(seq 1 $(WEB_START_TIMEOUT)); do \
			if curl -fsS "http://127.0.0.1:$(WEB_PORT)/" >/dev/null 2>&1 && \
			   curl -fsS "http://127.0.0.1:$(WEB_PORT)/balance" >/dev/null 2>&1 && \
			   curl -fsS "http://127.0.0.1:$(WEB_PORT)/mcp" >/dev/null 2>&1; then \
				ok=0; \
				break; \
			fi; \
			sleep 1; \
		done; \
		if [ $$ok -ne 0 ]; then \
			echo "web failed readiness checks"; \
			tail -n 80 $(WEB_LOG) || true; \
			exit 1; \
		fi; \
	fi
	@$(MAKE) web-status

web-stop:
	@if [ -f "$(WEB_PID)" ]; then \
		kill $$(cat "$(WEB_PID)") >/dev/null 2>&1 || true; \
		rm -f "$(WEB_PID)"; \
	fi
	@pkill -f "next start .*--port $(WEB_PORT)" >/dev/null 2>&1 || true
	@for pid in $$(lsof -t -i :$(WEB_PORT) 2>/dev/null); do \
		kill $$pid >/dev/null 2>&1 || true; \
	done
	@sleep 1
	@for pid in $$(lsof -t -i :$(WEB_PORT) 2>/dev/null); do \
		kill -9 $$pid >/dev/null 2>&1 || true; \
	done
	@echo "web stopped"

web-status:
	@if lsof -i :$(WEB_PORT) >/dev/null 2>&1; then \
		echo "web up on :$(WEB_PORT)"; \
		lsof -i :$(WEB_PORT); \
		echo "log: $(WEB_LOG)"; \
	else \
		echo "web down on :$(WEB_PORT)"; \
	fi

web-logs:
	@tail -n 120 $(WEB_LOG)

api:
	env -u DATABASE_URL npm run dev:api

api-start:
	@if lsof -i :$(API_PORT) >/dev/null 2>&1; then \
		echo "api already running on :$(API_PORT)"; \
	else \
		echo "starting api on :$(API_PORT)"; \
		cd '$(CURDIR)' && ./scripts/start_api_once.sh '$(CURDIR)' '$(API_LOG)' '$(API_PID)' '$(API_PORT)'; \
		sleep 2; \
		ok=1; \
		for attempt in $$(seq 1 $(API_START_TIMEOUT)); do \
			if curl -fsS "http://127.0.0.1:$(API_PORT)/health" >/dev/null 2>&1; then \
				ok=0; \
				break; \
			fi; \
			sleep 1; \
		done; \
		if [ $$ok -ne 0 ]; then \
			echo "api failed readiness checks"; \
			tail -n 80 $(API_LOG) || true; \
			exit 1; \
		fi; \
	fi
	@$(MAKE) api-status

api-stop:
	@if [ -f "$(API_PID)" ]; then \
		kill $$(cat "$(API_PID)") >/dev/null 2>&1 || true; \
		rm -f "$(API_PID)"; \
	fi
	@pkill -f "uvicorn app.main:app .*--port $(API_PORT)" >/dev/null 2>&1 || true
	@for pid in $$(lsof -t -i :$(API_PORT) 2>/dev/null); do \
		kill $$pid >/dev/null 2>&1 || true; \
	done
	@sleep 1
	@for pid in $$(lsof -t -i :$(API_PORT) 2>/dev/null); do \
		kill -9 $$pid >/dev/null 2>&1 || true; \
	done
	@echo "api stopped"

api-status:
	@if lsof -i :$(API_PORT) >/dev/null 2>&1; then \
		echo "api up on :$(API_PORT)"; \
		lsof -i :$(API_PORT); \
		echo "log: $(API_LOG)"; \
	else \
		echo "api down on :$(API_PORT)"; \
	fi

api-logs:
	@tail -n 120 $(API_LOG)

db:
	brew services start postgresql@16
	createdb payfi_box || true

db-docker:
	docker compose -f infra/docker-compose.yml up -d

db-down:
	brew services stop postgresql@16

db-docker-down:
	docker compose -f infra/docker-compose.yml down

dev-db: db-docker

migrate:
	cd apps/api && env -u DATABASE_URL ../../.venv/bin/alembic upgrade head

seed:
	cd apps/api && env -u DATABASE_URL ../../.venv/bin/python scripts/seed_demo_data.py

reset-db:
	cd apps/api && env -u DATABASE_URL ../../.venv/bin/python scripts/reset_demo_data.py

lint:
	npm run lint

test:
	npm run test

verify-api:
	$(PYTHON_BIN) scripts/verify_step7b.py --health-only

verify-seed:
	$(MAKE) db
	$(MAKE) migrate
	$(MAKE) reset-db

verify-step7b:
	$(PYTHON_BIN) scripts/verify_step7b.py

verify-step7b-reset:
	$(PYTHON_BIN) scripts/verify_step7b.py --reset-db

verify-execution-modes:
	bash scripts/verify_execution_modes.sh

contract-compile:
	cd apps/contracts && npm run compile

contract-deploy-hashkey:
	cd apps/contracts && npm run deploy:hashkey-testnet

contract-test-idempotency:
	cd apps/contracts && npm run test:idempotency
