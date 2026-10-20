"""Serveur TCI local pour la page du WebSDR ORSAT.

La page du WebSDR (bouton « CAT Sync », lib/catsync.js de PhantomSDR-ORSAT)
cherche un serveur TCI sur localhost, ports 50001 et 40001. ORSAT-LOG écoute
sur 40001 (50001 reste au transceiver, AetherSDR) : la page s'y connecte et
lui envoie la fréquence et le mode de ce que l'auditeur écoute vraiment.

    page -> ORSAT-LOG : vfo:0,0,<Hz>;  modulation:0,<mode>;  rx_filter_band:0,<bas>,<haut>;
    ORSAT-LOG -> page : vfo:0,0,<Hz>;  modulation:0,<mode>;   (recalage depuis le carnet)

À la connexion, la page interroge « vfo:0; modulation:0; trx:0; ». Tant que
la page n'a rien envoyé, ORSAT-LOG ne connaît pas la fréquence : il ne répond
pas, pour ne pas lui faire croire à une fréquence nulle. Le premier réglage
sur la page suffit à synchroniser.
"""

import asyncio
import logging

import websockets

from .tci import TCI_MODES

log = logging.getLogger("orsatlog.websdr")


class WebSdrServer:
    def __init__(self, on_change):
        self._on_change = on_change
        self._server = None
        self._pages = set()
        self.port = 40001
        self.state = self._empty_state()

    @staticmethod
    def _empty_state():
        return {
            "listening": False,   # le port TCI est ouvert
            "connected": False,   # au moins une page WebSDR est connectée
            "pages": 0,
            "device": "WebSDR",
            "freq": 0,
            "modulation": "",
            "mode": "",
            "submode": "",
            "ptt": False,
            "error": "",
        }

    # --- cycle de vie ---
    async def start(self, port):
        await self.stop()
        self.port = int(port)
        try:
            self._server = await websockets.serve(self._on_page, "127.0.0.1", self.port,
                                                  max_size=2**20)
        except OSError as exc:
            log.warning("WebSDR : port %s indisponible : %s", self.port, exc)
            self._set(error=f"port {self.port} déjà utilisé (un autre logiciel TCI ?)")
            return
        log.info("WebSDR : serveur TCI sur ws://127.0.0.1:%s", self.port)
        self._set(listening=True, error="")

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._pages.clear()
        self._set(**self._empty_state())

    # --- une page WebSDR ---
    async def _on_page(self, ws):
        self._pages.add(ws)
        self._set(connected=True, pages=len(self._pages))
        log.info("WebSDR : page connectée (%d)", len(self._pages))
        try:
            await ws.send("protocol:ExpertSDR3,1.9;device:ORSAT-LOG;receive_only:true;"
                          "trx_count:1;channels_count:1;ready;")
            async for msg in ws:
                if isinstance(msg, str):
                    for cmd in msg.replace("\n", "").split(";"):
                        cmd = cmd.strip()
                        if cmd:
                            await self._handle(ws, cmd)
        except websockets.ConnectionClosed:
            pass
        finally:
            self._pages.discard(ws)
            self._set(connected=bool(self._pages), pages=len(self._pages))
            log.info("WebSDR : page déconnectée (%d)", len(self._pages))

    async def _handle(self, ws, cmd):
        name, _, args = cmd.partition(":")
        name = name.strip().lower()
        parts = [a.strip() for a in args.split(",")] if args else []
        st = self.state
        if name == "vfo":
            if len(parts) >= 3:                       # la page a changé de fréquence
                try:
                    self._set(freq=int(float(parts[2])))
                except ValueError:
                    return
                await self._send_others(ws, f"vfo:0,0,{st['freq']};")
            elif st["freq"]:
                await ws.send(f"vfo:0,0,{st['freq']};")
        elif name == "modulation":
            if len(parts) >= 2:
                self._set_modulation(parts[1])
                await self._send_others(ws, f"modulation:0,{st['modulation']};")
            elif st["modulation"]:
                await ws.send(f"modulation:0,{st['modulation']};")
        elif name == "trx":
            await ws.send("trx:0,false;")             # le carnet n'émet jamais
        # rx_filter_band et le reste : rien à faire pour un carnet

    def _set_modulation(self, mod):
        mod = mod.lower()
        mode, sub = TCI_MODES.get(mod, (mod.upper(), ""))
        self._set(modulation=mod, mode=mode, submode=sub)

    async def _send_others(self, sender, text):
        for p in list(self._pages):
            if p is not sender:
                try:
                    await p.send(text)
                except websockets.ConnectionClosed:
                    pass

    # --- recalage de la page depuis le carnet ---
    async def tune(self, freq, modulation=None):
        """Envoie fréquence (Hz) et mode TCI à la page. Retourne False sans page connectée."""
        if not self._pages:
            return False
        text = f"vfo:0,0,{int(freq)};"
        if modulation:
            text += f"modulation:0,{modulation.lower()};"
        for p in list(self._pages):
            try:
                await p.send(text)
            except websockets.ConnectionClosed:
                pass
        self._set(freq=int(freq))
        if modulation:
            self._set_modulation(modulation)
        return True

    def _set(self, **changes):
        changed = {k: v for k, v in changes.items() if self.state.get(k) != v}
        if changed:
            self.state.update(changed)
            self._on_change(dict(self.state))
