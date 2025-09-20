import logging
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

from . import config

# Individual route blueprints (each exposes `bp`)
from .routes import models as models_route      # noqa: F401
from .routes import upload as upload_route      # noqa: F401
from .routes import preprocess as preprocess_route  # noqa: F401
from .routes import headers as headers_route    # noqa: F401
from .routes import process as process_route    # noqa: F401
from .routes import llm_test as llm_test_route  # noqa: F401

# Optional aggregate "api" blueprint (older builds). We'll try to mount it too.
try:
    from .routes import api  # noqa: F401
except Exception:
    api = None

load_dotenv()

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("FluidRAG")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=config.STATIC_FOLDER, static_url_path=config.STATIC_URL_PATH)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

    # CORS for API
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)

    # ---- Register blueprints (routes define absolute paths like "/api/…") ----
    # Prefer explicit registration of each functional blueprint
    app.register_blueprint(models_route.bp)
    app.register_blueprint(upload_route.bp)
    app.register_blueprint(preprocess_route.bp)
    app.register_blueprint(headers_route.bp)
    app.register_blueprint(process_route.bp)
    app.register_blueprint(llm_test_route.bp)

    # If a legacy aggregate "api" blueprint exists, attempt to register it too.
    # Use a safe guard so we don't crash on duplicate rules.
    if api is not None:
        try:
            # If your api blueprint expects a url_prefix, set it to "/api".
            # IMPORTANT: Only do this if the rules inside `api` are like "/models", not "/api/models".
            # If your api blueprint already prefixes with "/api", set url_prefix=None.
            app.register_blueprint(api, url_prefix="/api")
        except Exception as e:
            log.warning("Skipping legacy 'api' blueprint registration: %s", e)

    # ---- Static file serving ----
    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/<path:asset>")
    def static_proxy(asset: str):
        return app.send_static_file(asset)

    # ---- Health probe ----
    @app.get("/healthz")
    def healthz():
        return {"ok": True}, 200

    # ---- JSON error handlers for API paths ----
    @app.errorhandler(405)
    def handle_405(err):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "httpStatus": 405, "error": "Method Not Allowed"}), 405
        return err, 405

    @app.errorhandler(404)
    def handle_404(err):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "httpStatus": 404, "error": "Not Found"}), 404
        return err, 404

    @app.errorhandler(500)
    def handle_500(err):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "httpStatus": 500, "error": "Internal Server Error"}), 500
        return err, 500

    return app


app = create_app()

if __name__ == "__main__":
    app = create_app()
    log.info("Starting FluidRAG on http://127.0.0.1:%s", config.PORT)
    app.run(host="127.0.0.1", port=config.PORT, debug=True)
