import { useRef, useState, useEffect } from 'preact/hooks';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { setConfigValue, AuthError } from '../api';
import { useAppContext } from '../context';

// -------------------------------------------------------
// Geographic helpers
// -------------------------------------------------------

const R_EARTH = 6_371_000; // metres

function haversine(lat1, lon1, lat2, lon2) {
  const rLat1 = (lat1 * Math.PI) / 180;
  const rLat2 = (lat2 * Math.PI) / 180;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rLat1) * Math.cos(rLat2) * Math.sin(dLon / 2) ** 2;
  return R_EARTH * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** [lon, lat] of a point directly east of the given centre at radiusM metres. */
function eastEdge(lon, lat, radiusM) {
  const dLon = radiusM / (111_320 * Math.cos((lat * Math.PI) / 180));
  return [lon + dLon, lat];
}

/** GeoJSON polygon approximating a circle. */
function circleGeoJSON(lon, lat, radiusM, steps = 64) {
  const coords = [];
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const dLon =
      (radiusM / (111_320 * Math.cos((lat * Math.PI) / 180))) * Math.cos(angle);
    const dLat = (radiusM / 111_320) * Math.sin(angle);
    coords.push([lon + dLon, lat + dLat]);
  }
  return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] } };
}

/** Empty polygon used as placeholder before a zone is placed. */
function emptyPolygon() {
  return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [[]] } };
}

/** Rough zoom level that shows the circle with comfortable padding. */
function zoomForRadius(m) {
  return Math.max(1, Math.min(15, 14 - Math.log2(Math.max(m, 50) / 100)));
}

function fmtRadius(m) {
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;
}

// -------------------------------------------------------
// ZoneEditor component
// -------------------------------------------------------

