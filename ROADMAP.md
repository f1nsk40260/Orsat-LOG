# ORSAT-LOG — Feuille de route

Carnet de trafic radioamateur, simple à utiliser, connecté en **TCI**, orienté **analyse de la propagation**.
Style ORSAT (thème vieil or `rgb(207,181,59)`), Linux en priorité.

## Méthode de travail
- Claude écrit et pousse le code dans ce dépôt (`f1nsk40260/Orsat-LOG`, privé).
- Sur Main-PC : `~/Orsat-LOG`. Usage courant : icône ORSAT-LOG (Bureau/menu) ou commande `orsat-log`
  = récupère les modifs, recompile ce qui a changé, relance. `./update.sh` = installation complète.
- Retours de test : messages du terminal ou capture d'écran → correction → nouveau push.
- Petites livraisons : une fonction = un commit qui tourne.
- **Ce fichier est la mémoire du projet** : à mettre à jour à chaque livraison.

## Décisions techniques
| Sujet | Choix |
|---|---|
| Interface | Svelte 5 + Vite (`frontend/`), compilée dans `frontend/dist` |
| Backend | Python 3, FastAPI + uvicorn (`backend/orsatlog/`) |
| Fenêtre | pywebview (GTK/WebKit), repli automatique sur le navigateur |
| Base | SQLite : `~/.local/share/orsat-log/orsatlog.db` (variable `ORSATLOG_DATA` pour changer) |
| Radio | TCI WebSocket, port 40001 par défaut, récepteur 0 / VFO A |
| Solaire | hamqsl.com (SFI, A, K, X-ray), cache 15 min, figé dans chaque QSO |
| Échange | ADIF 3.1 (export fait, import à faire) |
| Port local | 8740 |

## Fait — v0.1.0 (20/10/2026)
- Squelette backend + frontend, thème ORSAT.
- Connexion TCI : fréquence, modulation, PTT, nom de l'appareil, reconnexion auto.
- Saisie QSO : heure UTC figée à la frappe de l'indicatif, fréquence/mode suivis depuis la radio,
  RST par défaut selon le mode, « déjà contacté » à la sortie du champ indicatif.
- Distance et azimut calculés depuis les locators.
- Contexte solaire (SFI/A/K) enregistré avec chaque QSO.
- Liste des QSO, suppression, export ADIF.
- Réglages : indicatif, locator, hôte/port TCI.
- Repli silencieux sur le navigateur si WebKit GTK absent (Main-PC : `sudo apt install gir1.2-webkit2-4.1`).

## À faire (ordre proposé)
1. Import ADIF (reprise de l'ancien carnet).
2. Édition d'un QSO existant.
3. Onglet **Analyse** : QSO par bande × heure UTC, carte des contacts (grand cercle depuis le QTH),
   distances max par bande, corrélation avec SFI/K.
4. Recherche / filtres dans le carnet (indicatif, bande, mode, période).
5. Préfixes → pays DXCC (cty.dat) et entité dans chaque QSO.
6. Spots TCI / DX cluster, croisement RBN / PSKReporter.
7. Envoi de commandes TCI (cliquer un spot = changer de fréquence).
8. Upload LoTW / QRZ / eQSL.

## Sources TCI visées
- **AetherSDR** (serveur TCI v2.0 : CAT, audio, IQ, CW, spots, événements récepteur ; FlexRadio en priorité,
  aussi récepteurs en réception seule). Port à régler dans les Réglages (pas de défaut documenté).
  → prévoir le choix du récepteur/slice suivi (aujourd'hui : récepteur 0 seulement).
- **Orsat-SDR** (plus tard) pour les logs SWL → nécessite d'ajouter un serveur TCI dans Orsat-SDR.

## Mode SWL (à concevoir)
- Écoute sans QSO : station entendue, report SINPO/SIO, langue, émetteur, pas de RST envoyé.
- Export ADIF avec marquage SWL.
- Identification automatique de la station par fréquence + heure via une grille de diffusion (EiBi)
  → émetteur et distance connus sans saisie : très utile pour l'analyse de propagation.
