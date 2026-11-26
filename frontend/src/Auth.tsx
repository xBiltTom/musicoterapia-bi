import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'

type User = {
  codigo_personal: string
  nombre_completo: string
  rol: string
  alcance_datos: 'GLOBAL' | 'PROPIOS'
  solo_lectura: boolean
  permisos: {
    ver_tablero: boolean
    ver_fr04: boolean
    editar_fr04: boolean
    registrar_altas: boolean
    registrar_perfil_clinico: boolean
    registrar_preferencias: boolean
    registrar_sesiones: boolean
    registrar_musica: boolean
  }
}

type Session = {
  user: User
  request: typeof fetch
  signOut: () => Promise<void>
  signingOut: boolean
  signOutError: string
}

const SessionContext = createContext<Session | null>(null)
const jsonHeaders = { 'Content-Type': 'application/json' }

export function useSession() {
  const session = useContext(SessionContext)
  if (!session) throw new Error('No hay una sesión disponible')
  return session
}

async function apiError(response: Response, fallback: string) {
  const body = await response.json().catch(() => null)
  return new Error(typeof body?.detail === 'string' ? body.detail : fallback)
}

async function getSession(signal?: AbortSignal): Promise<User | null> {
  const response = await fetch('/api/auth/sesion', { signal })
  if (response.status === 401) return null
  if (!response.ok) throw await apiError(response, 'No se pudo verificar la sesión')
  return response.json()
}

function LoginForm({ onLogin, notice }: { onLogin: (user: User) => void; notice: string }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting || !username.trim() || !password) return
    setSubmitting(true)
    setError('')
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST', headers: jsonHeaders,
        body: JSON.stringify({ usuario: username.trim(), contrasena: password }),
      })
      if (!response.ok) throw await apiError(response, 'No se pudo iniciar sesión')
      const user = await getSession()
      if (!user) throw new Error('No se pudo abrir la sesión. Verifica que el navegador permita cookies.')
      onLogin(user)
    } catch (cause) {
      setError(cause instanceof TypeError ? 'No se pudo conectar con el servidor. Inténtalo de nuevo.' : (cause as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return <>
    <h1 id="auth-title">Iniciar sesión</h1>
    <p className="login-description">Ingresa con tu cuenta del centro.</p>
    {notice && !error && <p className="login-notice" role="status">{notice}</p>}
    <form className="login-form" onSubmit={submit}>
      <label htmlFor="login-user">Usuario</label>
      <input id="login-user" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false}
        maxLength={60} value={username} onChange={event => setUsername(event.target.value)} required />
      <label htmlFor="login-password">Contraseña</label>
      <div className="login-password">
        <input id="login-password" name="password" type={showPassword ? 'text' : 'password'}
          autoComplete="current-password" maxLength={256} value={password} onChange={event => setPassword(event.target.value)} required />
        <button type="button" onClick={() => setShowPassword(value => !value)} aria-controls="login-password">
          {showPassword ? 'Ocultar' : 'Mostrar'}
        </button>
      </div>
      {error && <p className="login-error" role="alert">{error}</p>}
      <button className="login-submit" type="submit" disabled={submitting}>
        {submitting ? 'Ingresando…' : 'Ingresar'}
      </button>
    </form>
  </>
}

const bars = [16, 22, 36, 29, 43, 67, 52, 84, 100, 73, 55, 67, 47, 32, 20, 12]

function LoginLayout({ children }: { children: ReactNode }) {
  return <main className="login-layout">
    <div className="login-shell">
      <div className="login-brand">
        <strong>Musicoterapia BI</strong>
        <div className="login-wave" aria-hidden="true">
          {bars.map((height, index) => <span key={index} style={{ height: `${height}%` }} />)}
        </div>
        <p>Seguimiento del programa de musicoterapia</p>
      </div>
      <section className="login-panel" aria-labelledby="auth-title">
        {children}
      </section>
    </div>
  </main>
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [checking, setChecking] = useState(true)
  const [retry, setRetry] = useState(0)
  const [checkError, setCheckError] = useState('')
  const [notice, setNotice] = useState('')
  const [signingOut, setSigningOut] = useState(false)
  const [signOutError, setSignOutError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    getSession(controller.signal)
      .then(value => { if (!controller.signal.aborted) setUser(value) })
      .catch(error => {
        if (!controller.signal.aborted) {
          const fallback = 'No se pudo verificar la sesión. Inténtalo de nuevo.'
          setCheckError(error instanceof Error && !(error instanceof TypeError) ? error.message : fallback)
        }
      })
      .finally(() => { if (!controller.signal.aborted) setChecking(false) })
    return () => controller.abort()
  }, [retry])

  const request: typeof fetch = useCallback(async (input, init) => {
    const response = await fetch(input, init)
    if (response.status === 401 && !init?.signal?.aborted) {
      setNotice('Vuelve a iniciar sesión para continuar.')
      setUser(active => active === user ? null : active)
    }
    return response
  }, [user])

  async function signOut() {
    setSigningOut(true)
    setSignOutError('')
    try {
      const response = await fetch('/api/auth/logout', { method: 'POST', headers: jsonHeaders })
      if (!response.ok) throw await apiError(response, 'No se pudo cerrar la sesión')
      setNotice('')
      setUser(null)
    } catch {
      setSignOutError('No se pudo cerrar la sesión. Inténtalo de nuevo.')
    } finally {
      setSigningOut(false)
    }
  }

  if (user) {
    return <SessionContext.Provider value={{ user, request, signOut, signingOut, signOutError }}>
      {children}
    </SessionContext.Provider>
  }

  return <LoginLayout>
    {checking ? <h1 id="auth-title" role="status">Verificando sesión…</h1> : checkError ? <>
      <h1 id="auth-title">Acceso al sistema</h1>
      <p className="login-error" role="alert">{checkError}</p>
      <button className="login-submit" onClick={() => { setChecking(true); setCheckError(''); setRetry(value => value + 1) }}>
        Reintentar
      </button>
    </> : <LoginForm notice={notice} onLogin={value => { setNotice(''); setSignOutError(''); setUser(value) }} />}
  </LoginLayout>
}
