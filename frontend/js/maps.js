/* =========================================================================
   Les deux cartes Leaflet, synchronisées.
   -------------------------------------------------------------------------
   Exigence du sujet (§VII.5) : « A user must be able to look at the two maps
   and immediately see where the solvers agreed and where they did not. »

   Trois mécanismes rendent les différences visibles :
     1. les deux cartes sont SYNCHRONISÉES (même zoom, même cadrage), sinon
        la comparaison visuelle n'a aucun sens ;
     2. une borne choisie par UN SEUL solveur reçoit un contour jaune épais ;
     3. une zone couverte par UN SEUL solveur reçoit un anneau jaune.

   Le jaune est le slot 4 de la palette catégorielle, réservé ici au rôle
   « divergence entre solveurs ». Il n'est jamais utilisé pour autre chose
   sur la carte.
   ========================================================================= */

const MapPane = (() => {
  const css = (name) => getComputedStyle(document.documentElement)
    .getPropertyValue(name).trim();

  class Pane {
    constructor(elementId) {
      this.map = L.map(elementId, { zoomControl: true, attributionControl: true });
      this.tiles = null;
      this.setBasemap();

      // Ordre d'empilement : les polygones dessous, les bornes au-dessus.
      this.blockedLayer = L.layerGroup().addTo(this.map);
      this.radiusLayer = L.layerGroup().addTo(this.map);
      this.zoneLayer = L.layerGroup().addTo(this.map);
      this.candidateLayer = L.layerGroup().addTo(this.map);
      this._syncing = false;
    }

    /* Fond de carte : tuiles OpenStreetMap standard.

       Le sujet interdit toute clé d'API et tout service payant, donc on
       s'en tient au serveur de tuiles public d'OSM. (CARTO et Stadia, qui
       proposent de beaux fonds sombres, exigent désormais une clé : testés
       et écartés pour cette raison.)

       Pour que la carte s'intègre au thème sombre, le pane de tuiles est
       rendu semi-transparent par CSS : le fond sombre du conteneur Leaflet
       transparaît. `opacity` est une propriété COMPOSÉE par le GPU. Un
       `filter: invert()` donnerait un effet voisin mais force une
       rastérisation logicielle qui gèle le rendu plusieurs secondes :
       mesuré, puis abandonné. */
    setBasemap() {
      if (this.tiles) this.map.removeLayer(this.tiles);

      this.tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; contributeurs <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(this.map);

    }

    setView(center, zoom) { this.map.setView([center.lat, center.lon], zoom); }
    invalidate() { this.map.invalidateSize(); }

    /* Polygones inaccessibles : le Rhône, la Saône, l'emprise de Perrache. */
    drawBlocked(geojson) {
      this.blockedLayer.clearLayers();
      L.geoJSON(geojson, {
        style: (f) => ({
          color: f.properties.kind === 'water' ? css('--map-water') : css('--map-blocked'),
          weight: 1,
          fillColor: f.properties.kind === 'water' ? css('--map-water') : css('--map-blocked'),
          fillOpacity: 0.3,
          interactive: true,
        }),
        onEachFeature: (f, layer) =>
          layer.bindPopup(`<b>${f.properties.name}</b><br>Zone inaccessible : aucune demande.`),
      }).addTo(this.blockedLayer);
    }

    /* Zones de demande, colorées selon qu'elles sont couvertes ou non. */
    drawZones(zones, coveredSet, uniqueSet) {
      this.zoneLayer.clearLayers();
      const covered = css('--map-covered');
      const uncovered = css('--map-uncovered');
      const divergent = css('--series-4');

      for (const zone of zones) {
        const isCovered = coveredSet.has(zone.id);
        const isUnique = uniqueSet.has(zone.id);
        // Couvertes et non couvertes doivent se distinguer AU PREMIER COUP
        // D'OEIL : c'est l'exigence du sujet. Deux encodages redondants sont
        // donc employes, la teinte ET le remplissage — une zone couverte est
        // un disque plein, une zone non couverte un anneau creux.
        L.circleMarker([zone.lat, zone.lon], {
          radius: 4 + Math.min(zone.weight, 1) * 2.5,
          color: isUnique ? divergent : (isCovered ? covered : uncovered),
          weight: isUnique ? 2.5 : 1.6,
          fillColor: isCovered ? covered : uncovered,
          fillOpacity: isCovered ? 0.88 : 0.10,
          opacity: isCovered ? 1 : 0.85,
        })
          .bindPopup(
            `<b>Zone ${zone.id}</b><br>poids ${zone.weight}<br>` +
            (isCovered ? 'couverte' : 'non couverte') +
            (isUnique ? '<br><b>couverte par ce solveur seulement</b>' : ''))
          .addTo(this.zoneLayer);
      }
    }

    /* Candidats : losange numéroté si retenu, petit losange creux sinon.

       Le losange n'est pas décoratif — c'est lui qui sépare « emplacement
       constructible » de « zone de demande », qui reste un cercle. Voir le
       bloc .candidate-pin dans style.css pour le raisonnement. */
    drawCandidates(candidates, selection, uniqueStations, radiusM) {
      this.candidateLayer.clearLayers();
      this.radiusLayer.clearLayers();
      const chosen = new Set(selection);
      const unique = new Set(uniqueStations);
      const stationColor = css('--map-station');
      const divergent = css('--series-4');

      for (const cand of candidates) {
        const isChosen = chosen.has(cand.id);
        const isUnique = unique.has(cand.id);

        if (isChosen) {
          // Le disque de couverture : la visualisation du rayon r exigée
          // par le sujet (§VII.1).
          L.circle([cand.lat, cand.lon], {
            radius: radiusM,
            color: isUnique ? divergent : stationColor,
            weight: isUnique ? 2 : 1.5,
            dashArray: isUnique ? '5,4' : null,
            fillColor: stationColor,
            fillOpacity: 0.1,
            interactive: false,
          }).addTo(this.radiusLayer);
        }

        const icon = isChosen
          ? L.divIcon({
              className: '',
              html: `<div class="station-pin${isUnique ? ' unique' : ''}"><span>${cand.id}</span></div>`,
              iconSize: [24, 24], iconAnchor: [12, 12],
            })
          : L.divIcon({
              className: '',
              html: '<div class="candidate-pin"></div>',
              iconSize: [13, 13], iconAnchor: [6.5, 6.5],
            });

        L.marker([cand.lat, cand.lon], { icon, title: cand.name })
          .bindPopup(
            `<b>${cand.name}</b><br>candidat n° ${cand.id}<br>` +
            `peut couvrir un poids de ${cand.marginal_weight}<br>` +
            (isChosen
              ? (isUnique
                  ? '<b>retenu par ce solveur uniquement</b>'
                  : 'retenu par les deux solveurs')
              : 'non retenu'))
          .addTo(this.candidateLayer);
      }
    }
  }

  /* Synchronisation bidirectionnelle, avec garde anti-récursion. */
  function link(a, b) {
    const bind = (src, dst) => src.map.on('move zoom', () => {
      if (src._syncing) return;
      dst._syncing = true;
      dst.map.setView(src.map.getCenter(), src.map.getZoom(), { animate: false });
      dst._syncing = false;
    });
    bind(a, b);
    bind(b, a);
  }

  return { Pane, link };
})();
