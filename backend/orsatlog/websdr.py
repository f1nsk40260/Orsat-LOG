"""Liaison TCI avec la page du WebSDR ORSAT.

La page du WebSDR (même adresse que le carnet, https://orsat.ddns.net) ouvre un
WebSocket sur /log/tci dès que ce navigateur a une session au carnet, et parle TCI :

    page -> carnet : vfo:0,0,<Hz>;  modulation:0,<mode>;      (fréquence et mode écoutés)
    carnet -> page : vfo:0,0,<Hz>;  modulation:0,<mode>;      (recalage depuis le carnet)

La page est la référence : elle envoie d'elle-même fréquence et mode dès la connexion,
et le carnet ne répond jamais à ses questions (« vfo:0; », « trx:0; »...).
"""

import logging

log = logging.getLogger("orsatlog.websdr")

# modulation TCI -> (mode ADIF, sous-mode ADIF)
TCI_MODES = {
    "usb": ("SSB", "USB"),
    "lsb": ("SSB", "LSB"),
    "cw": ("CW", ""),
    "cwr": ("CW", ""),
    "rtty": ("RTTY", ""),
    "am": ("AM", ""),
    "sam": ("AM", ""),
    "dsb": ("AM", ""),
    "fm": ("FM", ""),
    "nfm": ("FM", ""),
    "wfm": ("FM", ""),
    "digu": ("", ""),   # mode numérique : laissé au choix de l'opérateur (FT8, RTTY...)
    "digl": ("", ""),
    "drm": ("DRM", ""),
}


class Page:
    """Une page WebSDR reliée par le WebSocket /tci (FastAPI)."""

    def __init__(self, ws):
        self.ws = ws

    async def send(self, text):
        await self.ws.send_text(text)

    def __aiter__(self):
        return self

    async def __anext__(self):
        from starlette.websockets import WebSocketDisconnect
        try:
            return await self.ws.receive_text()
        except WebSocketDisconnect:
            raise StopAsyncIteration


class WebSdrLink:
    def __init__(self, on_change):
        self._on_change = on_change
        self._pages = set()
        self.state = {
            "listening": True,
            "connected": False,   # au moins une page WebSDR est reliée
            "pages": 0,
            "device": "WebSDR",
            "freq": 0,
            "modulation": "",
            "mode": "",
            "submode": "",
            "ptt": False,
            "error": "",
        }

    async def on_page(self, page):
        self._pages.add(page)
        self._set(connected=True, pages=len(self._pages))
        log.info("WebSDR : page reliée (%d)", len(self._pages))
        try:
            await page.send("protocol:ExpertSDR3,1.9;device:ORSAT-LOG;receive_only:true;"
                            "trx_count:1;channels_count:1;ready;")
            async for msg in page:
                for cmd in msg.replace("\n", "").split(";"):
                    cmd = cmd.strip()
                    if cmd:
                        await self._handle(page, cmd)
        except Exception as exc:      # page fermée brutalement
            log.debug("WebSDR : %s", exc)
        finally:
            self._pages.discard(page)
            self._set(connected=bool(self._pages), pages=len(self._pages))
            log.info("WebSDR : page déconnectée (%d)", len(self._pages))

    async def _handle(self, page, cmd):
        name, _, args = cmd.partition(":")
        name = name.strip().lower()
        parts = [a.strip() for a in args.split(",")] if args else []
        if name == "vfo" and len(parts) >= 3:
            try:
                self._set(freq=int(float(parts[2])))
            except ValueError:
                return
            await self._send_others(page, f"vfo:0,0,{self.state['freq']};")
        elif name == "modulation" and len(parts) >= 2:
            self._set_modulation(parts[1])
            await self._send_others(page, f"modulation:0,{self.state['modulation']};")
        # questions (vfo:0; modulation:0; trx:0;) et le reste : pas de réponse

    def _set_modulation(self, mod):
        mod = mod.lower()
        mode, sub = TCI_MODES.get(mod, (mod.upper(), ""))
        self._set(modulation=mod, mode=mode, submode=sub)

    async def _send_others(self, sender, text):
        for p in list(self._pages):
            if p is not sender:
                try:
                    await p.send(text)
                except Exception:          # page fermée entre-temps
                    pass

    async def tune(self, freq, modulation=None):
        """Recale la page sur une entrée du carnet. False si aucune page n'est reliée."""
        if not self._pages:
            return False
        text = f"vfo:0,0,{int(freq)};"
        if modulation:
            text += f"modulation:0,{modulation.lower()};"
        for p in list(self._pages):
            try:
                await p.send(text)
            except Exception:
                pass
        self._set(freq=int(freq))
        if modulation:
            self._set_modulation(modulation)
        return True

    def mirror(self, freq, modulation=""):
        """AetherSDR a changé de fréquence ; la page l'a suivi (CAT Sync). Recopié
        seulement si la page a déjà parlé (fréquence connue)."""
        if not (self._pages and self.state["freq"] and freq):
            return
        self._set(freq=int(freq))
        if modulation:
            self._set_modulation(modulation)

    def _set(self, **changes):
        changed = {k: v for k, v in changes.items() if self.state.get(k) != v}
        if changed:
            self.state.update(changed)
            self._on_change(dict(self.state))
