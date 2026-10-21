#!/usr/bin/env python3
"""Démarre ORSAT-LOG, serveur central du carnet de trafic.

Lancé par le service systemd « orsat-log » (voir install-server.sh), derrière proxy.py de
PhantomSDR-ORSAT qui l'expose sous https://<site>/log/.

    python3 run.py [--host 127.0.0.1] [--port 8740] [--debug]
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

import uvicorn  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="ORSAT-LOG, serveur central")
    p.add_argument("--host", default="127.0.0.1", help="adresse d'écoute (défaut : boucle locale, derrière proxy.py)")
    p.add_argument("--port", type=int, default=8740)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from orsatlog import auth
    print(f"ORSAT-LOG sur http://{args.host}:{args.port}/ — mot de passe du panneau admin : "
          + (str(auth.ADMIN_CONFIG) if auth.password_available() else f"INTROUVABLE ({auth.ADMIN_CONFIG})"),
          flush=True)
    uvicorn.run("orsatlog.server:app", host=args.host, port=args.port,
                log_level="debug" if args.debug else "warning",
                proxy_headers=True, forwarded_allow_ips="127.0.0.1")


if __name__ == "__main__":
    main()
