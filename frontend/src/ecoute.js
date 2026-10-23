// Page publique : où le WebSDR ORSAT entend bien en ce moment (aucune donnée du carnet, sans connexion)
import { mount } from 'svelte';
import './theme.css';
import Ecoute from './Ecoute.svelte';

export default mount(Ecoute, { target: document.getElementById('app') });
