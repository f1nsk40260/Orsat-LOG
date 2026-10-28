// Locator à placer dans la fenêtre Trajet, partagé avec le carnet : le dernier indicatif saisi (locator trouvé
// par QRZ ou tapé) remplace le précédent. Rien n'est enregistré.
export const traceTarget = $state({ loc: '', call: '', open: false });
