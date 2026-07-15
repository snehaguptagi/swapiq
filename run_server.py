"""Launcher that respects the harness-assigned PORT env var, falling back to
8020 for manual runs (python run_server.py) outside the preview harness."""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8020"))
    uvicorn.run("api.index:app", host="0.0.0.0", port=port)
