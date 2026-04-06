from __future__ import annotations

import argparse

import uvicorn

from final_edu.config import get_settings


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Run the Final Edu curriculum coverage dashboard.",
    )
    parser.add_argument("--host", default=settings.host, help="Host interface to bind.")
    parser.add_argument("--port", default=settings.port, type=int, help="Port to bind.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto reload for local development.",
    )
    args = parser.parse_args()

    uvicorn.run(
        "final_edu.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
