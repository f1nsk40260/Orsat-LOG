<script>
  import { untrack } from 'svelte';
  import { api } from './api.js';

  let { settings, onclose, onsaved } = $props();

  let s = $state(untrack(() => ({ ...settings })));
  let error = $state('');

  // mise à jour depuis GitHub
  let upd = $state(null);         // { current, changes }
  let updState = $state('');      // '', 'check', 'run', message d'erreur
  async function checkUpdate() {
    updState = 'check';
    try { upd = await api.updateCheck(); updState = ''; }
    catch (err) { updState = err.message; }
  }
  async function runUpdate() {
    updState = 'run';
    try {
      await api.updateRun();
      // l'application redémarre : on attend le nouveau serveur puis on recharge la page
      await new Promise((r) => setTimeout(r, 4000));
      for (let i = 0; i < 90; i++) {
        try { await api.settings(); location.reload(); return; } catch { await new Promise((r) => setTimeout(r, 2000)); }
      }
      updState = 'Redémarrage trop long : relancer ORSAT-LOG depuis son icône.';
    } catch (err) { updState = err.message; }
  }

  async function save(e) {
    e.preventDefault();
    error = '';
    try {
      const saved = await api.saveSettings({
        callsign: s.callsign || '',
        locator: s.locator || '',
        tci_host: s.tci_host || '127.0.0.1',
        tci_port: String(s.tci_port || '50001'),
        tci_trx: String(s.tci_trx || '0'),
        tci_enabled: s.tci_enabled === '1' || s.tci_enabled === true ? '1' : '0',
        weathercloud: s.weathercloud || '',
        websdr_port: String(s.websdr_port || '40001'),
        websdr_enabled: s.websdr_enabled === '1' || s.websdr_enabled === true ? '1' : '0',
      });
      onsaved(saved);
    } catch (err) {
      error = err.message;
    }
  }
</script>

