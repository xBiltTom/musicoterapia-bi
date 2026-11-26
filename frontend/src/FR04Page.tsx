import { useEffect, useState } from 'react'

type Scenario = 'HIBRIDO' | 'SINTETICO_IA'
type Coverage = 'COMPLETA' | 'INSUFICIENTE' | 'CERO_CONFIRMADO'
type Summary = {
  candidatos_programa: number
  fichas_registradas: number
  fichas_pendientes: number
  en_intervencion: number
  fuera_intervencion: number
  cumple: number
  no_cumple: number
  indeterminada: number
  k4_tasa_adherencia: number | null
  estado_k4: string
}
type Preview = {
  paciente: { codigo_paciente: string; escenario: Scenario }
  semana_inicio: string
  semana_fin: string
  programa: string
  registro: {
    en_intervencion: boolean
    cobertura_registro: Coverage | null
    codigo_responsable: string
    observaciones: string | null
    fecha_actualizacion_utc: string
  } | null
  dosis: { sesiones_realizadas: number; minutos_realizados: number; horas_invalidas: number }
  clasificacion: string
  sesiones: {
    codigo_sesion: string
    fecha_hora_inicio_sesion: string
    estado_participacion: string
    minutos_realizados: number | null
  }[]
}

const formatter = new Intl.NumberFormat('es-PE')

async function readJson<T>(response: Response): Promise<T> {
  const body = await response.json()
  if (!response.ok) throw new Error(body.detail || 'No se pudo completar la consulta')
  return body as T
}

function isMonday(value: string) {
  return Boolean(value) && new Date(`${value}T12:00:00`).getDay() === 1
}

