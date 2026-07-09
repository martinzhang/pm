.PHONY: app sync bot deploy deploy-app deploy-bot

REMOTE_HOST := nmconline
REMOTE_DIR  := /Users/nmconline/apps/pm

# 远程 git pull + uv sync（内部使用，依赖 RemoteForward 10802）
_pull:
	ssh $(REMOTE_HOST) "bash -l -c 'cd $(REMOTE_DIR) && HTTP_PROXY=http://127.0.0.1:10802 HTTPS_PROXY=http://127.0.0.1:10802 git pull && uv sync'"

app:
	uv run uvicorn main:app --host 127.0.0.1 --port $${PORT:-8092} --reload

sync:
	uv sync

bot:
	uv run python -m wecom.bot

## 仅部署 web 服务 (pm / gunicorn)
deploy-app: _pull
	ssh $(REMOTE_HOST) "bash -l -c 'cd $(REMOTE_DIR) && pm2 start ecosystem.config.js --only pm --update-env'"
	@echo "deploy-app done."

## 仅部署 bot 服务 (pm-bot)
deploy-bot: _pull
	ssh $(REMOTE_HOST) "bash -l -c 'cd $(REMOTE_DIR) && pm2 start ecosystem.config.js --only pm-bot --update-env'"
	@echo "deploy-bot done."

## 同时部署两者
deploy: _pull
	ssh $(REMOTE_HOST) "bash -l -c 'cd $(REMOTE_DIR) && pm2 start ecosystem.config.js --update-env'"
	@echo "deploy done."