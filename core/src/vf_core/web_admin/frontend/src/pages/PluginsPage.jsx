import { useState, useEffect } from 'preact/hooks';
import {
  getAvailablePlugins, getPluginSchemas, getConfig,
  getSystemConfig, setSystemValue, AuthError,
} from '../api';
import { useAppContext } from '../context';
import { PluginCard } from '../components/PluginCard';

const CATEGORY_LABELS = {
  sources: 'Message Sources',
  processors: 'Processors',
  renderer: 'Renderer',
  screens: 'Screens',
  controllers: 'Controllers',
};

export function PluginsPage() {
  const { onAuthError } = useAppContext();
  const [plugins, setPlugins] = useState(null);
  const [schemas, setSchemas] = useState(null);
  const [config, setConfig] = useState(null);
  const [systemConfig, setSystemConfig] = useState(null);
  const [loadError, setLoadError] = useState(null);

  async function load() {
    try {
      const [p, s, c, sc] = await Promise.all([
        getAvailablePlugins(),
        getPluginSchemas(),
        getConfig(),
        getSystemConfig(),
      ]);
      setPlugins(p);
      setSchemas(s);
      setConfig(c);
      setSystemConfig(sc);
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setLoadError(err.message);
    }
  }

  useEffect(() => { load(); }, []);

  if (loadError) return <div class="alert alert-error">{loadError}</div>;
  if (!plugins || !config || !systemConfig) return <article aria-busy="true">Loading plugins…</article>;

  const enabledByCategory = config.plugins ?? {};

  return (
    <div>
      <SystemSettings systemConfig={systemConfig} />

      {Object.entries(CATEGORY_LABELS).map(([cat, label]) => {
        const names = plugins[cat] ?? [];
        if (names.length === 0) return null;
        const enabledList = enabledByCategory[cat] ?? [];

        return (
          <section key={cat} class="plugin-section">
            <h3>{label}</h3>
            {names.map(name => (
              <PluginCard
                key={name}
                category={cat}
                name={name}
                enabled={enabledList.includes(name)}
                schema={schemas[name] ?? null}
                config={config}
                onRefresh={load}
              />
            ))}
          </section>
        );
      })}
    </div>
  );
}

// -------------------------------------------------------
// System settings (Mapbox API key etc.)
// -------------------------------------------------------

function SystemSettings({ systemConfig }) {
  const { onAuthError } = useAppContext();
  const [mapboxKey, setMapboxKey] = useState(systemConfig?.mapbox_api_key ?? '');
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null);

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setStatus(null);
    try {
      await setSystemValue('mapbox_api_key', mapboxKey);
      setStatus('success');
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setStatus('error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section class="plugin-section">
      <h3>System</h3>
      <article class="plugin-card">
        <form onSubmit={handleSave}>
          <label htmlFor="mapbox-key">
            Mapbox API Key
            <input
              id="mapbox-key"
              type="text"
              value={mapboxKey}
              onInput={e => { setMapboxKey(e.target.value); setStatus(null); }}
              disabled={saving}
              placeholder="pk.eyJ1…"
            />
          </label>
          {status === 'success' && <p class="save-status save-status-ok">Saved</p>}
          {status === 'error' && <p class="save-status save-status-err">Failed to save</p>}
          <button type="submit" class="outline" aria-busy={saving} disabled={saving}
                  style="width: auto;">
            Save
          </button>
        </form>
      </article>
    </section>
  );
}