export default function FR04Page() {
  const [scenario, setScenario] = useState<Scenario>('HIBRIDO')
  const [week, setWeek] = useState('2024-10-28')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState('')
  const [suggestions, setSuggestions] = useState<{ codigo_paciente: string }[]>([])
  const [responsibles, setResponsibles] = useState<{ codigo_responsable: string; nombre_completo: string }[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [inIntervention, setInIntervention] = useState<boolean | null>(null)
  const [coverage, setCoverage] = useState<Coverage | ''>('')
  const [responsible, setResponsible] = useState('')
  const [notes, setNotes] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const validWeek = isMonday(week)

  useEffect(() => {
    fetch('/api/fr04/responsables')
      .then(readJson<{ codigo_responsable: string; nombre_completo: string }[]>)
      .then(setResponsibles)
      .catch(() => setResponsibles([]))
  }, [])

  useEffect(() => {
    setSelected('')
    setPreview(null)
    setMessage('')
  }, [scenario, week])

  useEffect(() => {
    if (!validWeek) { setSuggestions([]); return }
    const controller = new AbortController()
    const params = new URLSearchParams({ escenario: scenario, semana_inicio: week, buscar: search.trim() })
    fetch(`/api/fr04/pacientes?${params}`, { signal: controller.signal })
      .then(readJson<{ codigo_paciente: string }[]>)
      .then(setSuggestions)
      .catch(() => { if (!controller.signal.aborted) setSuggestions([]) })
    return () => controller.abort()
  }, [scenario, week, search, validWeek])

  useEffect(() => {
    if (!validWeek) { setSummary(null); return }
    const controller = new AbortController()
    const params = new URLSearchParams({ escenario: scenario, semana_inicio: week })
    fetch(`/api/fr04/resumen?${params}`, { signal: controller.signal })
      .then(readJson<Summary>)
      .then(setSummary)
      .catch(() => { if (!controller.signal.aborted) setSummary(null) })
    return () => controller.abort()
  }, [scenario, week, validWeek, refresh])

  useEffect(() => {
    if (!selected || !validWeek) { setPreview(null); return }
    const controller = new AbortController()
    setLoading(true)
    setError('')
    setPreview(null)
    const params = new URLSearchParams({ escenario: scenario, semana_inicio: week, codigo_paciente: selected })
    fetch(`/api/fr04/ficha?${params}`, { signal: controller.signal })
      .then(readJson<Preview>)
      .then(data => {
        setPreview(data)
        setInIntervention(data.registro?.en_intervencion ?? null)
        setCoverage(data.registro?.cobertura_registro ?? '')
        setResponsible(data.registro?.codigo_responsable ?? '')
        setNotes(data.registro?.observaciones ?? '')
      })
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [selected, scenario, week, validWeek, refresh])

  async function save() {
    if (!preview || inIntervention === null || !responsible.trim() || (inIntervention && !coverage)) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await readJson<Preview>(await fetch('/api/fr04/ficha', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          escenario: scenario,
          codigo_paciente: selected,
          semana_inicio: week,
          en_intervencion: inIntervention,
          cobertura_registro: inIntervention ? coverage : null,
          codigo_responsable: responsible.trim(),
          observaciones: notes.trim() || null,
        }),
      }))
      setMessage('Ficha semanal guardada. La clasificación y el resumen se actualizaron.')
      setRefresh(value => value + 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar FR04')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fr04-page">
      <div className="eyebrow">FORMULARIO FR04 · CONTROL SEMANAL</div>
      <h1>Adherencia a la intervención</h1>
      <p className="intro">Confirma quién estuvo en intervención y la cobertura del registro. Las sesiones y minutos se calculan desde el diario FR03.</p>

      <div className="fr04-context panel">
        <label>Escenario<select value={scenario} onChange={e => setScenario(e.target.value as Scenario)}><option value="HIBRIDO">Híbrido</option><option value="SINTETICO_IA">Sintético IA</option></select></label>
        <label>Inicio de semana ISO<input type="date" value={week} onChange={e => setWeek(e.target.value)} /></label>
        <span className={validWeek ? 'week-valid' : 'week-invalid'}>{validWeek ? 'Semana válida · lunes a domingo' : 'Selecciona un lunes'}</span>
      </div>

      <div className="fr04-summary">
        <div className="fr04-stat"><small>Candidatos en el programa</small><strong>{summary ? formatter.format(summary.candidatos_programa) : '—'}</strong></div>
        <div className="fr04-stat"><small>Fichas registradas</small><strong>{summary ? formatter.format(summary.fichas_registradas) : '—'}</strong></div>
        <div className="fr04-stat"><small>Fichas pendientes</small><strong>{summary ? formatter.format(summary.fichas_pendientes) : '—'}</strong></div>
        <div className="fr04-stat highlighted"><small>K4 · adherencia semanal</small><strong>{summary?.k4_tasa_adherencia == null ? '—' : `${summary.k4_tasa_adherencia.toFixed(1)} %`}</strong></div>
      </div>
      <p className="fr04-help">K4 se publica cuando todos los pacientes candidatos tienen ficha, ninguna cobertura es insuficiente y existe al menos un paciente en intervención. El ingreso al programa solo identifica candidatos; no confirma intervención.</p>

      <div className="fr04-columns">
        <section className="panel fr04-search-panel">
          <div className="eyebrow">PACIENTE Y SEMANA</div><h2>Seleccionar paciente</h2>
          <label>Código seudonimizado<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar por código" maxLength={60} /></label>
          <div className="fr04-suggestions">{suggestions.map(item => <button key={item.codigo_paciente} className={selected === item.codigo_paciente ? 'selected' : ''} onClick={() => { setSelected(item.codigo_paciente); setSearch(item.codigo_paciente); setMessage('') }}>{item.codigo_paciente}</button>)}</div>
          {loading && <p className="fr04-muted">Consultando sesiones…</p>}
          {preview && <><div className="fr04-divider" /><div className="fr04-patient"><small>PACIENTE SELECCIONADO</small><strong>{preview.paciente.codigo_paciente}</strong><span>{preview.semana_inicio} al {preview.semana_fin}</span></div><div className="fr04-dose"><div><strong>{preview.dosis.sesiones_realizadas}</strong><span>sesiones realizadas</span></div><div><strong>{preview.dosis.minutos_realizados.toFixed(1)}</strong><span>minutos acumulados</span></div></div>{preview.dosis.horas_invalidas > 0 && <p className="fr04-warning">{preview.dosis.horas_invalidas} participación(es) sin duración válida.</p>}</>}
        </section>

        <section className="panel fr04-form-panel">
          <div className="eyebrow">REGISTRO FR04</div><h2>Confirmar vigencia y cobertura</h2>
          {!preview ? <p className="fr04-placeholder">Selecciona un paciente para revisar su semana y completar la ficha.</p> : <>
            <div className="fr04-field"><span>Vigencia en la semana</span><div className="fr04-choice"><label><input type="radio" name="vigencia" checked={inIntervention === true} onChange={() => setInIntervention(true)} /> En intervención</label><label><input type="radio" name="vigencia" checked={inIntervention === false} onChange={() => { setInIntervention(false); setCoverage('') }} /> Fuera de intervención</label></div></div>
            {inIntervention && <label className="fr04-field">Cobertura del registro<select value={coverage} onChange={e => setCoverage(e.target.value as Coverage | '')}><option value="">Seleccionar cobertura</option><option value="COMPLETA">Completa</option><option value="CERO_CONFIRMADO">Cero sesiones confirmado</option><option value="INSUFICIENTE">Insuficiente</option></select></label>}
            <label className="fr04-field">Terapeuta responsable<select value={responsible} onChange={e => setResponsible(e.target.value)}><option value="">Seleccionar terapeuta</option>{responsibles.map(item => <option key={item.codigo_responsable} value={item.codigo_responsable}>{item.codigo_responsable} · {item.nombre_completo}</option>)}</select></label>
            <label className="fr04-field">Observaciones<textarea value={notes} onChange={e => setNotes(e.target.value)} maxLength={500} rows={3} placeholder="Fuente de la confirmación o incidencia de cobertura" /></label>
            <div className="fr04-save-row"><span>Clasificación: <strong>{preview.clasificacion.replaceAll('_', ' ').toLowerCase()}</strong></span><button onClick={save} disabled={saving || inIntervention === null || !responsible.trim() || (inIntervention && !coverage)}>{saving ? 'Guardando…' : 'Guardar FR04'}</button></div>
          </>}
        </section>
      </div>

      {error && <div className="error-panel" role="alert">{error}</div>}
      {message && <div className="fr04-success" role="status">{message}</div>}

      {preview && <section className="panel fr04-session-panel"><div className="eyebrow">TRAZABILIDAD FR03</div><h2>Sesiones del paciente en la semana</h2>{preview.sesiones.length ? <div className="fr04-table-wrap"><table><thead><tr><th>Sesión</th><th>Fecha</th><th>Participación</th><th>Minutos</th></tr></thead><tbody>{preview.sesiones.map(item => <tr key={item.codigo_sesion}><td>{item.codigo_sesion}</td><td>{item.fecha_hora_inicio_sesion.slice(0, 16).replace('T', ' ')}</td><td>{item.estado_participacion}</td><td>{item.minutos_realizados == null ? '—' : item.minutos_realizados.toFixed(1)}</td></tr>)}</tbody></table></div> : <p className="fr04-placeholder">No hay sesiones registradas. Confirma «cero sesiones» únicamente si la ausencia fue verificada.</p>}</section>}
      <footer>FR04 · Registro semanal sobre SQL Server transaccional · Sin ETL ni data mart</footer>
    </div>
  )
}
