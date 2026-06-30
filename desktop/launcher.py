"""FormuDoc desktop launcher.

Runs the FastAPI server (API + bundled UI) in a background thread and shows it
in a *native* application window via pywebview — so double-clicking the app
opens its own window, just like a normal desktop program (no browser tab).

Works both from source (`python desktop/app.py`) and inside a PyInstaller exe.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

# --- make the backend package importable (dev + PyInstaller bundle) ---------- #
_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "backend", Path(getattr(sys, "_MEIPASS", _ROOT))):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Default writable data dir under the user's home BEFORE importing the app
# (settings read this env var at import time).
os.environ.setdefault("FORMUDOC_DATA", str(Path.home() / "FormuDoc" / "data"))

from app.main import app  # noqa: E402  (import after sys.path / env setup)
import uvicorn  # noqa: E402


def _free_port(preferred: int = 8000) -> int:
    for p in (preferred, 8123, 8420, 8765):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    with socket.socket() as s:               # last resort: ephemeral port
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _free_port()


def _run_server() -> None:
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning",
                loop="asyncio", http="h11", lifespan="off")


def _wait_ready(timeout: float = 30.0) -> bool:
    url = f"http://127.0.0.1:{PORT}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def main() -> None:
    threading.Thread(target=_run_server, daemon=True).start()
    _wait_ready()
    import webview  # lazy import: only needed to show the window
    webview.create_window(
        "FormuDoc Converter",
        f"http://127.0.0.1:{PORT}",
        width=1180, height=860, min_size=(900, 640),
    )
    webview.start()


if __name__ == "__main__":
    main()
