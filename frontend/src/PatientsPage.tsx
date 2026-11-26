import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useSession } from './Auth'
import { formBoolean, formValue, localToday, readOperation, scenarioLabels, useOperationQuery } from './operations'
import type { Scenario } from './operations'

type Patient = {
  id_paciente: number
  codigo_paciente: string
  escenario: Scenario
  sexo: string | null
  fecha_ingreso_programa: string
  fecha_salida_programa: string | null
}

type Clinical = {
  fecha_visita: string
  edad_paciente_en_visita: number | null
  anios_educacion_completados: number | null
  nombre_diagnostico: string | null
  codigo_cie10: string | null
  tiene_diagnostico_alzheimer: boolean | null
  etapa_alzheimer: string | null
  antecedentes_fr01: string | null
  tabaquismo_fr01: string | null
  gold_msi_fr01: number | null
  antipsicoticos_fr01: boolean | null
  antidepresivos_fr01: boolean | null
  ansioliticos_fr01: boolean | null
}

type Preferences = {
  fuente: string
  antecedentes: string | null
  preferencias: string | null
  musica_a_evitar: string | null
  observaciones: string | null
}

type PatientDetail = { paciente: Patient; perfil_clinico: Clinical | null; medicamentos: string[]; preferencias: Preferences | null }
type PatientPage = {
  pacientes: Patient[]; pagina: number; tamano_pagina: number; total: number; total_paginas: number; hay_mas: boolean
  consultado_utc: string | null; datos_desactualizados: boolean
}
const number = new Intl.NumberFormat('es-PE')

function ProgramFields({ patient }: { patient?: Patient }) {
  return <>
    <label>Sexo registrado<select name="sexo" defaultValue={patient?.sexo ?? ''}>
      <option value="">Sin registrar</option><option value="FEMENINO">Femenino</option>
      <option value="MASCULINO">Masculino</option><option value="NO_ESPECIFICADO">No especificado</option>
    </select></label>
    <label>Fecha de ingreso<input name="fecha_ingreso_programa" type="date" defaultValue={patient?.fecha_ingreso_programa ?? localToday()} required /></label>
    <label>Fecha de salida<input name="fecha_salida_programa" type="date" defaultValue={patient?.fecha_salida_programa ?? ''} /></label>
  </>
}

function YesNo({ name, label, value }: { name: string; label: string; value?: boolean | null }) {
  return <label>{label}<select name={name} defaultValue={value == null ? '' : String(value)}>
    <option value="">No consta</option><option value="true">Sí</option><option value="false">No</option>
  </select></label>
}

function programValues(form: FormData) {
  return { sexo: formValue(form, 'sexo'), fecha_ingreso_programa: formValue(form, 'fecha_ingreso_programa'),
    fecha_salida_programa: formValue(form, 'fecha_salida_programa') }
}

