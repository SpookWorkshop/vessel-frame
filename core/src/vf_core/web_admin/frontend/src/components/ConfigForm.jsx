import { useState } from 'preact/hooks';
import { setConfigValue, AuthError } from '../api';
import { useAppContext } from '../context';
import { ZoneEditor } from './ZoneEditor';

// Map-type field types that save themselves via their own modal.
const MODAL_FIELD_TYPES = ['zone', 'bbox'];

function fmtRadius(m) {
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;
}

export function ConfigForm({ schema, config, pluginName, mapboxKey }) {
  const { onAuthError } = useAppContext();

  const [values, setValues] = useState(() => {
    const initial = {};
    for (const field of schema.fields) {
      initial[field.key] = config?.[pluginName]?.[field.key] ?? field.default ?? '';
    }
    return initial;
  });
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null); // 'success' | 'error' | null

  function handleChange(key, value) {
    setValues(v => ({ ...v, [key]: value }));
    setStatus(null);
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setStatus(null);
    try {
      for (const field of schema.fields) {
        if (MODAL_FIELD_TYPES.includes(field.type)) continue;
        await setConfigValue(`${pluginName}.${field.key}`, values[field.key]);
      }
      setStatus('success');
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setStatus('error');
    } finally {
      setSaving(false);
    }
  }

  const hasNonModalFields = schema.fields.some(f => !MODAL_FIELD_TYPES.includes(f.field_type));

  return (
    <form onSubmit={handleSave}>
      {schema.fields.map(field => (
        <FormField
          key={field.key}
          field={field}
          value={values[field.key]}
          onChange={v => handleChange(field.key, v)}
          disabled={saving}
          mapboxKey={mapboxKey}
          pluginName={pluginName}
        />
      ))}

      {status === 'success' && <p class="save-status save-status-ok">Saved</p>}
      {status === 'error' && <p class="save-status save-status-err">Failed to save</p>}

      {hasNonModalFields && (
        <button type="submit" class="outline" aria-busy={saving} disabled={saving}
                style="width: auto; margin-top: 0.5rem;">
          Save
        </button>
      )}
    </form>
  );
}

function FormField({ field, value, onChange, disabled, mapboxKey, pluginName }) {
  if (field.type === 'zone') {
    return (
      <ZoneField
        field={field}
        value={value}
        onChange={onChange}
        disabled={disabled}
        mapboxKey={mapboxKey}
        pluginName={pluginName}
      />
    );
  }

  const id = `field-${field.key}`;
  const isCheckbox = field.type === 'boolean';

  return (
    <label htmlFor={id} class={isCheckbox ? 'checkbox-label' : ''}>
      {isCheckbox ? (
        <>
          <input
            id={id}
            type="checkbox"
            role="switch"
            checked={!!value}
            onChange={e => onChange(e.target.checked)}
            disabled={disabled}
          />
          {field.label}
        </>
      ) : (
        <>
          {field.label}
          <FieldInput id={id} field={field} value={value} onChange={onChange} disabled={disabled} />
        </>
      )}
      {field.description && <small>{field.description}</small>}
    </label>
  );
}

function ZoneField({ field, value, onChange, disabled, mapboxKey, pluginName }) {
  const [modalOpen, setModalOpen] = useState(false);
  const hasKey = !!mapboxKey;

  const summary = value
    ? `${Number(value.lat).toFixed(5)}, ${Number(value.lon).toFixed(5)}, ${fmtRadius(value.rad)}`
    : 'Not configured';

  return (
    <div class="zone-field">
      <div class="zone-field-label">{field.label}</div>
      <div class="zone-field-row">
        <span class={value ? 'zone-summary' : 'zone-summary zone-unset'}>{summary}</span>
        <button
          type="button"
          class="outline"
          style="width: auto; margin: 0;"
          onClick={() => setModalOpen(true)}
          disabled={disabled || !hasKey}
        >
          {value ? 'Edit zone…' : 'Set zone…'}
        </button>
      </div>
      {!hasKey && <small class="save-status save-status-err">Set a Mapbox API key first</small>}
      {hasKey && field.description && <small>{field.description}</small>}
      {modalOpen && (
        <ZoneEditor
          value={value}
          mapboxKey={mapboxKey}
          pluginName={pluginName}
          fieldKey={field.key}
          onSave={newValue => { onChange(newValue); }}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  );
}

function FieldInput({ id, field, value, onChange, disabled }) {
  switch (field.type) {
    case 'select':
      return (
        <select id={id} value={value} onChange={e => onChange(e.target.value)} disabled={disabled}>
          {(field.options ?? []).map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      );
    case 'integer':
      return (
        <input id={id} type="number" step="1" value={value}
               onInput={e => onChange(e.target.value)} disabled={disabled} />
      );
    case 'float':
      return (
        <input id={id} type="number" step="any" value={value}
               onInput={e => onChange(e.target.value)} disabled={disabled} />
      );
    case 'colour':
      return (
        <input id={id} type="color" value={value}
               onInput={e => onChange(e.target.value)} disabled={disabled} />
      );
    default: // string, file, json, etc.
      return (
        <input id={id} type="text" value={value}
               onInput={e => onChange(e.target.value)} disabled={disabled} />
      );
  }
}
