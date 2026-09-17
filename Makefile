.PHONY: up down seed reconcile test types check logs
up:
	docker compose up -d --build
down:
	docker compose down
seed:
	docker compose exec -T api python -m app.seed
reconcile:
	docker compose exec -T api python -m app.assignments
test:
	docker compose exec -T api python -m pytest -q
types:
	cd frontend && npm run types
check:
	cd frontend && npm run build
logs:
	docker compose logs --tail=80 api web