export default function PatientsPage() {
  const { user, request } = useSession()
  const { registrar_altas, registrar_perfil_clinico: canViewClinical,
    registrar_preferencias: canViewPreferences } = user.permisos
  const canCreate = registrar_altas && !user.solo_lectura
  const canSaveClinical = canViewClinical && !user.solo_lectura
  const canSavePreferences = canViewPreferences && !user.solo_lectura
  const [scenario, setScenario] = useState<Scenario>('HIBRIDO')
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const results = useRef<HTMLDivElement>(null)
  const searching = search.trim() !== appliedSearch
  const params = new URLSearchParams({ escenario: scenario, buscar: appliedSearch, pagina: String(page) })
  const list = useOperationQuery<PatientPage>(`/api/pacientes?${params}`)
  const detail = useOperationQuery<PatientDetail>(selected === null || creating ? null : `/api/pacientes/${selected}`)

  useEffect(() => {
    if (!searching) return
    const timer = window.setTimeout(() => {
      setAppliedSearch(search.trim())
      setPage(1)
    }, 280)
    return () => window.clearTimeout(timer)
  }, [search, searching])

  useEffect(() => {
    if (results.current) results.current.scrollTop = 0
  }, [scenario, appliedSearch, page])

  async function save(path: string, method: 'POST' | 'PUT', body: object, message: string) {
    if (saving) return
    setSaving(true)
    setNotice('')
    setError('')
    try {
      const result = await readOperation<Patient | null>(await request(path, {
        method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }))
      if (path === '/api/pacientes' && result) {
        setScenario(result.escenario)
        setSearch(result.codigo_paciente)
        setAppliedSearch(result.codigo_paciente)
        setPage(1)
        setCreating(false)
        setSelected(result.id_paciente)
      }
      setNotice(message)
      list.refresh()
      detail.refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudieron guardar los datos.')
    } finally {
      setSaving(false)
    }
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    void save('/api/pacientes', 'POST', { ...programValues(form), codigo_paciente: formValue(form, 'codigo_paciente'),
      escenario: formValue(form, 'escenario') }, 'Paciente registrado.')
  }

  function saveClinical(event: FormEvent<HTMLFormElement>, patientId: number) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const names = ['fecha_visita', 'edad_paciente_en_visita', 'anios_educacion_completados', 'nombre_diagnostico',
      'codigo_cie10', 'etapa_alzheimer', 'antecedentes_fr01', 'tabaquismo_fr01', 'gold_msi_fr01']
    const values = Object.fromEntries(names.map(name => [name, formValue(form, name)]))
    void save(`/api/pacientes/${patientId}/perfil-clinico`, 'POST', { ...values,
      tiene_diagnostico_alzheimer: formBoolean(form, 'tiene_diagnostico_alzheimer'),
      antipsicoticos_fr01: formBoolean(form, 'antipsicoticos_fr01'), antidepresivos_fr01: formBoolean(form, 'antidepresivos_fr01'),
      ansioliticos_fr01: formBoolean(form, 'ansioliticos_fr01') }, 'Perfil clínico registrado como nueva visita.')
  }

  const patient = detail.data?.paciente
  const clinical = detail.data?.perfil_clinico
  const medications = detail.data?.medicamentos ?? []
  const preferences = detail.data?.preferencias
  const pageData = list.data
  const resultStart = pageData?.pacientes.length ? (pageData.pagina - 1) * pageData.tamano_pagina + 1 : 0
  const resultEnd = resultStart ? resultStart - 1 + (pageData?.pacientes.length ?? 0) : 0

  return <div className="operation-page">
    <div className="operation-heading">
      <div><div className="eyebrow">FR01</div><h1>Pacientes</h1><p className="intro">Registro y consulta por código seudonimizado.</p></div>
      {canCreate && <button className="operation-primary" disabled={saving} onClick={() => { setCreating(true); setSelected(null); setNotice(''); setError('') }}>Nuevo paciente</button>}
    </div>
    {notice && <div className="fr04-success" role="status">{notice}</div>}
    {error && <div className="error-panel" role="alert">{error}</div>}
    <div className="operation-columns" data-creating={creating}>
      <section className="panel operation-stack">
        <h2>Buscar pacientes</h2>
        <label>Escenario<select disabled={saving} value={scenario} onChange={event => { setScenario(event.target.value as Scenario); setAppliedSearch(search.trim()); setPage(1); setSelected(null) }}>
          <option value="HIBRIDO">Híbrido</option><option value="SINTETICO_IA">Sintético IA</option>
        </select></label>
        <label>Buscar por código<input disabled={saving} value={search} maxLength={60} onChange={event => setSearch(event.target.value)} /></label>
        {list.error && <p className="operation-error" role="alert">{list.error} <button className="operation-text" onClick={list.refresh}>Reintentar</button></p>}
        {pageData?.datos_desactualizados && <p className="operation-help" role="status">Mostrando la última lectura disponible de SQL Server.</p>}
        <nav className="patient-pagination" aria-label="Paginación de pacientes">
          <div className="operation-actions">
            <button type="button" className="operation-secondary" disabled={page === 1 || saving || searching || list.loading} onClick={() => setPage(value => value - 1)}>Anterior</button>
            <button type="button" className="operation-secondary" disabled={!pageData?.hay_mas || saving || searching || list.loading} onClick={() => setPage(value => value + 1)}>Siguiente</button>
          </div>
          <p className="operation-help" role="status">{pageData && !searching
            ? pageData.total > 0 ? `Página ${number.format(page)} de ${number.format(pageData.total_paginas)} · ${number.format(resultStart)}–${number.format(resultEnd)} de ${number.format(pageData.total)} pacientes` : '0 pacientes'
            : searching || list.loading ? `Consultando página ${number.format(page)}…` : `Página ${number.format(page)}`}</p>
        </nav>
        {!searching && pageData?.total === 0 && <p className="operation-help">No hay pacientes que coincidan con la búsqueda.</p>}
        <div className="operation-result-list patient-results" ref={results}>
          {list.data?.pacientes.map(row => <button type="button" key={row.id_paciente} className="operation-result"
            aria-pressed={selected === row.id_paciente && !creating} disabled={saving || searching}
            onClick={() => { setSelected(row.id_paciente); setCreating(false); setError(''); setNotice('') }}>
            <strong>{row.codigo_paciente}</strong><small>{row.fecha_ingreso_programa}</small>
          </button>)}
        </div>
      </section>
      <div className="operation-stack">
        {creating && <section className="panel operation-stack">
          <h2>Alta de paciente</h2>
          <p className="operation-help">Usa un código interno. Evita nombres y números de documento.</p>
          <form className="operation-stack" onSubmit={create}>
            <div className="operation-form-grid">
              <label>Código del paciente<input name="codigo_paciente" maxLength={60} pattern="[A-Za-z0-9][A-Za-z0-9._\-]*" required /></label>
              <label>Escenario de registro<select name="escenario" defaultValue={scenario}>
                <option value="HIBRIDO">Híbrido</option><option value="SINTETICO_IA">Sintético IA</option>
              </select></label>
              <ProgramFields />
            </div>
            <div className="operation-actions"><button className="operation-primary" disabled={saving}>{saving ? 'Guardando…' : 'Registrar paciente'}</button>
              <button className="operation-secondary" type="button" disabled={saving} onClick={() => { setCreating(false); setError('') }}>Cancelar</button></div>
          </form>
        </section>}
        {detail.loading && <section className="panel"><p className="operation-help" role="status">Cargando ficha…</p></section>}
        {detail.error && <section className="panel"><p className="operation-error" role="alert">{detail.error} <button className="operation-text" onClick={detail.refresh}>Reintentar</button></p></section>}
        {!creating && selected === null && <section className="panel"><p className="operation-help">Selecciona un paciente para ver su ficha.</p></section>}
        {patient && <>
          <section className="panel operation-stack">
            <div className="operation-subheading"><h2>{patient.codigo_paciente}</h2><span>{scenarioLabels[patient.escenario]}</span></div>
            {canCreate ? <form className="operation-stack" key={`${patient.id_paciente}-${patient.fecha_ingreso_programa}-${patient.fecha_salida_programa}-${patient.sexo}`}
              onSubmit={event => { event.preventDefault(); void save(`/api/pacientes/${patient.id_paciente}/programa`, 'PUT', programValues(new FormData(event.currentTarget)), 'Datos del programa actualizados.') }}>
              <div className="operation-form-grid"><ProgramFields patient={patient} /></div>
              <div className="operation-actions"><button className="operation-primary" disabled={saving}>Guardar datos del programa</button></div>
            </form> : <dl className="operation-summary">
              <div><dt>Ingreso</dt><dd>{patient.fecha_ingreso_programa}</dd></div><div><dt>Salida</dt><dd>{patient.fecha_salida_programa ?? '—'}</dd></div>
              <div><dt>Sexo registrado</dt><dd>{patient.sexo?.toLowerCase().replaceAll('_', ' ') ?? '—'}</dd></div>
            </dl>}
          </section>
          {canViewClinical && user.solo_lectura && <section className="panel operation-stack">
            <h2>Perfil clínico</h2>
            {clinical ? <dl className="operation-summary">
              <div><dt>Última visita</dt><dd>{clinical.fecha_visita}</dd></div>
              <div><dt>Edad en la visita</dt><dd>{clinical.edad_paciente_en_visita ?? '—'}</dd></div>
              <div><dt>Diagnóstico registrado</dt><dd>{clinical.nombre_diagnostico ?? '—'}</dd></div>
              <div><dt>Código CIE-10</dt><dd>{clinical.codigo_cie10 ?? '—'}</dd></div>
              <div><dt>Etapa registrada</dt><dd>{clinical.etapa_alzheimer?.toLowerCase().replaceAll('_', ' ') ?? '—'}</dd></div>
              <div><dt>Años de educación</dt><dd>{clinical.anios_educacion_completados ?? '—'}</dd></div>
            </dl> : <p className="operation-help">Sin visitas registradas.</p>}
            {medications.length > 0 && <div>
              <h3>Medicamentos registrados en la última visita</h3>
              <ul className="operation-track-list">{medications.map(name => <li key={name}>{name}</li>)}</ul>
            </div>}
          </section>}
          {canViewPreferences && user.solo_lectura && preferences && <section className="panel operation-stack">
            <h2>Preferencias musicales</h2>
            <dl className="operation-summary">
              <div><dt>Preferencias</dt><dd>{preferences.preferencias ?? '—'}</dd></div>
              <div><dt>Música a evitar</dt><dd>{preferences.musica_a_evitar ?? '—'}</dd></div>
            </dl>
          </section>}
          {canSaveClinical && <section className="panel operation-stack">
            <h2>Perfil clínico</h2>
            {clinical && <p className="operation-help">Última visita registrada el {clinical.fecha_visita}.</p>}
            <form className="operation-stack" onSubmit={event => saveClinical(event, patient.id_paciente)}>
              <div className="operation-form-grid">
                <label>Fecha de la visita<input name="fecha_visita" type="date" defaultValue={localToday()} required /></label>
                <label>Edad en la visita<input name="edad_paciente_en_visita" type="number" min={0} max={130} step="0.01" defaultValue={clinical?.edad_paciente_en_visita ?? ''} /></label>
                <label>Años de educación<input name="anios_educacion_completados" type="number" min={0} max={80} defaultValue={clinical?.anios_educacion_completados ?? ''} /></label>
                <label>Diagnóstico registrado<input name="nombre_diagnostico" maxLength={200} defaultValue={clinical?.nombre_diagnostico ?? ''} /></label>
                <label>Código CIE-10<input name="codigo_cie10" maxLength={16} defaultValue={clinical?.codigo_cie10 ?? ''} /></label>
                <YesNo name="tiene_diagnostico_alzheimer" label="Diagnóstico de Alzheimer" value={clinical?.tiene_diagnostico_alzheimer} />
                <label>Etapa registrada<select name="etapa_alzheimer" defaultValue={clinical?.etapa_alzheimer ?? ''}>
                  <option value="">Sin registrar</option><option value="LEVE">Leve</option><option value="MODERADA">Moderada</option>
                  <option value="OTRA">Otra</option><option value="NO_CONSTA">No consta</option>
                </select></label>
                <label>Tabaquismo<input name="tabaquismo_fr01" maxLength={100} defaultValue={clinical?.tabaquismo_fr01 ?? ''} /></label>
                <label>Puntaje Gold-MSI<input name="gold_msi_fr01" type="number" min={0} max={99999.99} step="0.01" defaultValue={clinical?.gold_msi_fr01 ?? ''} /></label>
                <YesNo name="antipsicoticos_fr01" label="Antipsicóticos" value={clinical?.antipsicoticos_fr01} />
                <YesNo name="antidepresivos_fr01" label="Antidepresivos" value={clinical?.antidepresivos_fr01} />
                <YesNo name="ansioliticos_fr01" label="Ansiolíticos" value={clinical?.ansioliticos_fr01} />
              </div>
              <label>Antecedentes<textarea name="antecedentes_fr01" rows={3} maxLength={500} defaultValue={clinical?.antecedentes_fr01 ?? ''} /></label>
              <div className="operation-actions"><button className="operation-primary" disabled={saving}>Registrar nueva visita</button></div>
            </form>
          </section>}
          {canSavePreferences && <section className="panel operation-stack">
            <h2>Preferencias musicales</h2>
            <form className="operation-stack" onSubmit={event => {
              event.preventDefault()
              const form = new FormData(event.currentTarget)
              const names = ['fuente', 'antecedentes', 'preferencias', 'musica_a_evitar', 'observaciones']
              void save(`/api/pacientes/${patient.id_paciente}/preferencias`, 'PUT',
                Object.fromEntries(names.map(name => [name, formValue(form, name)])), 'Preferencias musicales guardadas.')
            }}>
              <label>Fuente<select name="fuente" defaultValue={preferences?.fuente ?? ''} required>
                <option value="">Seleccionar</option><option value="PACIENTE">Paciente</option><option value="FAMILIAR">Familiar</option>
                <option value="CUIDADOR">Cuidador</option><option value="OTRA">Otra</option>
              </select></label>
              <label>Antecedentes musicales<textarea name="antecedentes" rows={2} maxLength={500} defaultValue={preferences?.antecedentes ?? ''} /></label>
              <label>Géneros, artistas o canciones preferidos<textarea name="preferencias" rows={2} maxLength={500} defaultValue={preferences?.preferencias ?? ''} /></label>
              <label>Música a evitar<textarea name="musica_a_evitar" rows={2} maxLength={500} defaultValue={preferences?.musica_a_evitar ?? ''} /></label>
              <label>Observaciones<textarea name="observaciones" rows={2} maxLength={500} defaultValue={preferences?.observaciones ?? ''} /></label>
              <div className="operation-actions"><button className="operation-primary" disabled={saving}>Guardar preferencias</button></div>
            </form>
          </section>}
        </>}
      </div>
    </div>
  </div>
}
