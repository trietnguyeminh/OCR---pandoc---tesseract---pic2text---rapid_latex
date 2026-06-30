"""FormuDoc desktop launcher (entry point at PROJECT ROOT).

Root placement keeps `app` unambiguous (no stray app.py shadows the backend).

IMPORTANT for PyInstaller *windowed* builds: sys.stdout / sys.stderr are None,
which makes uvicorn/logging crash the server thread. We give them a real stream
(a log file) BEFORE importing anything that logs.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------- #
#  0) Guarantee real stdout/stderr (windowed exe has them as None) + a log file
# --------------------------------------------------------------------------- #
_LOGDIR = Path(os.getenv("FORMUDOC_DATA", Path.home() / "FormuDoc" / "data")).parent
try:
    _LOGDIR.mkdir(parents=True, exist_ok=True)
    _LOGF = open(_LOGDIR / "formudoc.log", "a", buffering=1, encoding="utf-8")
except Exception:
    _LOGF = open(os.devnull, "w")
if sys.stdout is None:
    sys.stdout = _LOGF
if sys.stderr is None:
    sys.stderr = _LOGF

# --------------------------------------------------------------------------- #
#  1) Make the backend package importable (dev + frozen bundle)
# --------------------------------------------------------------------------- #
_HERE = Path(__file__).resolve().parent
for _cand in (_HERE / "backend", _HERE.parent / "backend"):
    if _cand.exists() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))
        break
if hasattr(sys, "_MEIPASS") and sys._MEIPASS not in sys.path:
    sys.path.insert(0, sys._MEIPASS)

os.environ.setdefault("FORMUDOC_DATA", str(Path.home() / "FormuDoc" / "data"))

# Import uvicorn protocol/loop impls explicitly so PyInstaller always bundles
# them and uvicorn.run() never fails to import them at startup.
import uvicorn  # noqa: E402
import uvicorn.loops.asyncio  # noqa: E402,F401
import uvicorn.protocols.http.h11_impl  # noqa: E402,F401
import uvicorn.lifespan.off  # noqa: E402,F401

from app.main import app  # noqa: E402


def _free_port(preferred: int = 8000) -> int:
    for p in (preferred, 8123, 8420, 8765):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _free_port()


def _run_server() -> None:
    try:
        print(f"[formudoc] starting server on 127.0.0.1:{PORT}", flush=True)
        # access_log=False stops the flood of `GET /api/jobs/... 200 OK`
        # lines from the UI polling progress; the formudoc.jobs INFO logs still
        # show real progress.
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info",
                    access_log=False,
                    loop="asyncio", http="h11", ws="none", lifespan="off")
    except Exception:
        print("[formudoc] SERVER FAILED:\n" + traceback.format_exc(), flush=True)


def _wait_ready(timeout: float = 60.0) -> bool:
    url = f"http://127.0.0.1:{PORT}/health"
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> None:
    threading.Thread(target=_run_server, daemon=True).start()
    ready = _wait_ready()
    print(f"[formudoc] server ready={ready}", flush=True)
    import webview  # lazy import: only needed to show the window
    webview.create_window("FormuDoc Converter", f"http://127.0.0.1:{PORT}",
                          width=1180, height=860, min_size=(900, 640))
    webview.start()


if __name__ == "__main__":
    main()
