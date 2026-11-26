"""Entrypoint for uvicorn.

Works with both invocation styles:

    uvicorn backend.main:app --reload --port 8000   # from the repo root
    cd backend && uvicorn main:app --reload         # from backend/
    docker run ...                                  # /app/main.py + /app/app/

The application itself lives in `backend/app/` - this file only builds it.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:  # imported as `backend.main` (repo root on sys.path)
    from backend.app import create_app
except ModuleNotFoundError as error:  # imported as `main` (backend/ on sys.path)
    # Only fall back when the `backend` package itself is missing; any other
    # import error is a real bug and must not be hidden.
    if (error.name or "").split(".")[0] != "backend":
        raise
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    from app import create_app

app = create_app()
