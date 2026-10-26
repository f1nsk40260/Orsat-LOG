"""Analyse du bruit de fond mesuré par ORSAT selon la foudre, le Kp et la pression.

Pour chaque mesure de bruit (snr_obs, toutes les 5 min et par bande) :
  - écart au bruit habituel = bruit - médiane de la même bande à la même heure UTC sur la période ;
  - foudre des 15 min autour de la mesure (tranche de la mesure + les deux précédentes) ;
  - Kp le plus récent (relevé NOAA du carnet) ; tendance de pression sur 3 h (station météo).
On regroupe ensuite par classes et on donne l'écart moyen (dB) et le nombre de mesures. Une corrélation
ne se lit que sur des classes bien remplies : le nombre de mesures est donc toujours affiché.
"""

import bisect
from datetime import datetime, timedelta, timezone

BANDS = ["160m", "80m", "40m", "20m", "10m"]
MIN_N = 12          # moins d'une heure de mesures : case non interprétée


def _epoch(day, time):
    return datetime.strptime(day + time[:6].ljust(6, "0"), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).timestamp()


def _classes(value, bounds, labels):
    for b, l in zip(bounds, labels):
        if value <= b:
            return l
    return labels[-1]


def compute(rows):
    noise = [r for r in rows["noise"] if r[2] in BANDS]
    if not noise:
        return {"ok": True, "n": 0, "tables": []}

    # bruit habituel : médiane par bande et par heure
    by = {}
    for day, time, band, f in noise:
        by.setdefault((band, time[:2]), []).append(f)
    med = {k: sorted(v)[len(v) // 2] for k, v in by.items() if len(v) >= MIN_N}

    storm = {}
    for day, time, total, n500, n2000 in rows["storm"]:
        storm[int(_epoch(day, time))] = (total or 0, n500 or 0, n2000 or 0)

    kp_t = [_epoch(d, t) for d, t, _ in rows["kp"]]
    kp_v = [v for _, _, v in rows["kp"]]
    bar_t = [_epoch(d, t) for d, t, _ in rows["bar"]]
    bar_v = [v for _, _, v in rows["bar"]]

    def last(ts, vals, t, max_age):
        i = bisect.bisect_right(ts, t) - 1
        return vals[i] if i >= 0 and t - ts[i] <= max_age else None

    # comptage mondial : classes par terciles de la période (le niveau dépend de la saison)
    worlds = []
    samples = []
    for day, time, band, f in noise:
        ref = med.get((band, time[:2]))
        if ref is None:
            continue
        t = _epoch(day, time)
        b0 = int(t) // 300 * 300
        st = [storm.get(b0 - k * 300) for k in range(3)]
        st = [s for s in st if s]
        s15 = (sum(s[0] for s in st), sum(s[1] for s in st), sum(s[2] for s in st)) if st else None
        kp = last(kp_t, kp_v, t, 3 * 3600)
        bar = last(bar_t, bar_v, t, 1800)
        bar3 = last(bar_t, bar_v, t - 3 * 3600, 1800)
        trend = round(bar - bar3, 1) if bar is not None and bar3 is not None else None
        samples.append((band, f - ref, s15, kp, trend))
        if s15:
            worlds.append(s15[0])

    worlds.sort()
    t1 = worlds[len(worlds) // 3] if worlds else 0
    t2 = worlds[2 * len(worlds) // 3] if worlds else 0

    defs = [
        ("near", "Foudre à moins de 500 km", "impacts dans les 15 min autour de la mesure",
         ["aucun", "1 à 10", "plus de 10"], lambda s: None if not s[2] else _classes(s[2][1], [0, 10], ["aucun", "1 à 10", "plus de 10"])),
        ("far", "Foudre à moins de 2000 km", "impacts dans les 15 min autour de la mesure",
         ["aucun", "1 à 50", "51 à 500", "plus de 500"],
         lambda s: None if not s[2] else _classes(s[2][2], [0, 50, 500], ["aucun", "1 à 50", "51 à 500", "plus de 500"])),
        ("world", "Activité orageuse mondiale", f"impacts en 15 min, terciles de la période (≤ {t1}, ≤ {t2}, plus)",
         ["faible", "moyenne", "forte"], lambda s: None if not s[2] else _classes(s[2][0], [t1, t2], ["faible", "moyenne", "forte"])),
        ("kp", "Selon le Kp", "Kp NOAA le plus récent (moins de 3 h)",
         ["0 à 2", "3", "4", "5 et plus"], lambda s: None if s[3] is None else _classes(s[3], [2.67, 3.67, 4.67], ["0 à 2", "3", "4", "5 et plus"])),
        ("bar", "Tendance de la pression (3 h)", "station météo locale, hPa",
         ["baisse forte (< −2)", "baisse", "stable", "hausse"],
         lambda s: None if s[4] is None else _classes(s[4], [-2, -0.5, 0.5], ["baisse forte (< −2)", "baisse", "stable", "hausse"])),
    ]
    tables = []
    for key, title, tip, labels, classify in defs:
        acc = {(l, b): [0.0, 0] for l in labels for b in BANDS}
        for smp in samples:
            l = classify(smp)
            if l is None:
                continue
            a = acc[(l, smp[0])]
            a[0] += smp[1]
            a[1] += 1
        tables.append({"key": key, "title": title, "tip": tip, "rows": [
            {"label": l, "cells": [{"band": b, "n": acc[(l, b)][1],
                                    "excess": round(acc[(l, b)][0] / acc[(l, b)][1], 1) if acc[(l, b)][1] >= MIN_N else None}
                                   for b in BANDS]} for l in labels]})
    return {"ok": True, "n": len(samples), "bands": BANDS, "tables": tables,
            "with_storm": sum(1 for s in samples if s[2]), "with_kp": sum(1 for s in samples if s[3] is not None),
            "with_bar": sum(1 for s in samples if s[4] is not None)}


def since_day(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
