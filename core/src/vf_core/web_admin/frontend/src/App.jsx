import { useState } from 'preact/hooks';
import { Router, Route, Link, useLocation } from 'wouter';
import { getToken, clearToken } from './api';
import { AppContext } from './context';
import { AuthPage } from './pages/AuthPage';
import { PluginsPage } from './pages/PluginsPage';
import { NetworkPage } from './pages/NetworkPage';

export function App() {
  const [authed, setAuthed] = useState(!!getToken());

  function handleAuth() {
    setAuthed(true);
  }

  function handleAuthError() {
    clearToken();
    setAuthed(false);
  }

  if (!authed) {
    return <AuthPage onAuth={handleAuth} />;
  }

  return (
    <AppContext.Provider value={{ onAuthError: handleAuthError }}>
      <Router base="/">
        <Header onLogout={handleAuthError} />
        <main class="page-content">
          <Route path="/" component={PluginsPage} />
          <Route path="/network" component={NetworkPage} />
        </main>
      </Router>
    </AppContext.Provider>
  );
}

// -------------------------------------------------------
// Header / nav
// -------------------------------------------------------

function NavLink({ href, children }) {
  const [location] = useLocation();
  const active = location === href || (href !== '/' && location.startsWith(href));
  return (
    <Link href={href} class={active ? 'active' : ''}>{children}</Link>
  );
}

function Header({ onLogout }) {
  return (
    <header class="site-header">
      <div class="header-inner">
        <span class="brand">Vessel<span>Frame</span></span>
        <nav class="site-nav">
          <NavLink href="/">Plugins</NavLink>
          <NavLink href="/network">Network</NavLink>
          <button class="logout-btn" onClick={onLogout}>Sign out</button>
        </nav>
      </div>
    </header>
  );
}
