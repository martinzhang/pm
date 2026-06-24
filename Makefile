.PHONY: app sync

app:
	uv run python app.py

sync:
	uv sync
