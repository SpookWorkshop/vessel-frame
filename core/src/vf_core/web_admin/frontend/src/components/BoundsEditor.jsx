import { useRef, useState, useEffect } from 'preact/hooks';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { setConfigValue, AuthError } from '../api';
import { useAppContext } from '../context';

// -------------------------------------------------------
// Box geometry helpers
// -------------------------------------------------------

/**
 * Compute the pixel position and size of each orientation's overlay box,
 * centred within the map container, maintaining the renderer's aspect ratio.
 *
 * rendererW/H are the effective canvas dimensions after orientation swap
 * (portrait: height > width; landscape: width > height).
 */
function computeBoxes(containerW, containerH, rendererW, rendererH) {
  const MAX = 0.82;

  function fitBox(aspectW, aspectH) {
    let w = containerW * MAX;
    let h = w * (aspectH / aspectW);
    if (h > containerH * MAX) {
      h = containerH * MAX;
      w = h * (aspectW / aspectH);
    }
    return {
      w: Math.round(w),
      h: Math.round(h),
      left: Math.round((containerW - w) / 2),
      top: Math.round((containerH - h) / 2),
    };
  }

  return {
    portrait:  fitBox(rendererW, rendererH),
    landscape: fitBox(rendererH, rendererW),
  };
}

function fmtCoord(v, posLabel, negLabel) {
  return `${Math.abs(Number(v)).toFixed(4)}°${Number(v) >= 0 ? posLabel : negLabel}`;
}

function fmtLiveBbox(b) {
  if (!b) return null;
  return (
    `${fmtCoord(b.min_lat, 'N', 'S')}–${fmtCoord(b.max_lat, 'N', 'S')}` +
    `  ·  ` +
    `${fmtCoord(b.min_lon, 'E', 'W')}–${fmtCoord(b.max_lon, 'E', 'W')}`
  );
}

// -------------------------------------------------------
// BoundsEditor component
// -------------------------------------------------------

export function BoundsEditor({value, mapboxKey, pluginName, fieldKey, rendererW, rendererH, onSave, onClose,}) {
  const { onAuthError } = useAppContext();

  const dialogRef   = useRef(null);
  const wrapperRef  = useRef(null);
  const mapRef      = useRef(null);
  const boxDimsRef  = useRef(null);

  const [boxes, setBoxes] = useState(null);
  const [liveBbox, setLiveBbox] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog.showModal();

    // Measure container
    const wrapper = wrapperRef.current;
    const containerW = wrapper.offsetWidth;
    const containerH = wrapper.offsetHeight;

    const computed = computeBoxes(containerW, containerH, rendererW, rendererH);
    boxDimsRef.current = computed;
    setBoxes(computed);

    mapboxgl.accessToken = mapboxKey;
    const map = new mapboxgl.Map({
      container: wrapperRef.current, // Mapbox renders directly into the wrapper
      style: 'mapbox://styles/mapbox/streets-v12', // move styles into system config so we can use here?
      center: [0, 0],
      zoom: 2,
    });
    mapRef.current = map;

    map.addControl(new mapboxgl.NavigationControl(), 'top-right');

    map.on('load', () => {
      if (value) {
        const p = computed.portrait;
        map.fitBounds(
          [[value.min_lon, value.min_lat], [value.max_lon, value.max_lat]],
          {
            padding: {
              top:    p.top,
              bottom: containerH - p.top - p.h,
              left:   p.left,
              right:  containerW - p.left - p.w,
            },
            animate: false,
          }
        );
      }
    });

    // Update the live bbox readout whenever the map moves
    function updateLive() {
      const p = boxDimsRef.current?.portrait;
      if (!p) return;
      const sw = map.unproject([p.left,       p.top + p.h]);
      const ne = map.unproject([p.left + p.w, p.top]);
      setLiveBbox({ min_lon: sw.lng, min_lat: sw.lat, max_lon: ne.lng, max_lat: ne.lat });
    }
    map.on('move', updateLive);

    const handleCancel = e => { e.preventDefault(); onClose(); };
    dialog.addEventListener('cancel', handleCancel);

    return () => {
      map.remove();
      dialog.removeEventListener('cancel', handleCancel);
    };
  }, []);

  async function handleSave() {
    const p = boxDimsRef.current?.portrait;
    const map = mapRef.current;
    if (!p || !map) return;

    setSaving(true);
    setSaveError(null);

    const sw = map.unproject([p.left,       p.top + p.h]);
    const ne = map.unproject([p.left + p.w, p.top]);
    const newValue = {
      min_lon: sw.lng,
      min_lat: sw.lat,
      max_lon: ne.lng,
      max_lat: ne.lat,
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

  // Inline styles for the two overlay boxes, derived from computed geometry
  const portraitStyle = boxes ? {
    position: 'absolute',
    left:   boxes.portrait.left,
    top:    boxes.portrait.top,
    width:  boxes.portrait.w,
    height: boxes.portrait.h,
    boxShadow: '0 0 0 9999px rgba(0,0,0,0.42)',
    border: '2px solid #0d9488',
    pointerEvents: 'none',
    zIndex: 2,
  } : null;

  const landscapeStyle = boxes ? {
    position: 'absolute',
    left:   boxes.landscape.left,
    top:    boxes.landscape.top,
    width:  boxes.landscape.w,
    height: boxes.landscape.h,
    border: '2px dashed rgba(13,148,136,0.75)',
    pointerEvents: 'none',
    zIndex: 3,
  } : null;

  return (
    <dialog ref={dialogRef} class="bounds-dialog">
      <article>
        <header class="zone-dialog-header">
          <strong>Set Map Bounds</strong>
          <p>
            Pan and zoom so the portrait box covers the area you want to display.
            The dashed box shows the same area in landscape orientation.
          </p>
        </header>

        {/* Map + overlay boxes share the same wrapper div */}
        <div ref={wrapperRef} class="bounds-map-wrap">
          {portraitStyle && (
            <div style={portraitStyle}>
              <span class="bounds-box-label">Portrait</span>
            </div>
          )}
          {landscapeStyle && (
            <div style={landscapeStyle}>
              <span class="bounds-box-label bounds-box-label-landscape">Landscape</span>
            </div>
          )}
        </div>

        <footer class="zone-dialog-footer">
          <div class="zone-footer-info">
            {liveBbox
              ? <span>{fmtLiveBbox(liveBbox)}</span>
              : <span class="zone-unset">Pan and zoom to set bounds</span>
            }
          </div>

          {saveError && (
            <p class="save-status save-status-err" style="margin:0">{saveError}</p>
          )}

          <div class="zone-footer-buttons">
            <button type="button" class="outline" onClick={handleCancel}
                    style="width: auto; margin: 0;">
              Cancel
            </button>
            <button type="button" onClick={handleSave}
                    disabled={saving} aria-busy={saving}
                    style="width: auto; margin: 0;">
              Save
            </button>
          </div>
        </footer>
      </article>
    </dialog>
  );
}
