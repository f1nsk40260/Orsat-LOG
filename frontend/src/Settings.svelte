<script>
  import { untrack } from 'svelte';
  import { api } from './api.js';

  let { settings, onclose, onsaved } = $props();

  let s = $state(untrack(() => ({ ...settings })));
  let error = $state('');

  async function save(e) {
    e.preventDefault();
    error = '';
    try {
      const saved = await api.saveSettings({
        callsign: s.callsign || '',
        locator: s.locator || '',
        tci_host: s.tci_host || '127.0.0.1',
        tci_port: String(s.tci_port || '40001'),
        tci_enabled: s.tci_enabled === '1' || s.tci_enabled === true ? '1' : '0',
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
    <div class="row">
      <div>
        <label for="s-host">Adresse</label>
        <input id="s-host" class="mono" bind:value={s.tci_host} />
      </div>
      <div>
        <label for="s-port">Port</label>
        <input id="s-port" class="mono" bind:value={s.tci_port} />
      </div>
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
  .check { display: flex; align-items: center; gap: 8px; text-transform: none; font-size: 0.88rem; margin-bottom: 10px; }
  .check input { width: auto; }
  .actions { display: flex; justify-content: flex-end; align-items: center; gap: 10px; }
  .error { color: var(--bad); margin-right: auto; }
</style>
