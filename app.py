"""
Projects -- Gantt-driven lightweight project management
Apple-like UI, all Chinese, iOS-friendly

Entry point: thin create_app() factory.
"""
import os
from flask import Flask
from config import URL_PREFIX, MAX_CONTENT_LENGTH, UPLOAD_DIR
from models import init_db, run_migrations
from auth import load_user, inject_globals


def create_app():
    app = Flask(__name__, static_url_path=f"{URL_PREFIX}/static")
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Database
    init_db()
    run_migrations()

    # Auth hooks
    app.before_request(load_user)

    @app.context_processor
    def _globals():
        return inject_globals()

    # Blueprints
    from blueprints import projects, tasks, calendar, dashboard, ai, meetings, ical, pm_agent
    for bp in [projects.bp, tasks.bp, calendar.bp, dashboard.bp, ai.bp, meetings.bp, ical.bp, pm_agent.bp]:
        app.register_blueprint(bp, url_prefix=URL_PREFIX)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8092))
    app.run(host="127.0.0.1", port=port, debug=True)
