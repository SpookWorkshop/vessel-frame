import { useState, useEffect } from 'preact/hooks';
import {
  getNetworkStatus, getNetworkConfig, scanNetworks,
  setAPMode, setClientMode, setOfflineMode, AuthError,
} from '../api';
import { useAppContext } from '../context';

export function NetworkPage() {
  const { onAuthError } = useAppContext();
  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState(null);
  const [loadError, setLoadError] = useState(null);

  async function load() {
    try {
      const [s, c] = await Promise.all([getNetworkStatus(), getNetworkConfig()]);
      setStatus(s);
      setConfig(c);
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setLoadError(err.message);
    }
  }

  useEffect(() => { load(); }, []);

  if (loadError) return <div class="alert alert-error">{loadError}</div>;
  if (!status || !config) return <article aria-busy="true">Loading network…</article>;

  return (
    <div>
      <NetworkStatus status={status} onRefresh={load} />
      <APModeForm config={config} onSaved={load} />
      <ClientModeForm config={config} onSaved={load} />
      <OfflineModeForm onSaved={load} />
    </div>
  );
}

// -------------------------------------------------------
// Status card
// -------------------------------------------------------

function NetworkStatus({ status, onRefresh }) {
  const modeLabel = {
    ap: 'Access Point',
    client: 'Client',
    offline: 'Offline',
  };

  const modeBadgeClass = {
    ap: 'badge-mode-ap',
    client: 'badge-mode-client',
    offline: 'badge-disabled',
  };

  const actual = status.actual_mode ?? 'offline';

  return (
    <section class="plugin-section">
      <h3>Current Status</h3>
      <article class="plugin-card">
        <div class="network-status-row">
          <div class="network-status-info">
            <span class={`badge ${modeBadgeClass[actual] ?? 'badge-disabled'}`}>
              {modeLabel[actual] ?? actual}
            </span>
            {actual === 'ap' && status.ap_ssid && (
              <span class="network-detail">
                <strong>SSID:</strong> {status.ap_ssid}
                {status.ap_ip && <> &nbsp;·&nbsp; <strong>IP:</strong> {status.ap_ip}</>}
              </span>
            )}
            {actual === 'client' && status.connected_ssid && (
              <span class="network-detail">
                <strong>SSID:</strong> {status.connected_ssid}
                {status.ip_address && <> &nbsp;·&nbsp; <strong>IP:</strong> {status.ip_address}</>}
              </span>
            )}
          </div>
          <button class="outline" onClick={onRefresh} style="width: auto; margin: 0;">
            Refresh
          </button>
        </div>
      </article>
    </section>
  );
}

// -------------------------------------------------------
// AP mode form
// -------------------------------------------------------

