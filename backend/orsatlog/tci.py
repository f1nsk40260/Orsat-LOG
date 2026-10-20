"""Client TCI (Expert Electronics) : lecture fréquence / mode / PTT.

Le protocole TCI est du texte sur WebSocket, chaque commande se termine par ';'.
Exemples envoyés par le serveur :
    protocol:ExpertSDR3,1.9;   device:SunSDR2PRO;   ready;
    vfo:0,0,14074000;          modulation:0,usb;     trx:0,false;
Les trames binaires (audio, IQ) sont ignorées.
"""

import asyncio
import logging

import websockets

log = logging.getLogger("orsatlog.tci")

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


class TciClient:
    def __init__(self, on_change):
        self._on_change = on_change
        self._task = None
        self.host = "127.0.0.1"
        self.port = 50001
        self.trx = "0"  # récepteur TCI suivi (slice A = 0, slice B = 1...)
        self.state = self._empty_state()

    @staticmethod
    def _empty_state():
        return {
            "connected": False,
            "ready": False,
            "device": "",
            "protocol": "",
            "freq": 0,
            "modulation": "",
            "mode": "",
            "submode": "",
            "ptt": False,
            "error": "",
        }

    # --- cycle de vie ---
    def start(self, host, port, trx=0):
        self.host, self.port, self.trx = host, int(port), str(trx)
        self.stop()
        self._task = asyncio.create_task(self._run())

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None
        self._set(**self._empty_state())

    async def _run(self):
        url = f"ws://{self.host}:{self.port}"
        while True:
            try:
                async with websockets.connect(url, open_timeout=5, max_size=None) as ws:
                    log.info("TCI connecté à %s", url)
                    self._set(connected=True, error="")
                    async for msg in ws:
                        if isinstance(msg, str):
                            for cmd in msg.split(";"):
                                cmd = cmd.strip()
                                if cmd:
                                    self._handle(cmd)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # serveur absent, coupure réseau...
                log.info("TCI %s : %s", url, exc)
                self._set(error=_explain(exc))
            self._set(connected=False, ready=False)
            await asyncio.sleep(5)

    # --- décodage ---
    def _handle(self, cmd):
        name, _, args = cmd.partition(":")
        name = name.lower()
        parts = [a.strip() for a in args.split(",")] if args else []
        if name == "ready":
            self._set(ready=True)
        elif name == "device" and parts:
            self._set(device=parts[0])
        elif name == "protocol" and parts:
            self._set(protocol=",".join(parts))
        elif name == "vfo" and len(parts) >= 3:
            # vfo:récepteur,canal,fréquence — on suit le récepteur choisi, canal A
            if parts[0] == self.trx and parts[1] == "0":
                try:
                    self._set(freq=int(float(parts[2])))
                except ValueError:
                    pass
        elif name == "modulation" and len(parts) >= 2 and parts[0] == self.trx:
            mod = parts[1].lower()
            mode, sub = TCI_MODES.get(mod, (mod.upper(), ""))
            self._set(modulation=mod, mode=mode, submode=sub)
        elif name == "trx" and len(parts) >= 2 and parts[0] == self.trx:
            self._set(ptt=parts[1].lower() == "true")

    def _set(self, **changes):
        changed = {k: v for k, v in changes.items() if self.state.get(k) != v}
        if changed:
            self.state.update(changed)
            self._on_change(dict(self.state))


def _explain(exc):
    """Message clair pour l'interface."""
    text = str(exc)
    if isinstance(exc, ConnectionRefusedError) or "refused" in text.lower():
        return "connexion refusée : serveur TCI arrêté ou mauvais port"
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "timed out" in text.lower():
        return "pas de réponse : adresse incorrecte ou pare-feu"
    return text[:120]
