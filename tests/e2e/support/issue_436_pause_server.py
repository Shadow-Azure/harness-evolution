"""Serve the real application with background evaluation observation held for UI tests."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn

from app.config import Settings
from app.main import create_app


def main() -> None:
    """Keep the seeded external evaluation pending; control API and database stay real."""
    app = create_app(Settings())
    lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def controlled_lifespan(application):
        async with lifespan(application):
            await application.state.evolution_eval_poller.stop()
            yield

    app.router.lifespan_context = controlled_lifespan
    uvicorn.run(
        app, host="127.0.0.1", port=int(os.environ["HE_PORT"]), log_level="warning"
    )


if __name__ == "__main__":
    main()
