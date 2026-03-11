import { useState } from 'preact/hooks';
import { enablePlugin, disablePlugin, AuthError } from '../api';
import { useAppContext } from '../context';
import { ConfigForm } from './ConfigForm';

export function PluginCard({ category, name, enabled, schema, config, mapboxKey, onRefresh }) {
  const { onAuthError } = useAppContext();
  const [open, setOpen] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [toggleError, setToggleError] = useState(null);

  const displayName = name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());

  async function handleToggle() {
    setToggling(true);
    setToggleError(null);
    try {
      if (enabled) {
        await disablePlugin(category, name);
        setOpen(false);
      } else {
        await enablePlugin(category, name);
      }
      onRefresh();
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setToggleError(err.message);
    } finally {
      setToggling(false);
    }
  }

  return (
    <article class="plugin-card">
      <div class="plugin-card-header">
        <div class="plugin-card-title">
          <span>{displayName}</span>
          <span class={`badge ${enabled ? 'badge-enabled' : 'badge-disabled'}`}>
            {enabled ? 'Enabled' : 'Disabled'}
          </span>
        </div>
        <button class="outline" aria-busy={toggling} disabled={toggling}
                onClick={handleToggle} style="width: auto; margin: 0;">
          {enabled ? 'Disable' : 'Enable'}
        </button>
      </div>

      {toggleError && <p class="save-status save-status-err">{toggleError}</p>}

      {enabled && schema && (
        <div class="plugin-card-config">
          <button class="config-toggle" onClick={() => setOpen(o => !o)}>
            {open ? '▲ Hide config' : '▼ Configure'}
          </button>
          {open && (
            <div class="config-form-wrap">
              <ConfigForm schema={schema} config={config} pluginName={name} mapboxKey={mapboxKey} />
            </div>
          )}
        </div>
      )}
    </article>
  );
}
