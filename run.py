#!/usr/bin/env python3
"""Lanceur ORSAT-LOG : démarre le serveur local et ouvre la fenêtre de l'application.

    python3 run.py              fenêtre native (pywebview)
    python3 run.py --browser    ouvre dans le navigateur à la place
    python3 run.py --server     serveur seul (développement)
"""

import argparse
import logging
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

import uvicorn  # noqa: E402

HOST = "127.0.0.1"


def wait_port(port, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex((HOST, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def native_window_available():
    """Vrai si pywebview peut ouvrir une fenêtre (GTK + WebKit2, ou Qt) — testé sans bruit."""
    try:
        import gi
        for ver in ("4.1", "4.0"):
            try:
                gi.require_version("WebKit2", ver)
                return True
            except ValueError:
                pass
    except ImportError:
        pass
    try:
        import qtpy  # noqa: F401
        return True
    except ImportError:
        return False


def main():
    p = argparse.ArgumentParser(description="ORSAT-LOG")
    p.add_argument("--port", type=int, default=8740)
    p.add_argument("--browser", action="store_true", help="ouvrir dans le navigateur")
    p.add_argument("--server", action="store_true", help="serveur seul, sans fenêtre")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    config = uvicorn.Config("orsatlog.server:app", host=HOST, port=args.port,
                            log_level="debug" if args.debug else "warning")
    server = uvicorn.Server(config)

    if args.server:
        server.run()
        return

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    if not wait_port(args.port):
        sys.exit("Le serveur ORSAT-LOG n'a pas démarré.")
    url = f"http://{HOST}:{args.port}/"

    if not args.browser and not native_window_available():
        print("Fenêtre native indisponible (WebKit GTK absent) : ouverture dans le navigateur.\n"
              "  Pour l'activer : sudo apt install gir1.2-webkit2-4.1")
        args.browser = True

    if not args.browser:
        try:
            import webview
        except ImportError:
            print("pywebview absent : ouverture dans le navigateur.")
            args.browser = True
        else:
            try:
                webview.create_window("ORSAT-LOG", url, width=1400, height=900,
                                      min_size=(1100, 700), background_color="#0d0d0f")
                webview.start()
                server.should_exit = True
                return
            except Exception as exc:  # GTK/WebKit absent, etc.
                print(f"Fenêtre native impossible ({exc}) : ouverture dans le navigateur.")
                args.browser = True

    import webbrowser
    webbrowser.open(url)
    print(f"ORSAT-LOG : {url}  (Ctrl+C pour quitter)")
    try:
        thread.join()
    except KeyboardInterrupt:
        server.should_exit = True


if __name__ == "__main__":
    main()
