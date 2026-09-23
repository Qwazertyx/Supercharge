/* =========================================================================
   Orchestration.
   -------------------------------------------------------------------------
   Au démarrage, l'application charge l'INSTANCE DE RÉFÉRENCE documentée
   (Lyon, N=9, B=3, r=300 m, poids uniformes) et la résout immédiatement.
   C'est une exigence du sujet (§IX) : l'évaluation doit être reproductible,
   donc l'état initial doit être exactement celui décrit dans le README.
   ========================================================================= */

(() => {
  const $ = (id) => document.getElementById(id);

  const state = {
    static: null,      // géographie de Lyon, chargée une fois
    last: null,        // dernière réponse de /api/solve
    panes: {},
    defaults: null,
    busy: false,
  };

  /* ---------------- Lecture des contrôles ---------------- */
  function readParams() {
    const auto = $('penalty-auto').checked;
    return {
      budget: +$('budget').value,
      radius_m: +$('radius').value,
      weight_mode: $('weight-mode').value,
      respect_inaccessible: $('inaccessible').checked,
      n_candidates: +$('ncand').value,
      // Le curseur est logarithmique : il couvre 0,1× à 10 000× la borne
      // théorique, de façon à rendre les DEUX défaillances atteignables
      // en soutenance (infaisable d'un côté, paysage plat de l'autre).
      penalty: auto ? null : penaltyFromSlider(),
      layers: +$('layers').value,
      run_annealing: $('annealing').checked,
      record_trace: true,
      noise: {
        enabled: $('noise').checked,
        one_qubit_error: 1e-3,
        two_qubit_error: 1e-2,
        readout_error: 1e-2,
      },
    };
  }

  function penaltyFromSlider() {
    // On mémorise la borne théorique max Wᵢ la première fois qu'on la voit.
    // Elle ne dépend QUE de la géométrie et des poids, jamais de P — s'en
    // servir comme référence garde le curseur stable quand P change.
    const bound = state.penaltyBound || 10;
    return Math.max(1e-6, bound * 10 ** +$('penalty').value);
  }

  /* ---------------- Échos des contrôles ---------------- */
  function refreshEchoes() {
    const n = +$('ncand').value;
    const b = Math.min(+$('budget').value, n);

    $('budget').max = n;
    if (+$('budget').value > n) $('budget').value = n;

    $('budget-val').textContent = b;
    $('radius-val').textContent = `${$('radius').value} m`;
    $('radius-echo').textContent = $('radius').value;
    $('ncand-val').textContent = n;
    $('layers-val').textContent = $('layers').value;

    // Σₖ≤B C(n,k), calculé côté client pour un retour instantané.
    let total = 0;
    for (let k = 0; k <= b; k++) total += binom(n, k);
    $('combo-echo').textContent = total.toLocaleString('fr-FR');

    const auto = $('penalty-auto').checked;
    $('penalty').disabled = auto;
    if (auto) {
      $('penalty-val').textContent = 'auto';
      $('penalty-hint').textContent =
        "Décochez pour démontrer en direct l'effet d'un P mal choisi.";
    } else {
      const mult = 10 ** +$('penalty').value;
      $('penalty-val').textContent = `${formatMult(mult)} × borne`;
      $('penalty-hint').textContent = mult < 1
        ? 'P sous sa borne : attendez-vous à une solution INFAISABLE (budget dépassé).'
        : (mult > 100
            ? 'P très au-dessus : le paysage énergétique s\'aplatit, l\'optimiseur perd ses gradients.'
            : 'Zone saine : P dépasse le gain marginal maximal d\'une borne supplémentaire.');
    }
  }

  const formatMult = (m) => (m >= 10 ? m.toExponential(0).replace('e+', '×10^') :
    (m >= 1 ? m.toFixed(1) : m.toFixed(2)));

  function binom(n, k) {
    if (k < 0 || k > n) return 0;
    let r = 1;
    for (let i = 1; i <= k; i++) r = (r * (n - i + 1)) / i;
    return Math.round(r);
  }

  /* ---------------- Résolution ----------------

     Une résolution QAOA prend plusieurs secondes. Si l'utilisateur touche un
     curseur pendant ce temps, on ne doit NI lancer un second calcul en
     parallèle, NI ignorer son geste : l'affichage se retrouverait à montrer
     des chiffres qui ne correspondent plus aux réglages visibles, ce qui est
     exactement l'incohérence que le sujet sanctionne.

     On COALESCE donc : la demande la plus récente est mémorisée et relancée
     dès que le calcul en cours se termine. L'état affiché finit toujours par
     correspondre aux contrôles.                                            */
  let pendingSolve = false;

  async function solve() {
    if (state.busy) { pendingSolve = true; return; }

    state.busy = true;
    $('solve-btn').disabled = true;
    Panels.error('');
    Panels.status('Résolution en cours…', true);

    try {
      const t0 = performance.now();
      const data = await API.solve(readParams());
      state.last = data;
      state.penaltyBound = data.qubo.penalty_lower_bound;
      render(data);
      Panels.status(`Résolu en ${((performance.now() - t0) / 1000).toFixed(2)} s`, false);
    } catch (err) {
      Panels.error(err.message);
      Panels.status('', false);
    } finally {
      state.busy = false;
      $('solve-btn').disabled = false;
      if (pendingSolve) { pendingSolve = false; solve(); }
    }
  }

  /* ---------------- Rendu ---------------- */
  function render(data) {
    const { classical, quantum, annealing } = data.solvers;
    const diff = data.comparison.diff;
    const candidates = data.instance.candidates;
    const zones = data.instance.zones;
    const budget = data.params.budget;

    Panels.verdict(data.comparison.verdict);
    Panels.qubo(data.qubo, data.params);
    Panels.agreement(data.comparison.agreement);
    Panels.metrics(data.comparison.metrics, !!annealing);

    /* --- carte classique --- */
    state.panes.classical.drawZones(
      zones,
      new Set(classical.covered_zones),
      new Set(diff ? diff.only_classical_zones : []));
    state.panes.classical.drawCandidates(
      candidates, classical.selection,
      diff ? diff.only_classical_stations : [], data.params.radius_m);
    Panels.mapStats('stats-classical', classical, budget, data.instance.n_zones);
    Panels.stationList('list-classical', classical, candidates,
      diff ? diff.only_classical_stations : [],
      classical.optimal_ties > 1
        ? `<div class="hint" style="margin-top:7px">Ce problème admet
           <b>${classical.optimal_ties} placements optimaux distincts</b> de même
           couverture. La force brute retient le premier rencontré ; QAOA peut
           légitimement en retenir un autre.</div>`
        : '');

    /* --- carte quantique --- */
    if (quantum.skipped) {
      Panels.skip(quantum.reason);
      Panels.mapStats('stats-quantum', quantum, budget, data.instance.n_zones);
      Panels.stationList('list-quantum', quantum, candidates, [], '');
      Charts.destroy('chart-convergence');
      $('amplitudes-card').hidden = true;
    } else {
      Panels.skip(null);
      state.panes.quantum.invalidate();
      state.panes.quantum.drawZones(
        zones,
        new Set(quantum.covered_zones),
        new Set(diff ? diff.only_quantum_zones : []));
      state.panes.quantum.drawCandidates(
        candidates, quantum.selection,
        diff ? diff.only_quantum_stations : [], data.params.radius_m);
      Panels.mapStats('stats-quantum', quantum, budget, data.instance.n_zones);

      // Ce que le circuit a produit SANS filtrage. C'est ici que se voit
      // l'effet d'un poids de pénalité trop faible.
      const rawNote = quantum.budget_violated_in_raw
        ? `<div class="hint" style="margin-top:7px;color:var(--critical)">
             Le tirage le plus probable du circuit était
             <b>{${quantum.raw_selection.join(', ')}}</b>, soit
             <b>${quantum.raw_stations} bornes pour un budget de ${budget}</b> :
             une solution INFAISABLE. La pénalité est trop faible pour rendre le
             dépassement de budget coûteux. Le placement affiché est le meilleur
             tirage faisable effectivement mesuré.</div>`
        : `<div class="hint" style="margin-top:7px">Tirage le plus probable :
             {${quantum.raw_selection.join(', ')}} (p = ${(quantum.raw_probability * 100).toFixed(1)} %),
             ${quantum.shots.toLocaleString('fr-FR')} mesures,
             ${quantum.iterations} évaluations, p = ${quantum.layers} couches,
             ${quantum.gate_count} portes dont ${quantum.two_qubit_gates} CX.</div>`;

      // QUALITÉ DE LA DISTRIBUTION.
      // Le placement affiché est le meilleur tirage faisable mesuré, ce qui
      // est le protocole QAOA canonique. Mais ce chiffre-là ne dit RIEN de
      // l'effet du bruit : sur 4096 mesures dans un espace de 512 états, le
      // hasard seul finit par toucher l'optimum. Ce qui se dégrade vraiment,
      // c'est la DISTRIBUTION. On la compare donc au tirage uniforme.
      const uniformOpt = 100 / 2 ** quantum.n_qubits;
      const lift = quantum.p_optimum > 0 ? quantum.p_optimum * 100 / uniformOpt : 0;
      const collapsed = lift < 2;
      const qualityNote = `<div class="hint" style="margin-top:7px${
        collapsed ? ';color:var(--critical)' : ''}">
          Qualité de la distribution mesurée :
          <b>${(quantum.p_optimum * 100).toFixed(2)} %</b> des tirages atteignent l'optimum
          (<b>×${lift.toFixed(1)}</b> le niveau du hasard pur),
          <b>${(quantum.p_feasible * 100).toFixed(1)} %</b> respectent le budget.
          ${collapsed
            ? "La distribution s'est effondrée sur le tirage aléatoire : le circuit "
              + "ne porte plus d'information exploitable."
            : ''}
        </div>`;

      Panels.stationList('list-quantum', quantum, candidates,
        diff ? diff.only_quantum_stations : [], rawNote + qualityNote);

      Charts.convergence('chart-convergence', quantum.energy_trace, quantum.optimal_energy);

      // Le conteneur doit etre VISIBLE avant de construire le graphique :
      // Chart.js mesure la taille du canvas a la creation, et un canvas dans
      // un element `hidden` mesure zero. Il ne se remesure pas ensuite, et
      // toutes les barres se retrouvent ecrasees sur quelques pixels.
      $('amplitudes-card').hidden = false;
      const drawn = Charts.amplitudes('chart-amplitudes', quantum.amplitude_snapshots, quantum.n_qubits);
      $('amplitudes-card').hidden = !drawn;
    }

    refreshComplexity();
  }

  /* ---------------- Courbe de complexité ---------------- */
  async function refreshComplexity() {
    try {
      const data = await API.complexity({
        n_max: 60,
        budget: +$('budget').value,
        layers: +$('layers').value,
        budget_scales_with_n: $('budget-scales').checked,
      });
      state.complexity = data;
      Charts.complexity('chart-complexity', data);
      updateScaling();
    } catch (err) {
      Panels.error(`Courbe de complexité : ${err.message}`);
    }
  }

  /* ---------------- Démo de mise à l'échelle ---------------- */
  let scalingCache = null;
  async function ensureScalingData() {
    if (scalingCache) return scalingCache;
    scalingCache = await API.complexity({
      n_max: 80, budget: +$('budget').value, layers: +$('layers').value,
      budget_scales_with_n: $('budget-scales').checked,
    });
    return scalingCache;
  }

  async function updateScaling() {
    const n = +$('scale-n').value;
    $('scale-n-val').textContent = n;
    const data = await ensureScalingData();
    Panels.scaling(data.points.find((p) => p.n === n));
  }

  /* ---------------- Thème ---------------- */
  function toggleTheme() {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('supercharge-theme', next); } catch { /* mode privé */ }
    Object.values(state.panes).forEach((p) => p.setBasemap());
    // Les graphiques lisent les couleurs dans le CSS : il faut les reconstruire.
    if (state.last) {
      if (state.complexity) Charts.complexity('chart-complexity', state.complexity);
      const q = state.last.solvers.quantum;
      if (!q.skipped) {
        Charts.convergence('chart-convergence', q.energy_trace, q.optimal_energy);
        Charts.amplitudes('chart-amplitudes', q.amplitude_snapshots, q.n_qubits);
      }
      render(state.last);
    }
  }

  /* ---------------- Réinitialisation ---------------- */
  function resetToReference() {
    const d = state.defaults;
    $('budget').value = d.budget;
    $('radius').value = d.radius_m;
    $('ncand').value = d.n_candidates ?? state.static.candidates.length;
    $('weight-mode').value = d.weight_mode;
    $('inaccessible').checked = d.respect_inaccessible;
    $('penalty-auto').checked = true;
    $('penalty').value = 0.04;
    $('layers').value = 3;
    $('noise').checked = false;
    $('annealing').checked = true;
    refreshEchoes();
    solve();
  }

  /* ---------------- Démarrage ---------------- */
  async function boot() {
    try {
      const saved = localStorage.getItem('supercharge-theme');
      if (saved) document.documentElement.dataset.theme = saved;
    } catch { /* mode privé */ }

    Panels.status('Chargement de l\'instance…', true);
    let stat;
    try {
      stat = await API.instance();
    } catch (err) {
      Panels.error(`Impossible de charger l'instance : ${err.message}`);
      Panels.status('', false);
      return;
    }

    state.static = stat;
    state.defaults = stat.defaults;

    const refN = stat.defaults.n_candidates ?? stat.candidates.length;

    $('area-name').textContent =
      `${stat.area.name} · instance de référence N = ${refN} ` +
      `(${stat.candidates.length} emplacements disponibles) · ` +
      `${stat.zones.length} zones de demande`;

    // Bornes des curseurs, déduites des données réelles. On DÉMARRE sur
    // l'instance de référence documentée, pas sur le maximum disponible :
    // l'état initial doit être exactement celui décrit dans le README pour
    // que l'évaluation soit reproductible (sujet §IX).
    $('ncand').max = stat.candidates.length;
    $('ncand').value = refN;
    $('budget').max = stat.candidates.length;
    $('budget').value = stat.defaults.budget;
    $('radius').value = stat.defaults.radius_m;
    $('weight-mode').value = stat.defaults.weight_mode;
    $('inaccessible').checked = stat.defaults.respect_inaccessible;

    state.panes.classical = new MapPane.Pane('map-classical');
    state.panes.quantum = new MapPane.Pane('map-quantum');
    for (const pane of Object.values(state.panes)) {
      pane.setView(stat.area.center, stat.area.default_zoom);
      pane.drawBlocked(stat.inaccessible);
    }
    MapPane.link(state.panes.classical, state.panes.quantum);

    refreshEchoes();
    wire();
    await solve();
  }

  function wire() {
    $('solve-btn').addEventListener('click', solve);
    $('reset-btn').addEventListener('click', resetToReference);
    $('theme-toggle').addEventListener('click', toggleTheme);

    // Les curseurs mettent à jour les échos en continu, mais ne relancent
    // la résolution qu'au relâchement : QAOA prend plusieurs secondes, on ne
    // veut pas en lancer un par pixel de déplacement.
    for (const id of ['budget', 'radius', 'ncand', 'layers', 'penalty']) {
      $(id).addEventListener('input', refreshEchoes);
      $(id).addEventListener('change', solve);
    }
    for (const id of ['weight-mode', 'inaccessible', 'annealing', 'noise']) {
      $(id).addEventListener('change', solve);
    }
    $('penalty-auto').addEventListener('change', () => { refreshEchoes(); solve(); });

    $('budget-scales').addEventListener('change', () => {
      scalingCache = null;
      refreshComplexity();
    });
    $('scale-n').addEventListener('input', updateScaling);

    window.addEventListener('resize', () => {
      Object.values(state.panes).forEach((p) => p.invalidate());
    });
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
