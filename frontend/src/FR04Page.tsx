import { useState } from 'react'
import { useSession } from './Auth'
import { displayDateTime, populationLabels, scenarioLabels, useOperationQuery } from './operations'
import type { Population, Scenario } from './operations'

type Summary = {
  en_intervencion: number
  cumple: number
  no_cumple: number
  k4_tasa_adherencia: number | null
}
type Preview = {
  paciente: { codigo_paciente: string }
  semana_inicio: string
  semana_fin: string
  dosis: { sesiones_realizadas: number; minutos_realizados: number }
  clasificacion: 'CUMPLE' | 'NO_CUMPLE'
  sesiones: {
    codigo_sesion: string
    fecha_hora_inicio_sesion: string
    fecha_hora_ingreso_paciente: string | null
    fecha_hora_salida_paciente: string | null
    minutos_realizados: number | null
  }[]
}

const integer = new Intl.NumberFormat('es-PE')
const decimal = new Intl.NumberFormat('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function FR04Page() {
  const { user } = useSession()
  const [filters, setFilters] = useState<{ escenario: Scenario; poblacion: Population; semana_inicio: string }>({
    escenario: 'HIBRIDO', poblacion: 'incluidos', semana_inicio: '2023-07-24',
  })
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState('')
  const validWeek = Boolean(filters.semana_inicio) && new Date(filters.semana_inicio + 'T12:00:00').getDay() === 1
  const showPatientDetails = validWeek && user.permisos.ver_ficha_fr04 === true
  const summary = useOperationQuery<Summary>(validWeek ? '/api/fr04/resumen?' + new URLSearchParams(filters) : null)
  const patients = useOperationQuery<{ codigo_paciente: string }[]>(showPatientDetails
    ? '/api/fr04/pacientes?' + new URLSearchParams({ ...filters, buscar: search.trim() }) : null)
  const patient = useOperationQuery<Preview>(showPatientDetails && selected
    ? '/api/fr04/ficha?' + new URLSearchParams({ ...filters, codigo_paciente: selected }) : null)
  const stats = summary.data
  const ficha = patient.data

  function changeFilters(next: typeof filters) {
    setFilters(next)
    setSelected('')
    setSearch('')
  }

  return <div className="operation-page">
    <div className="title-row"><div><h1>Control semanal de adherencia</h1>
      <p className="intro">FR04 se calcula a partir de las sesiones registradas en FR03.</p>
    </div></div>
    <section className="panel operation-stack">
      <div className="operation-form-grid fr04-filters">
        <label>Escenario<select value={filters.escenario}
          onChange={event => changeFilters({ ...filters, escenario: event.target.value as Scenario })}>
          <option value="HIBRIDO">{scenarioLabels.HIBRIDO}</option><option value="SINTETICO_IA">{scenarioLabels.SINTETICO_IA}</option>
        </select></label>
        <label>Población<select value={filters.poblacion}
          onChange={event => changeFilters({ ...filters, poblacion: event.target.value as Population })}>
          <option value="incluidos">{populationLabels.incluidos}</option><option value="todos">{populationLabels.todos}</option>
        </select></label>
        <label>Lunes de la semana ISO<input type="date" value={filters.semana_inicio}
          onChange={event => changeFilters({ ...filters, semana_inicio: event.target.value })} /></label>
      </div>
      {!validWeek && <p className="operation-help" role="status">Selecciona un lunes para consultar la semana.</p>}
      {summary.loading && <p className="operation-help" role="status">Consultando la adherencia semanal…</p>}
      {summary.error && <p className="error-panel" role="alert">{summary.error}</p>}
      {stats && <div className="fr04-summary">
        <div className="fr04-stat highlighted"><small>K4 · adherencia semanal</small>
          <strong>{stats.k4_tasa_adherencia === null ? '—' : decimal.format(stats.k4_tasa_adherencia) + ' %'}</strong></div>
        <div className="fr04-stat"><small>En intervención</small><strong>{integer.format(stats.en_intervencion)}</strong></div>
        <div className="fr04-stat"><small>Cumplen</small><strong>{integer.format(stats.cumple)}</strong></div>
        <div className="fr04-stat"><small>No cumplen</small><strong>{integer.format(stats.no_cumple)}</strong></div>
      </div>}
      <p className="operation-help">La intervención abarca desde la primera hasta la última semana con sesiones realizadas. La dosis exige al menos tres sesiones y 30 minutos acumulados.</p>
    </section>
    {showPatientDetails && <section className="panel operation-stack">
      <h2>Ficha por paciente</h2>
      <label className="fr04-search">Código del paciente<input value={search} maxLength={120}
        onChange={event => { setSearch(event.target.value); setSelected('') }} placeholder="Buscar por inicio del código" /></label>
      {patients.error && <p className="error-panel" role="alert">{patients.error}</p>}
      {patients.loading && <p className="operation-help" role="status">Buscando pacientes…</p>}
      {patients.data?.length === 0 && <p className="operation-help">Sin pacientes que coincidan en esa semana.</p>}
      <div className="fr04-suggestions">{patients.data?.map(item => <button type="button" key={item.codigo_paciente}
        aria-pressed={selected === item.codigo_paciente} className={selected === item.codigo_paciente ? 'selected' : ''}
        onClick={() => setSelected(item.codigo_paciente)}>{item.codigo_paciente}</button>)}</div>
      {patient.error && <p className="error-panel" role="alert">{patient.error}</p>}
      {patient.loading && <p className="operation-help" role="status">Consultando la ficha semanal…</p>}
      {ficha && <>
        <div className="operation-subheading"><h3>{ficha.paciente.codigo_paciente}</h3>
          <span>{ficha.semana_inicio} a {ficha.semana_fin}</span></div>
        <div className="fr04-dose">
          <div><strong>{integer.format(ficha.dosis.sesiones_realizadas)}</strong><span>sesiones realizadas</span></div>
          <div><strong>{decimal.format(ficha.dosis.minutos_realizados)}</strong><span>minutos acumulados</span></div>
          <div><strong>{ficha.clasificacion === 'CUMPLE' ? 'Cumple' : 'No cumple'}</strong><span>dosis semanal</span></div>
        </div>
        {ficha.sesiones.length ? <div className="fr04-table-wrap fr04-session-panel"><table>
          <thead><tr><th>Sesión</th><th>Fecha</th><th>Ingreso</th><th>Salida</th><th>Minutos</th></tr></thead>
          <tbody>{ficha.sesiones.map(item => <tr key={item.codigo_sesion}><td>{item.codigo_sesion}</td>
            <td>{displayDateTime(item.fecha_hora_inicio_sesion)}</td><td>{displayDateTime(item.fecha_hora_ingreso_paciente)}</td>
            <td>{displayDateTime(item.fecha_hora_salida_paciente)}</td>
            <td>{item.minutos_realizados == null ? '—' : decimal.format(item.minutos_realizados)}</td></tr>)}</tbody>
        </table></div> : <p className="operation-help">Esta semana en intervención tuvo cero sesiones registradas.</p>}
      </>}
    </section>}
  </div>
}
