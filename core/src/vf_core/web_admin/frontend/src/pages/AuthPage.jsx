import { useState, useEffect } from 'preact/hooks';
import { getAuthStatus, login, register, setToken } from '../api';

export function AuthPage({ onAuth }) {
  const [configured, setConfigured] = useState(null); // null = loading
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAuthStatus()
      .then(setConfigured)
      .catch(() => setConfigured(true)); // assume configured on error to show login
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const token = configured
        ? await login(username, password)
        : await register(username, password);
      setToken(token);
      onAuth();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (configured === null) {
    return (
      <main class="page-content" style="max-width: 400px">
        <article aria-busy="true">Checking status…</article>
      </main>
    );
  }

  return (
    <main class="page-content auth-page">
      <article>
        <header>
          <h2>{configured ? 'Sign in' : 'Create admin account'}</h2>
          {!configured && (
            <p>
              <small>Set up a username and password to secure the admin panel.</small>
            </p>
          )}
        </header>

        {error && <div class="alert alert-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <label>
            Username
            <input
              type="text"
              value={username}
              onInput={e => setUsername(e.target.value)}
              autocomplete={configured ? 'username' : 'new-password'}
              required
              disabled={busy}
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onInput={e => setPassword(e.target.value)}
              autocomplete={configured ? 'current-password' : 'new-password'}
              required
              disabled={busy}
            />
          </label>

          <button type="submit" aria-busy={busy} disabled={busy}>
            {configured ? 'Sign in' : 'Create account'}
          </button>
        </form>
      </article>
    </main>
  );
}
