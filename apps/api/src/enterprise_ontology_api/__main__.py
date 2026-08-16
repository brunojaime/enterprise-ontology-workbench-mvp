"""Run the packaged API with JSON-only process and request logs."""

from __future__ import annotations

import os

import uvicorn

from enterprise_ontology_api.logging import uvicorn_log_config


def main() -> None:
    uvicorn.run(
        "enterprise_ontology_api.main:app",
        host=os.getenv("EOW_API_HOST", "0.0.0.0"),
        port=int(os.getenv("EOW_API_PORT", "8000")),
        access_log=False,
        log_config=uvicorn_log_config(os.getenv("EOW_LOG_LEVEL", "INFO")),
    )


if __name__ == "__main__":
    main()
