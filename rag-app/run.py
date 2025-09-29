"""Start FastAPI backend using uvicorn and serve the static frontend."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import signal
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer

import uvicorn

from backend.app.config import get_settings
from backend.app.util.logging import get_logger

logger = get_logger(__name__)


def start_backend() -> None:
    """Start FastAPI backend using uvicorn."""
    settings = get_settings()
    reload = settings.backend_reload
    config = uvicorn.Config(
        "backend.app.main:create_app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=reload,
        factory=True,
        log_level=settings.log_level,
    )
    server = uvicorn.Server(config)
    logger.info(
        "backend.run",
        extra={
            "host": settings.backend_host,
            "port": settings.backend_port,
            "reload": reload,
        },
    )
    server.run()


def start_frontend() -> None:
    """Serve static frontend via SimpleHTTPServer."""
    settings = get_settings()
    directory = Path(__file__).parent / "frontend"
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))

    class QuietServer(ThreadingTCPServer):
        allow_reuse_address = True

    with QuietServer(
        (settings.frontend_host, settings.frontend_port), handler
    ) as httpd:
        logger.info(
            "frontend.run",
            extra={
                "host": settings.frontend_host,
                "port": settings.frontend_port,
                "directory": str(directory),
            },
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:  # pragma: no cover - handled by signal termination
            logger.info("frontend.stop")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the FluidRAG development stack.")
    parser.add_argument(
        "--reload", action="store_true", help="Reload backend on code changes."
    )
    return parser.parse_args()


def _terminate_processes(processes: list[multiprocessing.Process]) -> None:
    for proc in processes:
        if proc.is_alive():
            proc.terminate()
    for proc in processes:
        proc.join()


def main() -> None:
    args = parse_args()

    if args.reload:
        os.environ["BACKEND_RELOAD"] = "true"

    backend_proc = multiprocessing.Process(
        target=start_backend,
        name="backend",
    )
    frontend_proc = multiprocessing.Process(
        target=start_frontend,
        name="frontend",
    )

    processes = [backend_proc, frontend_proc]
    for proc in processes:
        proc.start()

    def _handle_signal(signum: int, _frame: object | None) -> None:
        logger.info("runner.signal", extra={"signal": signum})
        _terminate_processes(processes)
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    try:
        for proc in processes:
            proc.join()
    finally:
        _terminate_processes(processes)


if __name__ == "__main__":
    main()
