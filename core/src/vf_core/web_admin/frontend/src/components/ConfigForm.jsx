import { useState } from 'preact/hooks';
import { setConfigValue, AuthError } from '../api';
import { useAppContext } from '../context';

export function ConfigForm({ schema, config, pluginName }) {
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

  return (
    <form onSubmit={handleSave}>
      {schema.fields.map(field => (
        <FormField
          key={field.key}
          field={field}
          value={values[field.key]}
          onChange={v => handleChange(field.key, v)}
          disabled={saving}
        />
      ))}

      {status === 'success' && <p class="save-status save-status-ok">Saved</p>}
      {status === 'error' && <p class="save-status save-status-err">Failed to save</p>}

      <button type="submit" class="outline" aria-busy={saving} disabled={saving}
              style="width: auto; margin-top: 0.5rem;">
        Save
      </button>
    </form>
  );
}

function FormField({ field, value, onChange, disabled }) {
  const id = `field-${field.key}`;
  const isCheckbox = field.field_type === 'boolean';

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

function FieldInput({ id, field, value, onChange, disabled }) {
  switch (field.field_type) {
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