function APModeForm({ config, onSaved }) {
  const { onAuthError } = useAppContext();
  const [ssid, setSsid] = useState(config.ap_ssid ?? '');
  const [password, setPassword] = useState(config.ap_password ?? '');
  const [channel, setChannel] = useState(config.ap_channel ?? 6);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setStatus(null);
    try {
      await setAPMode(ssid || null, password || null, Number(channel));
      setStatus('success');
      onSaved();
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setStatus(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section class="plugin-section">
      <h3>Access Point Mode</h3>
      <article class="plugin-card">
        <form onSubmit={handleSubmit}>
          <div class="form-row">
            <label htmlFor="ap-ssid">
              SSID
              <input id="ap-ssid" type="text" maxLength={32} value={ssid}
                     onInput={e => setSsid(e.target.value)} disabled={saving} />
            </label>
            <label htmlFor="ap-password">
              Password
              <input id="ap-password" type="password" minLength={8} maxLength={63}
                     value={password} onInput={e => setPassword(e.target.value)}
                     disabled={saving} />
            </label>
            <label htmlFor="ap-channel">
              Channel
              <select id="ap-channel" value={channel}
                      onChange={e => setChannel(e.target.value)} disabled={saving}>
                <option value={1}>1</option>
                <option value={6}>6</option>
                <option value={11}>11</option>
              </select>
            </label>
          </div>

          {status === 'success' && <p class="save-status save-status-ok">Saved! Changes apply on next reboot</p>}
          {status && status !== 'success' && <p class="save-status save-status-err">{status}</p>}

          <button type="submit" aria-busy={saving} disabled={saving} style="width: auto;">
            Switch to Access Point Mode
          </button>
        </form>
      </article>
    </section>
  );
}

// -------------------------------------------------------
// Client mode form
// -------------------------------------------------------

function ClientModeForm({ config, onSaved }) {
  const { onAuthError } = useAppContext();
  const [ssid, setSsid] = useState(config.client_ssid ?? '');
  const [password, setPassword] = useState('');
  const [openNetwork, setOpenNetwork] = useState(false);
  const [autoFallback, setAutoFallback] = useState(config.auto_fallback ?? false);
  const [fallbackTimeout, setFallbackTimeout] = useState(config.fallback_timeout ?? 60);
  const [networks, setNetworks] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null);

  async function handleScan() {
    setScanning(true);
    setNetworks(null);
    try {
      const results = await scanNetworks();
      setNetworks(results);
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setNetworks([]);
    } finally {
      setScanning(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setStatus(null);
    try {
      const passwordToSend = openNetwork ? '' : (password || null);
      await setClientMode(ssid, passwordToSend, autoFallback, Number(fallbackTimeout));
      setStatus('success');
      onSaved();
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setStatus(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section class="plugin-section">
      <h3>Client Mode</h3>
      <article class="plugin-card">
        <form onSubmit={handleSubmit}>
          <label htmlFor="client-ssid">
            SSID
            <div class="input-with-action">
              <input id="client-ssid" type="text" maxLength={32} value={ssid}
                     onInput={e => setSsid(e.target.value)} disabled={saving} required />
              <button type="button" class="outline" aria-busy={scanning} disabled={scanning}
                      onClick={handleScan} style="width: auto; white-space: nowrap;">
                Scan
              </button>
            </div>
          </label>

          {networks !== null && (
            <div class="network-scan-results">
              {networks.length === 0
                ? <p class="save-status">No networks found</p>
                : networks.map(n => (
                    <button key={n.ssid} type="button" class="network-scan-item outline"
                            onClick={() => { setSsid(n.ssid); setNetworks(null); }}>
                      <span>{n.ssid}</span>
                      <span class="network-scan-meta">
                        {n.signal && <span>{n.signal}</span>}
                        {n.encrypted && <span>🔒</span>}
                      </span>
                    </button>
                  ))
              }
            </div>
          )}

          <label htmlFor="open-network" class="checkbox-label">
            <input id="open-network" type="checkbox" role="switch"
                   checked={openNetwork} onChange={e => setOpenNetwork(e.target.checked)}
                   disabled={saving} />
            Open network (no password)
          </label>

          {!openNetwork && (
            <label htmlFor="client-password">
              Password
              <input id="client-password" type="password" maxLength={63} value={password}
                     onInput={e => setPassword(e.target.value)} disabled={saving}
                     placeholder="Leave blank to keep existing" />
            </label>
          )}

          <label htmlFor="auto-fallback" class="checkbox-label">
            <input id="auto-fallback" type="checkbox" role="switch"
                   checked={autoFallback} onChange={e => setAutoFallback(e.target.checked)}
                   disabled={saving} />
            Fall back to Access Point if connection fails
          </label>

          {autoFallback && (
            <label htmlFor="fallback-timeout">
              Fallback timeout: {fallbackTimeout}s
              <input id="fallback-timeout" type="range" min={30} max={300} step={10}
                     value={fallbackTimeout}
                     onInput={e => setFallbackTimeout(e.target.value)}
                     disabled={saving} />
            </label>
          )}

          {status === 'success' && <p class="save-status save-status-ok">Saved! Changes apply on next reboot</p>}
          {status && status !== 'success' && <p class="save-status save-status-err">{status}</p>}

          <button type="submit" aria-busy={saving} disabled={saving} style="width: auto;">
            Switch to Client Mode
          </button>
        </form>
      </article>
    </section>
  );
}

// -------------------------------------------------------
// Offline mode
// -------------------------------------------------------

function OfflineModeForm({ onSaved }) {
  const { onAuthError } = useAppContext();
  const [confirmed, setConfirmed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setStatus(null);
    try {
      await setOfflineMode();
      setStatus('success');
      onSaved();
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setStatus(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section class="plugin-section">
      <h3>Offline Mode</h3>
      <article class="plugin-card">
        <p>
          Offline mode disables all wireless networking on the device. Once active,
          the admin panel will be unreachable over WiFi.
        </p>
        <p><strong>Before switching to offline mode, ensure USB gadget mode is enabled.</strong></p>
        <p>
          Without it, you will have no way to reach the admin panel to re-enable networking
          without physically re-imaging the SD card.
        </p>
        <form onSubmit={handleSubmit}>
          <label htmlFor="offline-confirm" class="checkbox-label">
            <input id="offline-confirm" type="checkbox" role="switch"
                   checked={confirmed} onChange={e => setConfirmed(e.target.checked)}
                   disabled={saving} />
            I understand I need USB gadget mode to recover network access
          </label>

          {status === 'success' && <p class="save-status save-status-ok">Saved! Changes apply on next reboot</p>}
          {status && status !== 'success' && <p class="save-status save-status-err">{status}</p>}

          <button type="submit" aria-busy={saving} disabled={saving || !confirmed} style="width: auto;">
            Switch to Offline Mode
          </button>
        </form>
      </article>
    </section>
  );
}
