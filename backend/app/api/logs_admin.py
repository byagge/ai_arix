"""Admin log tail for production monitoring."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.logging_setup import LOG_DIR

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/tail")
async def tail_logs(lines: int = Query(200, ge=20, le=2000)):
    path = LOG_DIR / "arix.log"
    if not path.exists():
        return {"path": str(path), "lines": [], "exists": False}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise HTTPException(500, str(e)) from e
    parts = text.splitlines()
    return {
        "path": str(path),
        "exists": True,
        "total_lines": len(parts),
        "lines": parts[-lines:],
    }


@router.get("/files")
async def list_log_files():
    files = sorted(LOG_DIR.glob("arix.log*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "dir": str(LOG_DIR),
        "files": [
            {"name": f.name, "size": f.stat().st_size, "mtime": f.stat().st_mtime} for f in files
        ],
    }
