# FlashMart — 부하·확장성 실험실
# 명령 목록은 `make help`.

SHELL := /bin/bash
.DEFAULT_GOAL := help

PROJECT := flashmart
FILES   := -f deploy/compose.yaml -f deploy/compose.obs.yaml

K6_IMAGE := grafana/k6:0.55.0

# app 인스턴스 수. N=1 은 Phase 0 구성(nginx 없음), N>1 이면 nginx LB 를 함께 띄운다.
N ?= 1
# 부하 프로파일 (§8): smoke | target | limit
PROFILE ?= smoke

ifeq ($(N),1)
  # Phase 0: app 을 호스트 8000 에 고정 노출한다 (compose.direct.yaml).
  # k6 는 도커 네트워크 안에서 app 을 직접 때린다.
  UP_FILES    := $(FILES) -f deploy/compose.direct.yaml
  UP_PROFILES :=
  BASE_URL    ?= http://app:8000
  HOST_URL    := http://localhost:8000
else
  # Phase 1+: 호스트에는 nginx 만 노출된다 (§11). app 은 포트를 열지 않는다.
  UP_FILES    := $(FILES)
  UP_PROFILES := --profile lb
  BASE_URL    ?= http://nginx
  HOST_URL    := http://localhost:8080
endif

COMPOSE     := docker compose -p $(PROJECT) $(FILES)
COMPOSE_UP  := docker compose -p $(PROJECT) $(UP_FILES)
# down/ps/stats 는 nginx 까지 봐야 하므로 프로파일을 항상 켠 형태를 따로 둔다.
COMPOSE_ALL := docker compose -p $(PROJECT) $(FILES) --profile lb

.PHONY: help up down logs migrate revision seed reset-deal load check psql redis-cli \
        kill-one pause-redis unpause-redis stats grafana ps clean lint

help:
	@echo "FlashMart — 실험 명령"
	@echo ""
	@echo "  기동"
	@echo "    make up               기본 기동 (app 1대, Phase 0 구성)"
	@echo "    make up N=3           app 3대 + nginx LB (Phase 1+ 구성)"
	@echo "    make down             중지 (데이터는 유지)"
	@echo "    make clean            중지 + 볼륨 삭제 (seed 도 날아간다)"
	@echo "    make ps / make logs [S=app]"
	@echo ""
	@echo "  스키마·데이터"
	@echo "    make migrate          alembic upgrade head"
	@echo "    make revision m=\"...\"  마이그레이션 생성 (--autogenerate)"
	@echo "    make seed             COPY 기반 대량 적재 (수 분)"
	@echo "    make reset-deal       딜 수량·주문 초기화 (스파이크 실험 전 필수)"
	@echo ""
	@echo "  실험"
	@echo "    make load S=mixed [PROFILE=smoke|target|limit] [N=3]"
	@echo "    make check S=oversell | S=dup_orders"
	@echo "    make kill-one         app 1대 강제 종료 (P2-08)"
	@echo "    make pause-redis / make unpause-redis   (P2-13)"
	@echo ""
	@echo "  관측"
	@echo "    make stats            리소스 제한이 실제로 걸렸는지 확인 (§13)"
	@echo "    make grafana          localhost:3000"
	@echo "    make psql / make redis-cli"

up:
	$(COMPOSE_UP) $(UP_PROFILES) up -d --build --scale app=$(N)
	@echo ""
	@echo "app x$(N) 기동"
	@echo "  호스트에서    : $(HOST_URL)"
	@echo "  k6 부하 대상  : $(BASE_URL)"
	@echo '  리소스 제한이 실제로 걸렸는지 "make stats" 로 확인할 것 (§13).'

down:
	$(COMPOSE_ALL) down --remove-orphans

clean:
	$(COMPOSE_ALL) down --remove-orphans --volumes

ps:
	$(COMPOSE_ALL) ps

logs:
	$(COMPOSE_ALL) logs -f --tail=100 $(S)

migrate:
	$(COMPOSE) run --rm app alembic upgrade head

revision:
	@test -n "$(m)" || { echo 'm="설명" 이 필요하다. 예: make revision m="add idempotency key"'; exit 1; }
	@# 생성된 파일이 호스트에 남아야 하므로 migrations 를 마운트한다.
	@# 컨테이너가 root 로 돌아서 파일 소유자가 root 가 된다 — 필요하면 chown 할 것.
	$(COMPOSE) run --rm -v "$(PWD)/migrations:/srv/migrations" app \
		alembic revision --autogenerate -m "$(m)"

seed:
	$(COMPOSE) run --rm app python -m seed.seed

reset-deal:
	$(COMPOSE) exec -T db psql -U flashmart -d flashmart -f - < seed/reset_deal.sql

load:
	@test -n "$(S)" || { echo 'S=<시나리오> 가 필요하다. 예: make load S=mixed'; exit 1; }
	@test -f "load/k6/$(S).js" || { echo "load/k6/$(S).js 가 없다."; exit 1; }
	@mkdir -p load/results
	docker run --rm -i \
		--network $(PROJECT)_default \
		-e BASE_URL=$(BASE_URL) \
		-e PROFILE=$(PROFILE) \
		-v "$(PWD)/load/k6:/scripts:ro" \
		-v "$(PWD)/load/results:/results" \
		$(K6_IMAGE) run /scripts/$(S).js

check:
	@test -n "$(S)" || { echo 'S=<검증> 이 필요하다. 예: make check S=oversell'; exit 1; }
	@test -f "load/checks/$(S).sql" || { echo "load/checks/$(S).sql 가 없다."; exit 1; }
	$(COMPOSE) exec -T db psql -U flashmart -d flashmart -f - < load/checks/$(S).sql

psql:
	$(COMPOSE) exec db psql -U flashmart -d flashmart

redis-cli:
	$(COMPOSE) exec redis redis-cli

# 부하 중 앱 인스턴스 1대를 강제 종료한다 (P2-08).
# docker kill 은 SIGKILL 이다 — graceful shutdown 을 우회해서 최악을 만든다.
# 다시 띄우려면 `make up N=<원래수>`.
kill-one:
	@cid=$$($(COMPOSE) ps -q app | head -1); \
	 test -n "$$cid" || { echo "app 컨테이너가 없다."; exit 1; }; \
	 name=$$(docker inspect --format '{{.Name}}' $$cid); \
	 echo "SIGKILL → $$name"; \
	 docker kill $$cid

# Redis 장애 주입 (P2-13). stop 이 아니라 pause 다 — stop 은 커넥션 리셋이라
# 클라이언트가 즉시 에러를 받지만, pause 는 응답이 사라져 timeout 경로를 탄다 (§11).
pause-redis:
	@docker pause $$($(COMPOSE) ps -q redis) && echo "redis paused — 복구는 make unpause-redis"

unpause-redis:
	@docker unpause $$($(COMPOSE) ps -q redis) && echo "redis unpaused"

# 리소스 제한이 실제로 적용됐는지 확인한다 (§13). LIMIT 이 호스트 전체 메모리로
# 나오면 제한이 안 걸린 것이고, 그 상태로는 문제가 로컬 사양에 묻혀서 안 터진다.
stats:
	@docker stats --no-stream \
		--format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' \
		$$($(COMPOSE_ALL) ps -q)

grafana:
	@open http://localhost:3000 2>/dev/null || echo "http://localhost:3000 (admin/admin)"

lint:
	uv run ruff check app mockpg seed
	uv run ruff format --check app mockpg seed
	uv run mypy app mockpg seed
