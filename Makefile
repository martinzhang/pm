.PHONY: app sync

app:
	uv run python app.py

sync:
	uv sync

bot:
	uv run python -m wecom.bot