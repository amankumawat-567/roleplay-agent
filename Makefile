.PHONY: install ui-install ui-build ui-dev dev run test seed-games research cleanup docker-build docker-up

install: ui-build
	pip install -e ".[dev]"
	playwright install chromium

ui-install:
	cd dev-ui && npm install

ui-build: ui-install
	cd dev-ui && npm run build

ui-dev:
	cd dev-ui && npm run dev

dev:
	uvicorn roleplay_agent.main:app --reload

run:
	uvicorn roleplay_agent.main:app --host 0.0.0.0 --port 8000

test:
	pytest

seed-games:
	python scripts/seed_games.py

research:
	python scripts/research.py $(GAME)

cleanup:
	python scripts/cleanup.py

docker-build:
	docker build -t roleplay-agent .

docker-up:
	docker compose up --build