<div class="backdrop" onclick={onclose} role="presentation"></div>
<form class="panel dialog" onsubmit={save}>
  <h2 class="panel-title">Réglages</h2>

  <fieldset>
    <legend>Station</legend>
    <div class="row">
      <div>
        <label for="s-call">Indicatif</label>
        <input id="s-call" class="mono" bind:value={s.callsign}
               oninput={() => (s.callsign = s.callsign.toUpperCase())} />
      </div>
      <div>
        <label for="s-loc">Locator</label>
        <input id="s-loc" class="mono" bind:value={s.locator} maxlength="8"
               oninput={() => (s.locator = s.locator.toUpperCase())}
               title="Nécessaire au calcul des distances et azimuts" />
      </div>
    </div>
  </fieldset>

  <fieldset>
    <legend>Connexion TCI</legend>
    <label class="check">
      <input type="checkbox" checked={s.tci_enabled === '1'}
             onchange={(e) => (s.tci_enabled = e.currentTarget.checked ? '1' : '0')} />
      Activer la connexion TCI
    </label>
    <div class="row3">
      <div>
        <label for="s-host">Adresse</label>
        <input id="s-host" class="mono" bind:value={s.tci_host} />
      </div>
      <div>
        <label for="s-port">Port</label>
        <input id="s-port" class="mono" bind:value={s.tci_port}
               title="AetherSDR : 50001 · ExpertSDR / SunSDR : 40001" />
      </div>
      <div>
        <label for="s-trx">Récepteur</label>
        <select id="s-trx" bind:value={s.tci_trx} title="Récepteur TCI suivi (slice de la Flex)">
          {#each ['0', '1', '2', '3'] as n}<option value={n}>{'ABCD'[+n]} ({n})</option>{/each}
        </select>
      </div>
    </div>
    <p class="note">AetherSDR : ouvrir l'applet « TCI Server », port 50001, et démarrer le serveur.</p>
  </fieldset>

  <fieldset>
    <legend>WebSDR ORSAT</legend>
    <label class="check">
      <input type="checkbox" checked={s.websdr_enabled === '1'}
             onchange={(e) => (s.websdr_enabled = e.currentTarget.checked ? '1' : '0')} />
      Recevoir la fréquence de la page WebSDR
    </label>
    <label for="s-wport">Port TCI local</label>
    <input id="s-wport" class="mono" bind:value={s.websdr_port}
           title="La page ORSAT cherche 50001 et 40001 ; 50001 est pris par AetherSDR" />
    <p class="note">Sur la page ORSAT (même PC), activer « CAT Sync » : le carnet suit la fréquence écoutée.</p>
  </fieldset>

  <fieldset>
    <legend>Météo</legend>
    <label for="s-wc">Station Weathercloud</label>
    <input id="s-wc" class="mono" bind:value={s.weathercloud}
           placeholder="identifiant à 10 chiffres ou adresse de la station" />
    <p class="note">Ex. https://app.weathercloud.net/d9224966553 — relevé toutes les 15 min.</p>
  </fieldset>

  <fieldset>
    <legend>Mise à jour</legend>
    {#if upd}
      <div class="ver">Version installée : <b>{upd.current.version}</b>
        <span class="muted">({upd.current.commit} du {upd.current.date})</span></div>
      {#if upd.changes.length}
        <div class="news">{upd.changes.length} modification{upd.changes.length > 1 ? 's' : ''} disponible{upd.changes.length > 1 ? 's' : ''} :</div>
        <ul>{#each upd.changes.slice(0, 8) as c}<li>{c}</li>{/each}</ul>
      {:else}
        <div class="ok">ORSAT-LOG est à jour.</div>
      {/if}
    {/if}
    {#if updState === 'run'}
      <p class="note">Mise à jour en cours… l'application va se fermer puis se rouvrir (une minute environ).</p>
    {:else if updState && updState !== 'check'}
      <p class="error">{updState}</p>
    {/if}
    <div class="upd-btns">
      <button type="button" onclick={checkUpdate} disabled={updState === 'check' || updState === 'run'}>
        {updState === 'check' ? 'Vérification…' : 'Vérifier'}
      </button>
      <button type="button" class:primary={upd?.changes.length} onclick={runUpdate}
              disabled={updState === 'run'} title="Récupère les modifications, recompile et redémarre">
        Mettre à jour et redémarrer
      </button>
    </div>
  </fieldset>

  <div class="actions">
    {#if error}<span class="error">{error}</span>{/if}
    <button type="button" onclick={onclose}>Annuler</button>
    <button type="submit" class="primary">Enregistrer</button>
  </div>
</form>

<style>
  .backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); z-index: 10; }
  .dialog {
    position: fixed; z-index: 11; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: 460px; max-width: calc(100vw - 32px);
  }
  fieldset { border: 1px solid var(--panel-edge); border-radius: 6px; margin: 0 0 12px; padding: 10px 12px; }
  legend { color: var(--gold); padding: 0 6px; font-size: 0.85rem; }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .row3 { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 10px; }
  .note { color: var(--muted); font-size: 0.78rem; margin: 8px 0 0; }
  .check { display: flex; align-items: center; gap: 8px; text-transform: none; font-size: 0.88rem; margin-bottom: 10px; }
  .check input { width: auto; }
  .actions { display: flex; justify-content: flex-end; align-items: center; gap: 10px; }
  .error { color: var(--bad); margin-right: auto; }
  .ver { font-size: 0.85rem; }
  .muted { color: var(--muted); }
  .news { color: var(--gold); font-size: 0.85rem; margin-top: 6px; }
  ul { margin: 4px 0 0; padding-left: 18px; font-size: 0.8rem; max-height: 120px; overflow: auto; }
  .ok { color: var(--ok); font-size: 0.85rem; margin-top: 4px; }
  .upd-btns { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; }
  .dialog { max-height: calc(100vh - 32px); overflow: auto; }
</style>
