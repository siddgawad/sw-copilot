from __future__ import annotations

import os
from multiprocessing import freeze_support

import uvicorn


def main() -> None:
    host = os.environ.get("SW_COPILOT_BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("SW_COPILOT_BACKEND_PORT", "8001"))

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        log_level=os.environ.get("SW_COPILOT_BACKEND_LOG_LEVEL", "info"),
        access_log=False,
    )


if __name__ == "__main__":
    freeze_support()
    main()
