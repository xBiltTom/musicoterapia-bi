import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import FR04Page from './FR04Page'
import PatientsPage from './PatientsPage'
import SessionsPage from './SessionsPage'
import { useSession } from './Auth'

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

type Scenario = { escenario: string; pacientes: number }
type Dashboard = {
  fuente: string
  consultado_utc?: string
  datos_desactualizados?: boolean
  filtros: { escenario: string; desde: string; hasta: string }
  k1: {
    tasa_positiva: number | null
    positivas: number
    neutras: number
    negativas: number
    participaciones_validas: number
  }
  k2: {
    reduccion_promedio: number | null
    pacientes_con_par: number
    respondedores: number
    tasa_respondedores: number | null
  }
  k3: {
    reduccion_promedio: number | null
    pacientes_con_par: number
    basales_sobre_corte: number
    cruces_corte: number
    tasa_cruce_corte: number | null
  }
  respuesta_mensual: {
    mes: string
    positivas: number
    participaciones_validas: number
    tasa_positiva: number | null
  }[]
}

const numberFormat = new Intl.NumberFormat('es-PE')
const decimalFormat = new Intl.NumberFormat('es-PE', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

function integer(value: number) {
  return numberFormat.format(value)
}

function decimal(value: number | null, suffix = '') {
  return value === null ? '—' : `${decimalFormat.format(value)}${suffix}`
}

function Icon({ name, size = 21 }: { name: 'pulse' | 'chart' | 'people' | 'calendar' | 'arrow' | 'music'; size?: number }) {
  const paths = {
    pulse: <path d="M2 12h4l3-7 4 14 3-7h6" />,
    chart: <><path d="M4 20V10m6 10V4m6 16v-7m5 7H2" /></>,
    people: <><circle cx="9" cy="8" r="3" /><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 5v1" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4m10-4v4M3 10h18" /></>,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    music: <><path d="M9 18V5l12-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="16" r="3" /></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

function TrendChart({ data }: { data: Dashboard['respuesta_mensual'] }) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!container.current) return
    const chart = echarts.init(container.current)
    chart.setOption({
      grid: { left: 42, right: 14, top: 24, bottom: 34 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#172941',
        borderWidth: 0,
        textStyle: { color: '#fff', fontFamily: 'Inter, sans-serif' },
        valueFormatter: (value: unknown) => `${decimalFormat.format(Number(value))} %`,
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: data.map(item => item.mes),
        axisLine: { lineStyle: { color: '#dbe4eb' } },
        axisTick: { show: false },
        axisLabel: { color: '#8091a1', fontSize: 11, hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: { color: '#8091a1', formatter: '{value}%' },
        splitLine: { lineStyle: { color: '#edf1f4' } },
      },
      series: [{
        type: 'line',
        data: data.map(item => item.tasa_positiva),
        showSymbol: false,
        smooth: 0.25,
        lineStyle: { color: '#17a69a', width: 3 },
        itemStyle: { color: '#17a69a' },
        areaStyle: { color: 'rgba(23,166,154,.12)' },
      }],
    })
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(container.current)
    return () => { observer.disconnect(); chart.dispose() }
  }, [data])

  return <div className="chart" ref={container} role="img" aria-label="Tendencia mensual de la tasa de respuesta positiva" />
}

