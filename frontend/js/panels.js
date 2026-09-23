/* =========================================================================
   Rendu des panneaux textuels : verdict, badges QUBO, statistiques de carte,
   tableau de métriques, démo de mise à l'échelle.

   Aucune valeur n'est recalculée ici. Tout vient du backend, qui l'a lui-même
   obtenu de la fonction objectif exacte. C'est ce qui garantit qu'un chiffre
   affiché ne peut pas contredire la carte.
   ========================================================================= */

const Panels = (() => {
  const $ = (id) => document.getElementById(id);
  const nf = new Intl.NumberFormat('fr-FR');
  const fmt = (v) => (v === null || v === undefined ? '—' : nf.format(v));
  const pct = (v) => (v === null || v === undefined ? '—' : `${v.toFixed(1)} %`);

  /* ---------------- Verdict ---------------- */
  function verdict(v) {
    $('verdict').hidden = false;
    $('verdict-headline').textContent = v.headline;
    $('verdict-detail').textContent = v.detail;
    const note = $('verdict-annealing');
    if (v.annealing_note) {
      note.hidden = false;
      note.textContent = v.annealing_note;
    } else {
      note.hidden = true;
    }
  }

  /* ---------------- Diagnostic du QUBO ----------------
     Les deux badges répondent en direct aux deux questions que le sujet
     annonce : la troncature au degré 2 est-elle exacte ici, et le poids de
     pénalité est-il au-dessus de sa borne théorique ?                      */
  function qubo(q, params) {
    const f = q.fidelity;
    const safe = q.penalty_is_safe;

    const badges = [
      {
        cls: f.exact ? 'ok' : 'warn',
        html: f.exact
          ? `QUBO <strong>exact</strong> · multiplicité max <strong>${f.max_multiplicity}</strong>`
          : `QUBO <strong>approché</strong> · ${f.zones_at_risk} zone(s) à multiplicité <strong>${f.max_multiplicity}</strong>`,
      },
      {
        cls: safe ? 'ok' : 'danger',
        html: `Pénalité P = <strong>${q.penalty.toFixed(2)}</strong> ` +
              (safe ? '&gt;' : '<b>&lt;</b>') +
              ` borne <strong>${q.penalty_lower_bound.toFixed(2)}</strong>` +
              (safe ? '' : ' · budget non garanti'),
      },
      { cls: '', html: `<strong>${q.n_couplings}</strong> couplages Ising` },
      {
        cls: '',
        html: `P ${params.penalty_is_auto ? 'automatique' : '<strong>forcé à la main</strong>'}`,
      },
    ];

    $('qubo-badges').innerHTML = badges
      .map((b) => `<span class="badge ${b.cls}"><span class="dot"></span>${b.html}</span>`)
      .join('');

    let msg = f.message;
    if (!safe) {
      msg += ' ⚠️ Le poids de pénalité est SOUS sa borne théorique max Wᵢ : ' +
             'rien ne garantit plus que l\'état fondamental du QUBO respecte le budget. ' +
             'C\'est exactement la défaillance « P trop petit ».';
    }
    $('qubo-message').textContent = msg;
  }

  /* ---------------- Bandeau de statistiques sous une carte ---------------- */
  function mapStats(containerId, solver, budget, totalZones) {
    const el = $(containerId);
    if (!solver || solver.skipped) { el.innerHTML = ''; return; }

    const cells = [
      ['Couverture', pct(solver.coverage_ratio * 100)],
      ['Bornes', `${solver.stations_used}/${budget}`],
      ['Non couvertes', `${solver.uncovered_zones.length}/${totalZones}`],
      ['Temps', solver.elapsed_ms < 1000
        ? `${solver.elapsed_ms.toFixed(1)} ms`
        : `${(solver.elapsed_ms / 1000).toFixed(2)} s`],
    ];
    el.innerHTML = cells
      .map(([k, v]) => `<div><div class="k">${k}</div><div class="v">${v}</div></div>`)
      .join('');
  }

  /* ---------------- Liste nominative des bornes retenues ---------------- */
  function stationList(containerId, solver, candidates, uniqueIds, extraHtml) {
    const el = $(containerId);
    if (!solver || solver.skipped) { el.innerHTML = extraHtml || ''; return; }

    const unique = new Set(uniqueIds || []);
    const chips = solver.selection.map((id) => {
      const c = candidates.find((x) => x.id === id);
      const uniq = unique.has(id) ? ' uniq' : '';
      const title = unique.has(id) ? ' title="choisie par ce solveur uniquement"' : '';
      return `<span class="chip${uniq}"${title}>${id} · ${c ? c.name : '?'}</span>`;
    }).join('');

    el.innerHTML = (chips || '<i>aucune borne</i>') + (extraHtml || '');
  }

  /* ---------------- Tableau de métriques ---------------- */
  function metrics(rows, hasAnnealing) {
    $('th-annealing').hidden = !hasAnnealing;

    const body = rows.map((r) => {
      const isPct = r.unit === '%';
      const show = (v) => {
        if (v === null || v === undefined) return '—';
        if (isPct) return pct(v);
        return typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(2) : fmt(v);
      };

      // Le delta n'a de sens que si les deux valeurs existent.
      let delta = '—';
      if (r.classical !== null && r.quantum !== null &&
          r.classical !== undefined && r.quantum !== undefined) {
        const d = r.quantum - r.classical;
        const sign = d > 0 ? '+' : '';
        delta = isPct
          ? `${sign}${d.toFixed(1)} pts`
          : `${sign}${nf.format(Number(d.toFixed(2)))}`;
        if (Math.abs(d) < 1e-9) delta = '0';
      }

      const annealCell = hasAnnealing
        ? `<td>${show(r.annealing)}${r.unit && !isPct ? ` <span class="help" style="display:inline">${''}</span>` : ''}</td>`
        : '';

      return `<tr>
        <td>${r.label}<span class="help">${r.help}</span></td>
        <td>${show(r.classical)}</td>
        <td>${show(r.quantum)}</td>
        ${annealCell}
        <td>${delta}</td>
      </tr>`;
    }).join('');

    $('metrics-body').innerHTML = body;
  }

  /* ---------------- Badge d'accord entre solveurs ----------------
     Distingue « placements identiques », « optima équivalents » (des
     placements différents couvrant le même poids : personne ne se trompe)
     et « QAOA sous l'optimum ». Cette distinction est essentielle : sans
     elle on accuse QAOA d'une erreur qu'il n'a pas commise.               */
  function agreement(a) {
    const badge = $('agreement-badge');
    badge.hidden = false;
    const cls = { identical: 'ok', degenerate: 'ok', suboptimal: 'warn', skipped: 'warn' };
    badge.className = `badge ${cls[a.code] || ''}`;
    badge.innerHTML = `<span class="dot"></span>${a.label}`;
    $('agreement-detail').textContent = a.detail || '';
  }

  /* ---------------- Démo de mise à l'échelle ---------------- */
  function scaling(point) {
    if (!point) return;
    const alarm = point.search_space > 1e15;
    $('scale-grid').innerHTML = [
      ['Espace de recherche 2^N', formatBig(point.search_space), alarm ? 'alarm' : ''],
      ['Combinaisons réellement testées', formatBig(point.brute_force), ''],
      ['Temps pour tout énumérer', point.search_space_duration, alarm ? 'alarm' : ''],
      ['Portes du circuit QAOA', formatBig(point.qaoa_circuit), 'calm'],
    ].map(([k, v, cls]) =>
      `<div><div class="k">${k}</div><div class="v ${cls}">${v}</div></div>`).join('');
  }

  function formatBig(v) {
    if (v < 1e6) return nf.format(Math.round(v));
    const e = Math.floor(Math.log10(v));
    const m = v / 10 ** e;
    return `${m.toFixed(2)} × 10^${e}`;
  }

  /* ---------------- États transverses ---------------- */
  function status(text, busy) {
    $('status').innerHTML = text
      ? `${busy ? '<span class="spin"></span>' : ''}<span>${text}</span>`
      : '';
  }

  function error(message) {
    $('error-slot').innerHTML = message
      ? `<div class="errorbox"><b>Erreur.</b> ${message}</div>`
      : '';
  }

  function skip(reason) {
    const box = $('skip-quantum');
    const map = $('map-quantum');
    if (reason) {
      box.hidden = false; map.hidden = true;
      box.innerHTML = `<div><b>QAOA ignoré.</b><br><br>${reason}</div>`;
    } else {
      box.hidden = true; map.hidden = false;
    }
  }

  return {
    verdict, qubo, mapStats, stationList, metrics,
    agreement, scaling, status, error, skip, formatBig,
  };
})();
