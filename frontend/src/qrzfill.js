// Saisie d'un indicatif (QSO, QSO de groupe) : recherche dans l'annuaire QRZ.com et remplissage
// des cases restées vides (locator, nom, QTH). Attend une pause de frappe ; une réponse arrivée
// après un changement d'indicatif est ignorée.
import { api } from './api.js';

const CALL_RE = /^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,4}[A-Z](\/[A-Z0-9]+)?$|^[A-Z0-9]+\/[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,4}[A-Z]$/;

export function qrzFiller() {
  let timer = null;
  /** target : objet du formulaire ($state) avec call, gridsquare, name, qth. */
  return function fill(target, delay = 700) {
    clearTimeout(timer);
    const call = (target.call || '').trim().toUpperCase();
    if (!CALL_RE.test(call)) return;
    timer = setTimeout(async () => {
      const r = await api.qrzLookup(call).catch(() => null);
      if (!r?.ok || (target.call || '').trim().toUpperCase() !== call) return;
      const base = call.split('/').length > 1 ? null : r;   // portable (F/…, …/P) : QTH du moment inconnu
      if (base?.grid && !target.gridsquare) target.gridsquare = base.grid;
      if (r.fname && !target.name) target.name = r.nickname || r.fname;
      if (base?.qth && !target.qth) target.qth = base.qth;
    }, delay);
  };
}