function App() {
  const { user, request, signOut, signingOut, signOutError } = useSession()
  const { ver_tablero: canViewDashboard, ver_fr04: canViewFr04, registrar_sesiones: canViewSessions,
    registrar_altas, registrar_perfil_clinico, registrar_preferencias } = user.permisos
  const canViewPatients = registrar_altas || registrar_perfil_clinico || registrar_preferencias
  const [section, setSection] = useState<'dashboard' | 'fr04' | 'patients' | 'sessions' | null>(
    canViewDashboard ? 'dashboard' : canViewPatients ? 'patients' : canViewSessions ? 'sessions' : canViewFr04 ? 'fr04' : null,
  )
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [scenario, setScenario] = useState('HIBRIDO')
  const [from, setFrom] = useState('2022-01-01')
  const [to, setTo] = useState('2024-12-31')
  const [applied, setApplied] = useState({ scenario: 'HIBRIDO', from: '2022-01-01', to: '2024-12-31' })
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!canViewDashboard || section !== 'dashboard') return
    const controller = new AbortController()
    request('/api/escenarios', { signal: controller.signal })
      .then(response => response.ok ? response.json() as Promise<Scenario[]> : Promise.reject())
      .then(setScenarios)
      .catch(() => { if (!controller.signal.aborted) setScenarios([]) })
    return () => controller.abort()
  }, [canViewDashboard, request, section])

  useEffect(() => {
    if (!canViewDashboard || section !== 'dashboard') return
    const controller = new AbortController()
    setLoading(true)
    setError('')
    setDashboard(null)
    const params = new URLSearchParams({ escenario: applied.scenario, desde: applied.from, hasta: applied.to })
    request(`/api/tablero?${params}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}))
          throw new Error(body.detail || 'No se pudo cargar el tablero')
        }
        return response.json() as Promise<Dashboard>
      })
      .then(setDashboard)
      .catch(e => { if (e.name !== 'AbortError') setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [applied, canViewDashboard, reload, request, section])

  const valid = dashboard?.k1.participaciones_validas ?? 0
  const selectedScenario = scenarios.find(item => item.escenario === scenario)
  const scenarioOptions = scenarios.length ? scenarios.map(item => item.escenario) : ['HIBRIDO', 'SINTETICO_IA']
  const portions = [
    { label: 'Positiva', value: dashboard?.k1.positivas ?? 0, color: 'teal' },
    { label: 'Neutra', value: dashboard?.k1.neutras ?? 0, color: 'gold' },
    { label: 'Negativa', value: dashboard?.k1.negativas ?? 0, color: 'coral' },
  ]
  const sectionTitle = { dashboard: 'INDICADORES', fr04: 'CONTROL SEMANAL', patients: 'PACIENTES', sessions: 'SESIONES' }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-icon"><Icon name="music" size={22} /></div><div><strong>Musicoterapia</strong><span>INTELIGENCIA DE NEGOCIOS</span></div></div>
        <div className="nav-label">MÓDULOS</div>
        {canViewDashboard && <button className={`nav-button ${section === 'dashboard' ? 'nav-active' : ''}`} onClick={() => setSection('dashboard')}><Icon name="chart" size={19} /> Indicadores <span>01</span></button>}
        {canViewPatients && <button className={`nav-button ${section === 'patients' ? 'nav-active' : ''}`} onClick={() => setSection('patients')}><Icon name="people" size={19} /> Pacientes <span>FR01</span></button>}
        {canViewSessions && <button className={`nav-button ${section === 'sessions' ? 'nav-active' : ''}`} onClick={() => setSection('sessions')}><Icon name="music" size={19} /> Sesiones <span>FR02–03</span></button>}
        {canViewFr04 && <button className={`nav-button ${section === 'fr04' ? 'nav-active' : ''}`} onClick={() => setSection('fr04')}><Icon name="calendar" size={19} /> Control semanal <span>FR04</span></button>}
        <div className="sidebar-info"><div className="info-icon"><Icon name="pulse" size={20} /></div><strong>Seguimiento con datos</strong><p>Indicadores descriptivos de sesiones y evaluaciones clínicas.</p><small>Fuente actual · Base transaccional</small></div>
        <div className="sidebar-footer">Proyecto académico<br />Alzheimer y musicoterapia · 2022–2024</div>
      </aside>

      <main className="content">
        <header className="topbar">
          <span>{section ? sectionTitle[section] : 'CUENTA'}</span>
          <div className="account-menu">
            <span>{user.nombre_completo}</span>
            <button type="button" onClick={signOut} disabled={signingOut}>{signingOut ? 'Cerrando…' : 'Cerrar sesión'}</button>
          </div>
        </header>
        <div className="page">
          {user.solo_lectura && <p className="source-pill mode-pill">Base local · Solo lectura</p>}
          {signOutError && <div className="error-panel" role="alert">{signOutError}</div>}
          {section === 'dashboard' ? <>
          <div className="title-row"><div><div className="eyebrow">DATOS DEL ESCENARIO</div><h1>Respuesta a la musicoterapia</h1><p className="intro">Seguimiento de experiencias durante las sesiones y cambios observados en las evaluaciones.</p></div><div className="period-badge"><Icon name="calendar" size={18} /><span>{applied.from} — {applied.to}</span></div></div>

          <form className="filter-card" onSubmit={event => { event.preventDefault(); if (from <= to) setApplied({ scenario, from, to }) }}>
            <div className="filter-head"><div><span className="filter-title">Explorar los datos</span><span className="filter-subtitle">Seleccione el origen y el periodo de análisis</span></div><span className="filter-tag">FILTROS</span></div>
            <div className="filter-grid">
              <label>Escenario de datos<select value={scenario} onChange={event => setScenario(event.target.value)}>{scenarioOptions.map(value => <option key={value} value={value}>{value === 'HIBRIDO' ? 'Híbrido' : value === 'SINTETICO_IA' ? 'Sintético IA' : value}</option>)}</select></label>
              <label>Desde<input type="date" value={from} onChange={event => setFrom(event.target.value)} required /></label>
              <label>Hasta<input type="date" value={to} min={from} onChange={event => setTo(event.target.value)} required /></label>
              <button className="apply-button" type="submit" disabled={from > to || loading}>Aplicar filtros <Icon name="arrow" size={17} /></button>
            </div>
            <div className="filter-note"><span className="note-dot" /> Los escenarios se muestran por separado. {selectedScenario ? `${integer(selectedScenario.pacientes)} pacientes en el escenario seleccionado.` : ''}</div>
          </form>

          {error && <div className="error-panel" role="alert">
            <strong>No se pudieron cargar los indicadores.</strong><span>{error}</span>
            <button className="operation-secondary dashboard-retry" type="button" onClick={() => setReload(value => value + 1)}>Reintentar</button>
          </div>}
          {dashboard?.datos_desactualizados && <p className="operation-help" role="status">Mostrando los indicadores de la última lectura disponible de SQL Server.</p>}

          <div className="section-heading"><div><span className="eyebrow">INDICADORES PRINCIPALES</span><h2>Una lectura del periodo</h2></div><span className="subdued">{loading ? 'Consultando datos…' : `${applied.from} — ${applied.to}`}</span></div>
          <div className="kpi-grid">
            <article className="kpi-card"><div className="card-top"><span className="kpi-code">K1 · EXPERIENCIA</span><span className="card-icon teal"><Icon name="pulse" size={20} /></span></div><div className="kpi-value">{loading ? '…' : decimal(dashboard?.k1.tasa_positiva ?? null, '%')}</div><h3>Respuesta emocional positiva</h3><p>Participaciones positivas entre las experiencias válidas registradas.</p><div className="card-divider" /><div className="card-foot"><strong>{dashboard ? integer(valid) : '—'}</strong><span>participaciones válidas</span></div></article>
            <article className="kpi-card"><div className="card-top"><span className="kpi-code">K2 · AGITACIÓN</span><span className="card-icon blue"><Icon name="chart" size={20} /></span></div><div className="kpi-value">{loading ? '…' : decimal(dashboard?.k2.reduccion_promedio ?? null)}<small> pts</small></div><h3>Reducción promedio CMAI</h3><p>Diferencia entre evaluación inicial y último seguimiento por paciente.</p><div className="card-divider" /><div className="card-foot"><strong>{dashboard ? integer(dashboard.k2.pacientes_con_par) : '—'}</strong><span>pacientes con par válido</span></div></article>
            <article className="kpi-card"><div className="card-top"><span className="kpi-code">K3 · ÁNIMO</span><span className="card-icon purple"><Icon name="people" size={20} /></span></div><div className="kpi-value">{loading ? '…' : decimal(dashboard?.k3.reduccion_promedio ?? null)}<small> pts</small></div><h3>Reducción promedio CSDD</h3><p>Diferencia observada en síntomas depresivos con par válido.</p><div className="card-divider" /><div className="card-foot"><strong>{dashboard ? integer(dashboard.k3.pacientes_con_par) : '—'}</strong><span>pacientes con par válido</span></div></article>
          </div>

          <div className="analysis-grid">
            <section className="panel trend-panel"><div className="panel-heading"><div><span className="eyebrow">EVOLUCIÓN TEMPORAL</span><h2>Respuesta positiva por mes</h2></div><span className="legend"><i /> Tasa de respuesta</span></div>{dashboard?.respuesta_mensual.length ? <TrendChart data={dashboard.respuesta_mensual} /> : <div className="empty-chart">{loading ? 'Cargando tendencia…' : dashboard ? 'Sin datos en el periodo seleccionado' : 'Tendencia no disponible'}</div>}<div className="panel-caption">K1 · Participaciones positivas ÷ participaciones con experiencia válida.</div></section>
            <section className="panel composition-panel"><div className="panel-heading"><div><span className="eyebrow">DISTRIBUCIÓN</span><h2>Experiencias registradas</h2></div></div><div className="composition-total">{dashboard ? integer(valid) : '—'}<span> participaciones válidas</span></div><div className="stacked-bar" aria-label="Distribución de experiencias">{portions.map(item => <div key={item.label} className={item.color} style={{ width: valid ? `${100 * item.value / valid}%` : '0%' }} />)}</div><div className="composition-list">{portions.map(item => <div key={item.label}><span className={`color-dot ${item.color}`} /> <span>{item.label}</span><strong>{dashboard ? integer(item.value) : '—'}</strong><small>{valid ? decimal(100 * item.value / valid, '%') : '—'}</small></div>)}</div><div className="panel-caption">Se excluyen respuestas «no sabe» y valores vacíos.</div></section>
          </div>

          <section className="method-panel"><div className="method-icon"><Icon name="pulse" size={20} /></div><div><strong>Cómo leer estos resultados</strong><p>K2 y K3 comparan la primera evaluación inicial con el último seguimiento válido del periodo para cada paciente. Las diferencias describen cambios observados; por sí solas no prueban que la musicoterapia los haya causado. Los datos híbridos y sintéticos permanecen separados.</p></div></section>
          <footer>Musicoterapia BI · Primera fase de software · Consultas directas a SQL Server</footer>
          </> : section === 'fr04' ? <FR04Page /> : section === 'patients' ? <PatientsPage /> : section === 'sessions' ? <SessionsPage />
            : <section className="panel"><h1>Tu cuenta está activa</h1><p>Tu rol no dispone de acceso a los módulos actuales.</p></section>}
        </div>
      </main>
    </div>
  )
}

export default App
