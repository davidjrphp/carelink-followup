COMPOSE := docker compose

.PHONY: help up up-nodb down reset seed seed-small test test-api test-web bench-api bench-web logs psql

help: ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

.env:
	cp .env.example .env

up: .env ## Build and start postgres, api and web (migrations run on api start)
	$(COMPOSE) up -d --build --wait db api web
	@echo "\n  Screen:   http://localhost:5173\n  API docs: http://localhost:8000/docs\n"

up-nodb: .env ## Start api and web against DATABASE_URL in .env (your own Postgres)
	$(COMPOSE) up -d --build --wait --no-deps api web

down: ## Stop everything (keeps data)
	$(COMPOSE) down

reset: ## Stop everything and delete the database volume
	$(COMPOSE) down -v

seed: ## Load the pack's sample data + 100,000 patients / 400,000 visits
	$(COMPOSE) exec api python -m seed

seed-small: ## Sample data + 2,000 patients (quick)
	$(COMPOSE) exec api python -m seed --patients 2000 --visits 8000

test: test-api test-web ## Run all tests

test-api: .env ## pytest against a real PostgreSQL (separate carelink_test database)
	$(COMPOSE) --profile test run --rm --build api-test

test-web: ## Type-check, then Vitest + Testing Library + MSW
	$(COMPOSE) --profile test run --rm --build web-test

bench-api: ## EXPLAIN ANALYZE + API latency with and without the visit index (needs `make seed`)
	$(COMPOSE) exec api python -m scripts.bench_api

bench-web: ## 10,000-row screen, naive vs virtualised (host Python + Playwright + Chrome; needs `make up`)
	python3 scripts/measure_web.py

logs: ## Follow api logs
	$(COMPOSE) logs -f api

psql: ## Open psql on the bundled database
	$(COMPOSE) exec db sh -c 'psql -U $$POSTGRES_USER $$POSTGRES_DB'
