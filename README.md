# ORSAT-LOG

Carnet de trafic radioamateur orienté analyse de la propagation, installé sur le PC du
WebSDR **PhantomSDR-ORSAT** et servi par lui sous **https://orsat.ddns.net/log/**.

- **Exploitation** : depuis n'importe quel poste, dans un navigateur. Mot de passe = celui du
  panneau admin du WebSDR.
  - QSO / QSO de groupe : le navigateur se relie lui-même à AetherSDR (TCI, `ws://127.0.0.1:50001`
    sur le poste d'exploitation).
  - SWL : la page du WebSDR ouverte dans le même navigateur envoie fréquence et mode au carnet.
- **Gestion** : panneau admin du WebSDR, rubrique **Carnet ORSAT-LOG** : réglages (indicatif,
  locators station / WebSDR, TCI, météo), sauvegardes et restauration, mise à jour, état du service.

## Installation sur le PC du WebSDR (une seule fois)

```bash
cd ~ && git clone https://github.com/f1nsk40260/Orsat-LOG.git
cd ~/Orsat-LOG && bash install-server.sh ~/PhantomSDR-Plus
```

Le script crée le service systemd `orsat-log` (priorité basse, plafonds CPU et mémoire), ajoute
`log_port` à `admin_config.json` et relance le proxy du WebSDR (quelques secondes de coupure).
Prérequis : Python 3 avec venv, Node.js/npm (nvm accepté).

## Mises à jour

Depuis le panneau admin (rubrique Carnet ORSAT-LOG → METTRE À JOUR), ou à la main :

```bash
bash ~/Orsat-LOG/update-server.sh && sudo systemctl restart orsat-log
```

## Données

Indices solaires historiques : archive Kp / ap / Ap / SN / F10.7 du GFZ Potsdam (Matzka et al., 2021,
*Space Weather*, https://doi.org/10.1029/2020SW002641), licence CC BY 4.0.

Ionosphère mesurée (fiche QSO) : ionosondes du réseau GIRO, Lowell GIRO Data Center (Reinisch, B. W., and
I. A. Galkin, *Global ionospheric radio observatory (GIRO)*, Earth Planets Space, 63, 377-381, 2011 ;
http://spase.info/SMWG/Observatory/GIRO), licence CC BY-NC-SA 4.0, usage non commercial ; l'observatoire
fournisseur est cité dans chaque fiche.

Identification des écoutes SWL : grille des émissions en ondes courtes EiBi (Eike Bierwirth),
http://www.eibispace.de/.


`~/Orsat-LOG/data/` (jamais envoyé sur GitHub) : base `orsatlog.db`, copies quotidiennes
`backups/`, clé de session `secret.key`.

## Développement

```bash
.venv/bin/python run.py                              # serveur sur 127.0.0.1:8740
cd frontend && npm run dev                           # interface avec rechargement à chaud
```

Voir [ROADMAP.md](ROADMAP.md) pour l'état du projet.