export function ZoneEditor({ value, mapboxKey, pluginName, fieldKey, onSave, onClose }) {
  const { onAuthError } = useAppContext();

  const dialogRef = useRef(null);
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const centreMarkerRef = useRef(null);
  const edgeMarkerRef = useRef(null);

  // Refs hold the live values used inside map event handlers (avoids stale closures).
  const centreRef = useRef({ lon: value?.lon ?? 0, lat: value?.lat ?? 0 });
  const radiusRef = useRef(value?.rad ?? 0);

  const hasInitialZone = !!(value && value.rad > 0);

  // State for rendering the UI only.
  const [displayCentre, setDisplayCentre] = useState(centreRef.current);
  const [displayRadius, setDisplayRadius] = useState(radiusRef.current);
  const [hasZone, setHasZone] = useState(hasInitialZone);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog.showModal();

    mapboxgl.accessToken = mapboxKey;
    const map = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: 'mapbox://styles/mapbox/streets-v12',
      center: hasInitialZone
        ? [centreRef.current.lon, centreRef.current.lat]
        : [0, 0],
      zoom: hasInitialZone ? zoomForRadius(radiusRef.current) : 2,
    });
    mapRef.current = map;

    map.addControl(new mapboxgl.NavigationControl(), 'top-right');

    map.on('load', () => {
      // GeoJSON source + layers for the zone circle
      map.addSource('zone', {
        type: 'geojson',
        data: hasInitialZone
          ? circleGeoJSON(centreRef.current.lon, centreRef.current.lat, radiusRef.current)
          : emptyPolygon(),
      });

      map.addLayer({
        id: 'zone-fill',
        type: 'fill',
        source: 'zone',
        paint: { 'fill-color': '#0d9488', 'fill-opacity': 0.15 },
      });

      map.addLayer({
        id: 'zone-outline',
        type: 'line',
        source: 'zone',
        paint: { 'line-color': '#0d9488', 'line-width': 2 },
      });

      // Shared flag set after any handle dragend to suppress the map click
      // that Mapbox fires on the same mouseup event.
      let justDragged = false;
      function markDragged() {
        justDragged = true;
        setTimeout(() => { justDragged = false; }, 100);
      }

      // Centre handle
      const centreEl = document.createElement('div');
      centreEl.className = 'zone-centre-handle';
      if (!hasInitialZone) centreEl.style.display = 'none';

      const centreMarker = new mapboxgl.Marker({ element: centreEl, draggable: true })
        .setLngLat([centreRef.current.lon, centreRef.current.lat])
        .addTo(map);
      centreMarkerRef.current = centreMarker;

      centreMarker.on('drag', () => {
        const pos = centreMarker.getLngLat();
        centreRef.current = { lon: pos.lng, lat: pos.lat };
        map.getSource('zone').setData(
          circleGeoJSON(pos.lng, pos.lat, radiusRef.current)
        );
        edgeMarkerRef.current.setLngLat(eastEdge(pos.lng, pos.lat, radiusRef.current));
        setDisplayCentre({ lon: pos.lng, lat: pos.lat });
      });

      centreMarker.on('dragend', () => {
        markDragged();
        const pos = centreMarker.getLngLat();
        centreRef.current = { lon: pos.lng, lat: pos.lat };
        setDisplayCentre({ lon: pos.lng, lat: pos.lat });
      });

      // Edge (resize) handle
      const edgeEl = document.createElement('div');
      edgeEl.className = 'zone-edge-handle';
      if (!hasInitialZone) edgeEl.style.display = 'none';

      const edgeMarker = new mapboxgl.Marker({ element: edgeEl, draggable: true })
        .setLngLat(
          hasInitialZone
            ? eastEdge(centreRef.current.lon, centreRef.current.lat, radiusRef.current)
            : [0, 0]
        )
        .addTo(map);
      edgeMarkerRef.current = edgeMarker;

      edgeMarker.on('drag', () => {
        const pos = edgeMarker.getLngLat();
        const newR = Math.max(
          50,
          haversine(centreRef.current.lat, centreRef.current.lon, pos.lat, pos.lng)
        );
        map.getSource('zone').setData(
          circleGeoJSON(centreRef.current.lon, centreRef.current.lat, newR)
        );
        setDisplayRadius(newR);
      });

      edgeMarker.on('dragend', () => {
        markDragged();
        const pos = edgeMarker.getLngLat();
        const newR = Math.max(
          50,
          haversine(centreRef.current.lat, centreRef.current.lon, pos.lat, pos.lng)
        );
        radiusRef.current = newR;
        setDisplayRadius(newR);
        // Snap back to exact east edge at the final radius
        edgeMarker.setLngLat(eastEdge(centreRef.current.lon, centreRef.current.lat, newR));
      });

      // Map click:
      // Ignore if a handle was just dragged
      // Ignore if click is inside the circle
      // Else move the zone centre to the clicked point
      map.on('click', e => {
        if (justDragged) return;

        if (radiusRef.current > 0) {
          const d = haversine(
            centreRef.current.lat, centreRef.current.lon,
            e.lngLat.lat, e.lngLat.lng
          );
          if (d < radiusRef.current) return;
        }

        const newCentre = { lon: e.lngLat.lng, lat: e.lngLat.lat };
        const newR = radiusRef.current > 0 ? radiusRef.current : 1000;

        centreRef.current = newCentre;
        radiusRef.current = newR;
        setDisplayCentre({ ...newCentre });
        setDisplayRadius(newR);
        setHasZone(true);

        map.getSource('zone').setData(circleGeoJSON(newCentre.lon, newCentre.lat, newR));

        centreMarker.getElement().style.display = '';
        centreMarker.setLngLat([newCentre.lon, newCentre.lat]);

        edgeMarker.getElement().style.display = '';
        edgeMarker.setLngLat(eastEdge(newCentre.lon, newCentre.lat, newR));
      });
    });

    // ESC closes the dialog via the native cancel event
    const handleCancel = e => { e.preventDefault(); onClose(); };
    dialog.addEventListener('cancel', handleCancel);

    return () => {
      map.remove();
      dialog.removeEventListener('cancel', handleCancel);
    };
  }, []);

  async function handleSave() {
    if (!hasZone) return;
    setSaving(true);
    setSaveError(null);
    const newValue = {
      lat: centreRef.current.lat,
      lon: centreRef.current.lon,
      rad: radiusRef.current,
    };
    try {
      await setConfigValue(`${pluginName}.${fieldKey}`, newValue);
      onSave(newValue);
      dialogRef.current.close();
      onClose();
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setSaveError('Failed to save. Check the console for details.');
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    dialogRef.current.close();
    onClose();
  }

  return (
    <dialog ref={dialogRef} class="zone-dialog">
      <article>
        <header class="zone-dialog-header">
          <strong>Set Zone</strong>
          <p>
            Drag the centre handle to reposition. Drag the edge handle to resize.
            Click outside the circle to move the centre there.
          </p>
        </header>

        <div ref={mapContainerRef} class="zone-map" />

        <footer class="zone-dialog-footer">
          <div class="zone-footer-info">
            {hasZone ? (
              <span>
                {Number(displayCentre.lat).toFixed(5)}°,&nbsp;
                {Number(displayCentre.lon).toFixed(5)}°
                &nbsp;·&nbsp;
                {fmtRadius(displayRadius)}
              </span>
            ) : (
              <span class="zone-unset">Click the map to place a zone</span>
            )}
          </div>

          {saveError && <p class="save-status save-status-err" style="margin:0">{saveError}</p>}

          <div class="zone-footer-buttons">
            <button type="button" class="outline" onClick={handleCancel}
                    style="width: auto; margin: 0;">
              Cancel
            </button>
            <button type="button" onClick={handleSave}
                    disabled={saving || !hasZone} aria-busy={saving}
                    style="width: auto; margin: 0;">
              Save
            </button>
          </div>
        </footer>
      </article>
    </dialog>
  );
}
