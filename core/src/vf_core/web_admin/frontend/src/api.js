/**
 * Vessel Frame Admin API client
 *
 * All communication with the FastAPI backend goes through this module.
 * Authenticated calls automatically attach the stored JWT and redirect
 * to the auth page on 401.
 */

const TOKEN_KEY = 'atoken'

// -------------------------------------------------------
// Token helpers
// -------------------------------------------------------

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

// -------------------------------------------------------
// Base fetch wrappers
// -------------------------------------------------------

/**
 * Unauthenticated fetch, for auth endpoints only.
 */
async function publicFetch(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  return res
}

/**
 * Authenticated fetch, attaches Bearer token.
 * Throws an AuthError on 401 so the app shell can redirect to login.
 */
export async function apiFetch(path, options = {}) {
  const token = getToken()
  const res = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...options,
  })

  if (res.status === 401) {
    clearToken()
    throw new AuthError('Session expired')
  }

  return res
}

export class AuthError extends Error {}

// -------------------------------------------------------
// Auth endpoints
// -------------------------------------------------------

/** Returns true if admin credentials have been configured. */
export async function getAuthStatus() {
  const res = await publicFetch('/api/auth/status')
  if (!res.ok) throw new Error('Failed to fetch auth status')
  const data = await res.json()
  return data.configured
}

/** Login, returns the JWT string on success, throws on failure. */
export async function login(username, password) {
  const res = await publicFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? 'Login failed')
  return data.token
}

/** Register initial admin credentials, returns the JWT string on success. */
export async function register(username, password) {
  const res = await publicFetch('/api/auth/setup', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? data.message ?? 'Registration failed')
  // Setup doesn't return a token so follow up with login
  return login(username, password)
}

// -------------------------------------------------------
// Plugin endpoints
// -------------------------------------------------------

export async function getAvailablePlugins() {
  const res = await apiFetch('/api/plugins/available')
  if (!res.ok) throw new Error('Failed to fetch plugins')
  return res.json()
}

export async function getPluginSchemas() {
  const res = await apiFetch('/api/plugins/schemas')
  if (!res.ok) throw new Error('Failed to fetch schemas')
  return res.json()
}

export async function enablePlugin(category, name) {
  const res = await apiFetch('/api/plugins/enable', {
    method: 'PUT',
    body: JSON.stringify({ category, name }),
  })
  if (!res.ok) throw new Error('Failed to enable plugin')
  return res.json()
}

export async function disablePlugin(category, name) {
  const res = await apiFetch('/api/plugins/disable', {
    method: 'PUT',
    body: JSON.stringify({ category, name }),
  })
  if (!res.ok) throw new Error('Failed to disable plugin')
  return res.json()
}

// -------------------------------------------------------
// Config endpoints
// -------------------------------------------------------

export async function getConfig() {
  const res = await apiFetch('/api/config/')
  if (!res.ok) throw new Error('Failed to fetch config')
  return res.json()
}

export async function setConfigValue(path, value) {
  const res = await apiFetch('/api/config/', {
    method: 'PUT',
    body: JSON.stringify({ path, value }),
  })
  if (!res.ok) throw new Error('Failed to save config')
  return res.json()
}

// -------------------------------------------------------
// System endpoints
// -------------------------------------------------------

export async function getSystemConfig() {
  const res = await apiFetch('/api/system/')
  if (!res.ok) throw new Error('Failed to fetch system config')
  return res.json()
}

export async function setSystemValue(key, value) {
  const res = await apiFetch('/api/system/', {
    method: 'PUT',
    body: JSON.stringify({ key, value }),
  })
  if (!res.ok) throw new Error('Failed to save system config')
  return res.json()
}

// -------------------------------------------------------
// Network endpoints
// -------------------------------------------------------

export async function getNetworkStatus() {
  const res = await apiFetch('/api/network/status')
  if (!res.ok) throw new Error('Failed to fetch network status')
  return res.json()
}

export async function getNetworkConfig() {
  const res = await apiFetch('/api/network/config')
  if (!res.ok) throw new Error('Failed to fetch network config')
  return res.json()
}

export async function scanNetworks() {
  const res = await apiFetch('/api/network/scan')
  if (!res.ok) throw new Error('Failed to scan networks')
  return res.json()
}

export async function setAPMode(ssid, password, channel) {
  const res = await apiFetch('/api/network/mode/ap', {
    method: 'POST',
    body: JSON.stringify({ ssid, password, channel }),
  })
  if (!res.ok) throw new Error('Failed to set AP mode')
  return res.json()
}

export async function setClientMode(ssid, password, autoFallback, fallbackTimeout) {
  const res = await apiFetch('/api/network/mode/client', {
    method: 'POST',
    body: JSON.stringify({
      ssid,
      password,
      auto_fallback: autoFallback,
      fallback_timeout: fallbackTimeout,
    }),
  })
  if (!res.ok) throw new Error('Failed to set client mode')
  return res.json()
}
