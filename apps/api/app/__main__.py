"""Development and production entry point for the FastAPI service."""

import argparse

import uvicorn

from app.config import Settings


def main() -> None:
    """Run uvicorn using environment-backed host and port settings."""
    parser = argparse.ArgumentParser(description="Run the Harness Evolution API")
    parser.add_argument("--reload", action="store_true", help="reload on source changes")
    args = parser.parse_args()
    settings = Settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=args.reload,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
