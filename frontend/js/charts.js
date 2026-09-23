/* =========================================================================
   Graphiques (Chart.js).
   -------------------------------------------------------------------------
   Règles de visualisation appliquées ici :
     • palette catégorielle en ORDRE FIXE, jamais recyclée ;
     • un seul axe vertical, jamais deux échelles superposées ;
     • traits fins (2 px), grille discrète, texte en couleurs de texte
       (jamais en couleur de série) ;
     • légende présente dès 2 séries, PLUS étiquettes directes en bout de
       courbe tant qu'il y a 4 séries ou moins : l'identité ne repose ainsi
       jamais sur la seule couleur ;
     • infobulle au survol sur tous les graphiques.
   ========================================================================= */

const Charts = (() => {
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const registry = {};

  /* Étiquettes directes en bout de courbe. Secondary encoding : même si le
     lecteur ne distingue pas deux teintes, le nom est écrit à côté du trait. */
  const directLabels = {
    id: 'directLabels',
    afterDatasetsDraw(chart) {
      if (!chart.options.plugins.directLabels?.enabled) return;
      const { ctx } = chart;
      ctx.save();
      ctx.font = '600 11px ' + css('--mono');
      ctx.textBaseline = 'middle';
      // On collecte d'abord, puis on ecarte les etiquettes qui se chevauchent :
      // sans cela, deux courbes proches en fin de parcours ecrivent leur nom
      // l'une sur l'autre et plus rien n'est lisible.
      const labels = [];
      chart.data.datasets.forEach((ds, i) => {
        const meta = chart.getDatasetMeta(i);
        if (meta.hidden) return;
        const pts = meta.data.filter(Boolean);
        if (!pts.length) return;
        const last = pts[pts.length - 1];
        labels.push({ y: last.y, x: last.x, text: ds.shortLabel || ds.label,
                      color: ds.borderColor });
      });

      labels.sort((a, b) => a.y - b.y);
      const MIN_GAP = 13;
      for (let i = 1; i < labels.length; i++) {
        if (labels[i].y - labels[i - 1].y < MIN_GAP) {
          labels[i].y = labels[i - 1].y + MIN_GAP;
        }
      }

      for (const l of labels) {
        const w = ctx.measureText(l.text).width;
        let x = l.x + 7;
        let align = 'left';
        if (x + w > chart.width - 2) { x = l.x - 7; align = 'right'; }
        ctx.textAlign = align;
        ctx.fillStyle = l.color;
        ctx.fillText(l.text, x, l.y);
      }
      ctx.restore();
    },
  };

  /* Ligne horizontale de référence (l'énergie optimale, connue par la force brute). */
  const referenceLine = {
    id: 'referenceLine',
    afterDatasetsDraw(chart) {
      const cfg = chart.options.plugins.referenceLine;
      if (!cfg?.enabled || cfg.value === null || cfg.value === undefined) return;
      const y = chart.scales.y.getPixelForValue(cfg.value);
      if (!Number.isFinite(y)) return;
      const { ctx, chartArea } = chart;
      ctx.save();
      ctx.setLineDash([5, 4]);
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = css('--text-muted');
      ctx.beginPath();
      ctx.moveTo(chartArea.left, y);
      ctx.lineTo(chartArea.right, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = '600 10.5px ' + css('--mono');
      ctx.fillStyle = css('--text-muted');
      ctx.textAlign = 'left';
      ctx.textBaseline = 'bottom';
      ctx.fillText(cfg.label, chartArea.left + 6, y - 3);
      ctx.restore();
    },
  };

  Chart.register(directLabels, referenceLine);

  function baseOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 220 },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          align: 'start',
          labels: {
            boxWidth: 10, boxHeight: 2, padding: 12,
            color: css('--text-secondary'),
            font: { size: 11, family: css('--sans') },
            usePointStyle: false,
          },
        },
        tooltip: {
          backgroundColor: css('--surface-3'),
          titleColor: css('--text-primary'),
          bodyColor: css('--text-secondary'),
          borderColor: css('--border-strong'),
          borderWidth: 1, padding: 10, cornerRadius: 6,
          titleFont: { size: 12, family: css('--sans') },
          bodyFont: { size: 11.5, family: css('--mono') },
        },
      },
      scales: {
        x: {
          grid: { color: css('--border'), drawTicks: false },
          border: { color: css('--border') },
          ticks: { color: css('--text-muted'), font: { size: 10.5, family: css('--mono') } },
        },
        y: {
          grid: { color: css('--border'), drawTicks: false },
          border: { color: css('--border') },
          ticks: { color: css('--text-muted'), font: { size: 10.5, family: css('--mono') } },
        },
      },
    };
  }

  function destroy(key) {
    if (registry[key]) { registry[key].destroy(); delete registry[key]; }
  }

  const fmtSci = (v) => {
    if (v === 0) return '0';
    const e = Math.floor(Math.log10(Math.abs(v)));
    if (e >= -1 && e < 4) return Number(v.toPrecision(3)).toLocaleString('fr-FR');
    return `10^${e}`;
  };

  /* ---------------- Courbe de complexité : LE visuel du projet ---------- */
  function complexity(canvasId, data) {
    destroy(canvasId);
    const pts = data.points;
    const opts = baseOptions();

    opts.scales.y.type = 'logarithmic';
    opts.scales.y.title = {
      display: true, text: 'Travail (opérations, échelle log)',
      color: css('--text-muted'), font: { size: 11, family: css('--sans') },
    };
    opts.scales.y.ticks.callback = fmtSci;
    opts.scales.x.title = {
      display: true, text: 'N — nombre de candidats',
      color: css('--text-muted'), font: { size: 11, family: css('--sans') },
    };
    opts.layout = { padding: { right: 74 } };  // place pour les étiquettes directes
    opts.plugins.directLabels = { enabled: true };
    opts.plugins.tooltip.callbacks = {
      label: (c) => `${c.dataset.label} : ${fmtSci(c.parsed.y)} op.`,
    };

    // Ordre FIXE des slots : 1 bleu, 2 orange, 3 aqua, 4 jaune.
    // Le style de trait porte un second encodage : plein pour les deux
    // courbes qui portent l'argument, pointillé pour les deux courbes de
    // contexte (honnêteté : ce que fait vraiment ma force brute, et ce que
    // coûte vraiment ma simulation).
    const series = [
      { key: 'search_space',    color: css('--series-1'), dash: [],     short: '2^N',      label: 'Espace de recherche 2^N' },
      { key: 'brute_force',     color: css('--series-2'), dash: [5, 4],  short: 'brute',    label: 'Force brute réelle Σₖ≤B C(N,k)' },
      { key: 'qaoa_circuit',    color: css('--series-3'), dash: [],      short: 'QPU',      label: 'Circuit QAOA sur QPU O(p·N²)' },
      { key: 'qaoa_simulation', color: css('--series-4'), dash: [2, 3],  short: 'ma simu',  label: 'Ma simulation QAOA sur CPU' },
    ];

    registry[canvasId] = new Chart(document.getElementById(canvasId), {
      type: 'line',
      data: {
        labels: pts.map((p) => p.n),
        datasets: series.map((s) => ({
          label: s.label,
          shortLabel: s.short,
          data: pts.map((p) => p[s.key]),
          borderColor: s.color,
          backgroundColor: s.color,
          borderWidth: 2,
          borderDash: s.dash,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0,
        })),
      },
      options: opts,
    });
  }

  /* ---------------- Convergence de la boucle variationnelle -------------

     On ne superpose PAS la trace du recuit simulé ici. Son axe X (les
     « balayages de température ») n'est pas la même grandeur que celui de
     QAOA (les « évaluations de la fonction de cout »). Les placer sur une
     echelle commune produirait un graphique faux, qui inviterait a une
     comparaison depourvue de sens.                                        */
  function convergence(canvasId, trace, optimalEnergy) {
    destroy(canvasId);
    if (!trace || !trace.length) return;

    const opts = baseOptions();
    opts.layout = { padding: { right: 20, top: 8 } };
    opts.scales.x.title = {
      display: true, text: 'Evaluation de la fonction de cout',
      color: css('--text-muted'), font: { size: 11, family: css('--sans') },
    };
    opts.scales.y.title = {
      display: true, text: 'energie moyenne',
      color: css('--text-muted'), font: { size: 11, family: css('--sans') },
    };
    opts.plugins.legend.display = true;
    opts.plugins.directLabels = { enabled: false };
    opts.plugins.referenceLine = {
      enabled: optimalEnergy !== null && optimalEnergy !== undefined,
      value: optimalEnergy,
      label: `optimum exact  ${Number(optimalEnergy).toFixed(1)}`,
    };
    opts.plugins.tooltip.callbacks = {
      label: (c) => `${c.dataset.label} : ${c.parsed.y.toFixed(2)}`,
    };

    // La trace brute oscille : COBYLA explore, et chaque redemarrage repart
    // d'angles aleatoires. La montrer telle quelle est honnete. On y ajoute
    // le MINIMUM COURANT, qui est ce que l'algorithme retient reellement et
    // qui rend la descente lisible.
    let best = Infinity;
    const running = trace.map((v) => (best = Math.min(best, v)));

    registry[canvasId] = new Chart(document.getElementById(canvasId), {
      type: 'line',
      data: {
        labels: trace.map((_, i) => i),
        datasets: [
          {
            label: 'Energie evaluee',
            data: trace,
            borderColor: withAlpha(css('--series-1'), 0.3),
            backgroundColor: 'transparent',
            borderWidth: 1, pointRadius: 0, pointHoverRadius: 3, tension: 0,
          },
          {
            label: 'Meilleure energie atteinte',
            data: running,
            borderColor: css('--series-1'),
            backgroundColor: 'transparent',
            borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0,
          },
        ],
      },
      options: opts,
    });
  }

  /* Attenue une couleur de serie en lui donnant un canal alpha. */
  function withAlpha(hex, alpha) {
    const h = hex.replace('#', '');
    const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
    const n = parseInt(full, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }

  /* ---------------- Amplitudes : l'interference rendue visible ----------

     UNE seule serie de barres, plus une ligne de reference au niveau
     equiprobable 1/2^N. C'est plus lisible qu'une seconde serie « avant
     optimisation » : apres les portes de Hadamard tous les etats valent
     1/512 ~ 0,002, soit vingt fois moins que les barres finales. Ces
     barres-la n'auraient aucune hauteur rendable, et le message « c'etait
     plat au depart » ne passerait pas. Une ligne horizontale le dit mieux. */
  function amplitudes(canvasId, snapshots, nQubits) {
    destroy(canvasId);
    if (!snapshots || !snapshots.length) return false;

    const final = snapshots.find((s) => s.label === 'final');
    if (!final || !final.states.length) return false;

    const keyOf = (st) => (st.selection.length ? st.selection.join(', ') : 'aucune');
    const uniform = nQubits ? 1 / 2 ** nQubits : null;

    const opts = baseOptions();
    opts.layout = { padding: { top: 14 } };
    opts.plugins.legend.display = false;   // une seule serie : le titre suffit
    opts.plugins.directLabels = { enabled: false };
    opts.plugins.referenceLine = {
      enabled: uniform !== null,
      value: uniform,
      label: `niveau equiprobable  1/2^${nQubits}`,
    };
    opts.scales.y.title = {
      display: true, text: 'Probabilite de mesure',
      color: css('--text-muted'), font: { size: 11, family: css('--sans') },
    };
    opts.scales.y.ticks.callback = (v) => `${(v * 100).toFixed(1)} %`;
    opts.scales.x.ticks.maxRotation = 55;
    opts.scales.x.ticks.minRotation = 30;
    opts.scales.x.grid.display = false;
    opts.interaction = { mode: 'index', intersect: false };
    opts.plugins.tooltip.callbacks = {
      title: (items) => `bornes {${items[0].label}}`,
      label: (c) => {
        const st = final.states[c.dataIndex];
        const ratio = uniform ? ` (${(c.parsed.y / uniform).toFixed(0)}x le niveau uniforme)` : '';
        return [`probabilite ${(c.parsed.y * 100).toFixed(2)} %${ratio}`,
                `energie ${st.energy.toFixed(1)}`];
      },
    };

    registry[canvasId] = new Chart(document.getElementById(canvasId), {
      type: 'bar',
      data: {
        labels: final.states.map(keyOf),
        datasets: [{
          label: 'Probabilite apres optimisation',
          data: final.states.map((st) => st.probability),
          backgroundColor: css('--series-1'),
          borderRadius: 4, borderSkipped: 'bottom',
          borderWidth: 2, borderColor: css('--surface-1'),
        }],
      },
      options: opts,
    });
    return true;
  }

  function redrawAll() {
    Object.values(registry).forEach((c) => c.update('none'));
  }

  return { complexity, convergence, amplitudes, destroy, redrawAll, registry };
})();
