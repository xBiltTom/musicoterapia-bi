import { useState } from 'react'
import DashboardPage from './DashboardPage'
import FR04Page from './FR04Page'
import PatientsPage from './PatientsPage'
import SessionsPage from './SessionsPage'
import { useSession } from './Auth'

const sections = {
  dashboard: { title: 'Indicadores', icon: <path d="M4 20V10m6 10V4m6 16v-7m5 7H2" /> },
  patients: { title: 'Pacientes', icon: <><circle cx="9" cy="8" r="3" /><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 5v1" /></> },
  sessions: { title: 'Sesiones', icon: <><path d="M9 18V5l12-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="16" r="3" /></> },
  fr04: { title: 'Control semanal', icon: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4m10-4v4M3 10h18" /></> },
}
type Section = keyof typeof sections

function Icon({ section, size = 19 }: { section: Section; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{sections[section].icon}</svg>
}

export default function App() {
  const { user, signOut, signingOut, signOutError } = useSession()
  const { ver_tablero, ver_fr04, registrar_sesiones, registrar_altas, registrar_perfil_clinico, registrar_preferencias } = user.permisos
  const allowed = {
    dashboard: ver_tablero, patients: registrar_altas || registrar_perfil_clinico || registrar_preferencias,
    sessions: registrar_sesiones, fr04: ver_fr04,
  }
  const navigation = (Object.keys(sections) as Section[]).filter(key => allowed[key])
  const [selected, setSelected] = useState<Section | null>(null)
  const section = selected && allowed[selected] ? selected : navigation[0]

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-icon"><Icon section="sessions" size={22} /></div>
        <div><strong>Musicoterapia</strong><span>INTELIGENCIA DE NEGOCIOS</span></div></div>
      <nav className="module-navigation" aria-label="Módulos">
        {navigation.map(key => <button key={key} type="button" className={'nav-button' + (section === key ? ' nav-active' : '')}
          aria-current={section === key ? 'page' : undefined} onClick={() => setSelected(key)}>
          <Icon section={key} />{sections[key].title}
        </button>)}
      </nav>
      <div className="sidebar-footer">Alzheimer y musicoterapia · 2022–2024</div>
    </aside>

    <main className="content">
      <header className="topbar">
        <span>{section ? sections[section].title.toUpperCase() : 'CUENTA'}</span>
        <div className="account-menu">
          <span>{user.nombre_completo}</span>
          <button type="button" onClick={signOut} disabled={signingOut}>{signingOut ? 'Cerrando…' : 'Cerrar sesión'}</button>
        </div>
      </header>
      <div className="page">
        {user.solo_lectura && <p className="source-pill mode-pill">Base local · Solo lectura</p>}
        {signOutError && <div className="error-panel" role="alert">{signOutError}</div>}
        {section === 'dashboard' ? <DashboardPage /> : section === 'fr04' ? <FR04Page />
          : section === 'patients' ? <PatientsPage /> : section === 'sessions' ? <SessionsPage />
            : <section className="panel"><h1>Tu cuenta está activa</h1><p>Tu rol no dispone de acceso a los módulos actuales.</p></section>}
      </div>
    </main>
  </div>
}
