import { useState } from 'react'
import type { FormEvent } from 'react'
import { useSession } from './Auth'
import { displayDateTime, formValue, localToday, readOperation, scenarioLabels, useOperationQuery } from './operations'
import type { Scenario } from './operations'

type PatientOption = { id_paciente: number; codigo_paciente: string }
type Song = { id_cancion: number; titulo_cancion: string; nombre_album: string | null; anio_publicacion: number }
type Playlist = { id_lista_reproduccion: number; nombre_lista_reproduccion: string }
type Music = { pistas: Song[]; listas: Playlist[] }
type Usage = 'SIN_MUSICA' | 'SIN_DETALLE' | 'PISTAS' | 'LISTA'
type TrackDraft = { key: number; song: Song }
type ParticipationDraft = { patient: PatientOption; tracks: TrackDraft[] }
type SessionRow = {
  id_sesion_musical: number
  codigo_sesion: string
  fecha_hora_inicio_sesion: string
  fecha_hora_fin_sesion: string
  modalidad_sesion: string
  tipo_actividad: string
  uso_musica: Usage | null
  codigo_personal: string
}
type Participation = {
  codigo_paciente: string
  estado_participacion: string
  fecha_hora_ingreso_paciente: string | null
  fecha_hora_salida_paciente: string | null
  experiencia_sesion: string | null
  efecto_resto_dia: string | null
  estado_respuesta_positiva: string | null
  minutos_hasta_primera_respuesta: number | null
  comentarios: string | null
  pistas: { orden_reproduccion: number; titulo_cancion: string; fecha_hora_inicio_cancion: string; fecha_hora_fin_cancion: string }[]
}
type SessionDetail = { sesion: SessionRow & { fecha_hora_inicio_musica: string | null; nombre_lista_reproduccion: string | null }; participantes: Participation[] }

const usageLabels: Record<Usage, string> = {
  SIN_MUSICA: 'Sin música', SIN_DETALLE: 'Música sin detalle', PISTAS: 'Pistas del catálogo', LISTA: 'Lista de reproducción',
}

function label(value: string | null) {
  if (!value) return '—'
  const words = value.toLowerCase().replaceAll('_', ' ')
  return words[0].toUpperCase() + words.slice(1)
}

function ExperienceOptions({ effect = false }: { effect?: boolean }) {
  return <><option value="">Sin registrar</option><option value={effect ? 'POSITIVO' : 'POSITIVA'}>Positiva</option>
    <option value={effect ? 'NEUTRO' : 'NEUTRA'}>Neutra</option><option value={effect ? 'NEGATIVO' : 'NEGATIVA'}>Negativa</option>
    <option value="NO_SABE">No sabe</option></>
}

function ParticipationForm({ draft, usage, songs, onAddTrack, onRemoveTrack, remove }: {
  draft: ParticipationDraft; usage: Usage; songs: Song[]; onAddTrack: (song: Song) => void
  onRemoveTrack: (key: number) => void; remove: () => void
}) {
  const [attendance, setAttendance] = useState('COMPLETA')
  const [response, setResponse] = useState('')
  const [songId, setSongId] = useState('')
  const prefix = `p${draft.patient.id_paciente}-`
  const chosen = songs.find(song => String(song.id_cancion) === songId)
  const canPickTracks = usage === 'PISTAS' || usage === 'LISTA'

  return <fieldset className="operation-participant operation-stack">
    <legend>{draft.patient.codigo_paciente}</legend>
    <div className="operation-actions"><button className="operation-text" type="button" onClick={remove}>Quitar participante</button></div>
    <div className="operation-form-grid">
      <label>Participación<select name={prefix + 'estado'} value={attendance} onChange={event => setAttendance(event.target.value)}>
        <option value="COMPLETA">Completa</option><option value="INTERRUMPIDA">Interrumpida</option><option value="AUSENTE">Ausente</option>
      </select></label>
      {attendance !== 'AUSENTE' && <>
        <label>Ingreso del paciente<input name={prefix + 'ingreso'} type="datetime-local" required={attendance === 'INTERRUMPIDA'} /></label>
        <label>Salida del paciente<input name={prefix + 'salida'} type="datetime-local" required={attendance === 'INTERRUMPIDA'} /></label>
        {attendance === 'INTERRUMPIDA' && <label>Motivo de interrupción<input name={prefix + 'motivo_interrupcion'} maxLength={500} /></label>}
        <label>Experiencia durante la sesión<select name={prefix + 'experiencia'}><ExperienceOptions /></select></label>
        <label>Efecto durante el resto del día<select name={prefix + 'efecto_resto_dia'}><ExperienceOptions effect /></select></label>
        {usage !== 'SIN_MUSICA' && <>
          <label>Respuesta positiva<select name={prefix + 'estado_respuesta'} value={response} onChange={event => setResponse(event.target.value)}>
            <option value="">Sin registrar</option><option value="OBSERVADA">Observada</option>
            <option value="SIN_RESPUESTA">Sin respuesta observada</option><option value="NO_OBSERVADA">No se observó</option>
          </select></label>
          {response === 'OBSERVADA' && <label>Hora de primera respuesta<input name={prefix + 'primera_respuesta'} type="datetime-local" required /></label>}
        </>}
        <label>Agitación antes (0–16)<input name={prefix + 'agitacion_antes'} type="number" min={0} max={16} /></label>
        <label>Agitación después (0–16)<input name={prefix + 'agitacion_despues'} type="number" min={0} max={16} /></label>
      </>}
    </div>
    {attendance === 'COMPLETA' && <p className="operation-help">Si dejas el ingreso y la salida en blanco, se usan las horas de la sesión.</p>}
    <label>Comentarios<textarea name={prefix + 'comentarios'} rows={2} maxLength={500} /></label>
    {attendance !== 'AUSENTE' && canPickTracks && <div className="operation-stack">
      <div className="operation-inline">
        <label>Pista<select value={chosen ? songId : ''} onChange={event => setSongId(event.target.value)}>
          <option value="">Seleccionar pista</option>
          {songs.map(song => <option key={song.id_cancion} value={song.id_cancion}>{song.titulo_cancion} · {song.anio_publicacion}</option>)}
        </select></label>
        <button className="operation-secondary" type="button" disabled={!chosen || draft.tracks.length >= 30} onClick={() => {
          if (chosen) { onAddTrack(chosen); setSongId('') }
        }}>Añadir pista</button>
      </div>
      {draft.tracks.map(track => <div key={track.key} className="operation-track">
        <div className="operation-subheading"><strong>{track.song.titulo_cancion}</strong><button className="operation-text" type="button" onClick={() => onRemoveTrack(track.key)}>Quitar pista</button></div>
        <div className="operation-form-grid">
          <label>Inicio de la pista<input name={`${prefix}pista-${track.key}-inicio`} type="datetime-local" required /></label>
          <label>Fin de la pista<input name={`${prefix}pista-${track.key}-fin`} type="datetime-local" required /></label>
        </div>
      </div>)}
    </div>}
  </fieldset>
}

function SessionForm({ scenario, saving, submit, cancel }: {
  scenario: Scenario; saving: boolean; submit: (body: object) => void; cancel: () => void
}) {
  const { user } = useSession()
  const [start, setStart] = useState(`${localToday()}T09:00`)
  const [usage, setUsage] = useState<Usage>('SIN_DETALLE')
  const [modality, setModality] = useState('INDIVIDUAL')
  const [patientSearch, setPatientSearch] = useState('')
  const [musicSearch, setMusicSearch] = useState('')
  const [playlist, setPlaylist] = useState<Playlist | null>(null)
  const [participants, setParticipants] = useState<ParticipationDraft[]>([])
  const [nextTrack, setNextTrack] = useState(1)
  const patientParams = new URLSearchParams({ escenario: scenario, fecha: start.slice(0, 10), buscar: patientSearch.trim() })
  const musicParams = new URLSearchParams({ escenario: scenario, buscar: musicSearch.trim() })
  const patientOptions = useOperationQuery<PatientOption[]>(start ? `/api/sesiones/pacientes?${patientParams}` : null)
  const music = useOperationQuery<Music>(usage === 'LISTA' || usage === 'PISTAS' ? `/api/sesiones/musica?${musicParams}` : null)
  const playlists = music.data?.listas ?? []

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving || participants.length === 0) return
    const form = new FormData(event.currentTarget)
    const entered = participants.map(({ patient, tracks }) => {
      const prefix = `p${patient.id_paciente}-`
      const names = ['estado', 'ingreso', 'salida', 'motivo_interrupcion', 'experiencia', 'efecto_resto_dia',
        'estado_respuesta', 'primera_respuesta', 'agitacion_antes', 'agitacion_despues', 'comentarios']
      const values = Object.fromEntries(names.map(name => [name, formValue(form, prefix + name)]))
      const recordedTracks = values.estado !== 'AUSENTE' && (usage === 'PISTAS' || usage === 'LISTA') ? tracks.map(track => ({
        id_cancion: track.song.id_cancion,
        inicio: formValue(form, `${prefix}pista-${track.key}-inicio`), fin: formValue(form, `${prefix}pista-${track.key}-fin`),
      })) : []
      return { id_paciente: patient.id_paciente, ...values, pistas: recordedTracks }
    })
    submit({ codigo_sesion: formValue(form, 'codigo_sesion'), escenario: scenario, modalidad: modality,
      actividad: formValue(form, 'actividad'), inicio: start, fin: formValue(form, 'fin'), uso_musica: usage,
      inicio_musica: formValue(form, 'inicio_musica'), id_lista_reproduccion: usage === 'LISTA' ? playlist?.id_lista_reproduccion : null,
      participantes: entered })
  }

  function addTrack(patientId: number, song: Song) {
    setParticipants(items => items.map(item => item.patient.id_paciente === patientId ? {
      ...item, tracks: [...item.tracks, { key: nextTrack, song }],
    } : item))
    setNextTrack(value => value + 1)
  }

  return <section className="panel operation-stack">
    <div className="operation-subheading"><h2>Nueva sesión</h2><span>{scenarioLabels[scenario]}</span></div>
    <form className="operation-stack" onSubmit={submitForm}>
      <div className="operation-form-grid">
        <label>Código de sesión<input name="codigo_sesion" maxLength={100} pattern="[A-Za-z0-9][A-Za-z0-9._\-]*" required /></label>
        <label>Modalidad<select value={modality} onChange={event => setModality(event.target.value)}>
          <option value="INDIVIDUAL" disabled={participants.length > 1}>Individual</option><option value="GRUPAL">Grupal</option>
        </select></label>
        <label>Actividad<select name="actividad"><option value="ESCUCHA">Escucha</option><option value="CANTO">Canto</option>
          <option value="ESTIMULACION_SENSORIAL">Estimulación sensorial</option><option value="OTRA">Otra o combinada</option></select></label>
        <label>Inicio de sesión<input type="datetime-local" name="inicio" value={start} onChange={event => setStart(event.target.value)} required /></label>
        <label>Fin de sesión<input type="datetime-local" name="fin" defaultValue={`${localToday()}T09:30`} min={start} required /></label>
        <label>Música utilizada<select value={usage} onChange={event => setUsage(event.target.value as Usage)}>
          <option value="SIN_MUSICA">Sin música</option><option value="SIN_DETALLE">Música sin detalle</option>
          {user.permisos.registrar_musica && <><option value="PISTAS">Pistas del catálogo</option><option value="LISTA">Lista de reproducción</option></>}
        </select></label>
        {usage !== 'SIN_MUSICA' && <label>Inicio de la música<input name="inicio_musica" type="datetime-local" min={start} /></label>}
      </div>
      {(usage === 'LISTA' || usage === 'PISTAS') && <div className="operation-stack">
        <label>Buscar en el catálogo<input value={musicSearch} maxLength={100} onChange={event => setMusicSearch(event.target.value)} /></label>
        {music.loading && <p className="operation-help" role="status">Consultando catálogo…</p>}
        {music.error && <p className="operation-error" role="alert">{music.error}</p>}
        {music.data && !music.data.pistas.length && !music.data.listas.length && <p className="operation-help">Sin coincidencias en este escenario.</p>}
        {usage === 'LISTA' && <label>Lista utilizada<select value={playlist?.id_lista_reproduccion ?? ''} required onChange={event => {
          setPlaylist(playlists.find(item => String(item.id_lista_reproduccion) === event.target.value) ?? null)
        }}>
          <option value="">Seleccionar lista</option>
          {playlist && !playlists.some(item => item.id_lista_reproduccion === playlist.id_lista_reproduccion) && <option value={playlist.id_lista_reproduccion}>{playlist.nombre_lista_reproduccion}</option>}
          {playlists.map(item => <option key={item.id_lista_reproduccion} value={item.id_lista_reproduccion}>{item.nombre_lista_reproduccion}</option>)}
        </select></label>}
      </div>}
      <div className="operation-stack">
        <h3>Participantes</h3>
        {user.alcance_datos === 'PROPIOS' && <p className="operation-help">Escribe el código completo del paciente para agregarlo.</p>}
        <label>Buscar participante<input value={patientSearch} maxLength={60} onChange={event => setPatientSearch(event.target.value)} /></label>
        {patientOptions.error && <p className="operation-error" role="alert">{patientOptions.error}</p>}
        {patientOptions.data?.length === 0 && (user.alcance_datos === 'GLOBAL' || patientSearch.trim()) && <p className="operation-help">Sin pacientes vigentes que coincidan con la búsqueda y la fecha.</p>}
        <div className="operation-chips">
          {patientOptions.data?.map(patient => <button className="operation-secondary" type="button" key={patient.id_paciente}
            disabled={participants.some(item => item.patient.id_paciente === patient.id_paciente) || participants.length >= (modality === 'INDIVIDUAL' ? 1 : 25)}
            onClick={() => setParticipants(items => [...items, { patient, tracks: [] }])}>{patient.codigo_paciente}</button>)}
        </div>
      </div>
      {participants.map(item => <ParticipationForm key={item.patient.id_paciente} draft={item} usage={usage} songs={music.data?.pistas ?? []}
        remove={() => setParticipants(items => items.filter(row => row.patient.id_paciente !== item.patient.id_paciente))}
        onAddTrack={song => addTrack(item.patient.id_paciente, song)}
        onRemoveTrack={key => setParticipants(items => items.map(row => row.patient.id_paciente === item.patient.id_paciente
          ? { ...row, tracks: row.tracks.filter(track => track.key !== key) } : row))} />)}
      <div className="operation-actions"><button className="operation-primary" disabled={saving || participants.length === 0}>{saving ? 'Guardando…' : 'Registrar sesión'}</button>
        <button className="operation-secondary" disabled={saving} type="button" onClick={cancel}>Cancelar</button></div>
    </form>
  </section>
}

function SessionRecord({ detail }: { detail: SessionDetail }) {
  const { sesion, participantes } = detail
  return <section className="panel operation-stack">
    <div className="operation-subheading"><h2>{sesion.codigo_sesion}</h2><span>{label(sesion.modalidad_sesion)}</span></div>
    <dl className="operation-summary">
      <div><dt>Inicio</dt><dd>{displayDateTime(sesion.fecha_hora_inicio_sesion)}</dd></div>
      <div><dt>Fin</dt><dd>{displayDateTime(sesion.fecha_hora_fin_sesion)}</dd></div>
      <div><dt>Actividad</dt><dd>{label(sesion.tipo_actividad)}</dd></div>
      <div><dt>Responsable</dt><dd>{sesion.codigo_personal}</dd></div>
      <div><dt>Música</dt><dd>{sesion.nombre_lista_reproduccion ?? (sesion.uso_musica ? usageLabels[sesion.uso_musica] : '—')}</dd></div>
      <div><dt>Inicio de la música</dt><dd>{displayDateTime(sesion.fecha_hora_inicio_musica)}</dd></div>
    </dl>
    {participantes.map(item => <div className="operation-track" key={item.codigo_paciente}>
      <div className="operation-subheading"><h3>{item.codigo_paciente}</h3><span>{label(item.estado_participacion)}</span></div>
      <dl className="operation-summary">
        <div><dt>Ingreso</dt><dd>{displayDateTime(item.fecha_hora_ingreso_paciente)}</dd></div>
        <div><dt>Salida</dt><dd>{displayDateTime(item.fecha_hora_salida_paciente)}</dd></div>
        <div><dt>Experiencia</dt><dd>{label(item.experiencia_sesion)}</dd></div>
        <div><dt>Efecto el resto del día</dt><dd>{label(item.efecto_resto_dia)}</dd></div>
        <div><dt>Respuesta</dt><dd>{label(item.estado_respuesta_positiva)}</dd></div>
        <div><dt>Latencia</dt><dd>{item.minutos_hasta_primera_respuesta == null ? '—' : `${item.minutos_hasta_primera_respuesta} min`}</dd></div>
      </dl>
      {item.comentarios && <p>{item.comentarios}</p>}
      {!!item.pistas.length && <ul className="operation-track-list">{item.pistas.map(track => <li key={track.orden_reproduccion}>
        {track.titulo_cancion} · {displayDateTime(track.fecha_hora_inicio_cancion)} a {displayDateTime(track.fecha_hora_fin_cancion)}
      </li>)}</ul>}
    </div>)}
  </section>
}

export default function SessionsPage() {
  const { user, request } = useSession()
  const [scenario, setScenario] = useState<Scenario>('HIBRIDO')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const params = new URLSearchParams({ escenario: scenario, buscar: search.trim(), pagina: String(page) })
  const list = useOperationQuery<{ sesiones: SessionRow[]; hay_mas: boolean }>(`/api/sesiones?${params}`)
  const detail = useOperationQuery<SessionDetail>(selected === null || creating ? null : `/api/sesiones/${selected}?escenario=${scenario}`)

  async function save(body: object) {
    setSaving(true)
    setNotice('')
    setError('')
    try {
      const result = await readOperation<{ id_sesion_musical: number; codigo_sesion: string }>(await request('/api/sesiones', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }))
      setCreating(false)
      setSearch(result.codigo_sesion)
      setPage(1)
      setSelected(result.id_sesion_musical)
      list.refresh()
      setNotice('Sesión registrada. Las participaciones válidas ya están disponibles en el control semanal.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo registrar la sesión.')
    } finally {
      setSaving(false)
    }
  }

  return <div className="operation-page">
    <div className="operation-heading">
      <div><div className="eyebrow">FR02 Y FR03</div><h1>Diario de sesiones</h1><p className="intro">{user.solo_lectura ? 'Consulta la participación, la música utilizada y las observaciones.' : 'Registra la participación, la música utilizada y las observaciones de la sesión.'}</p></div>
      {!user.solo_lectura && <button className="operation-primary" disabled={saving} onClick={() => { setCreating(true); setSelected(null); setError(''); setNotice('') }}>Nueva sesión</button>}
    </div>
    {notice && <div className="fr04-success" role="status">{notice}</div>}
    {error && <div className="error-panel" role="alert">{error}</div>}
    <div className="operation-columns" data-creating={creating}>
      <section className="panel operation-stack">
        <h2>Buscar sesiones</h2>
        <label>Escenario<select disabled={creating || saving} value={scenario} onChange={event => { setScenario(event.target.value as Scenario); setSelected(null); setPage(1) }}>
          <option value="HIBRIDO">Híbrido</option><option value="SINTETICO_IA">Sintético IA</option>
        </select></label>
        {creating && <p className="operation-help">La sesión se registrará en este escenario.</p>}
        <label>Buscar por código<input disabled={saving} value={search} maxLength={100} onChange={event => { setSearch(event.target.value); setPage(1) }} /></label>
        {list.error && <p className="operation-error" role="alert">{list.error} <button className="operation-text" onClick={list.refresh}>Reintentar</button></p>}
        {list.loading && <p className="operation-help" role="status">Consultando sesiones…</p>}
        {list.data?.sesiones.length === 0 && <p className="operation-help">No hay sesiones que coincidan con la búsqueda.</p>}
        <div className="operation-result-list">
          {list.data?.sesiones.map(row => <button type="button" key={row.id_sesion_musical} className="operation-result"
            aria-pressed={selected === row.id_sesion_musical && !creating} disabled={saving}
            onClick={() => { setSelected(row.id_sesion_musical); setCreating(false); setError(''); setNotice('') }}>
            <strong>{row.codigo_sesion}</strong><small>{displayDateTime(row.fecha_hora_inicio_sesion)}</small>
          </button>)}
        </div>
        {(page > 1 || list.data?.hay_mas) && <div className="operation-actions">
          <button type="button" className="operation-secondary" disabled={page === 1 || saving} onClick={() => setPage(value => value - 1)}>Anterior</button>
          <button type="button" className="operation-secondary" disabled={!list.data?.hay_mas || saving} onClick={() => setPage(value => value + 1)}>Siguiente</button>
        </div>}
      </section>
      {creating && <SessionForm scenario={scenario} saving={saving} submit={save} cancel={() => { setCreating(false); setError('') }} />}
      {detail.loading && <section className="panel"><p className="operation-help" role="status">Cargando sesión…</p></section>}
      {detail.error && <section className="panel"><p className="operation-error" role="alert">{detail.error} <button className="operation-text" onClick={detail.refresh}>Reintentar</button></p></section>}
      {detail.data && <SessionRecord detail={detail.data} />}
      {!creating && selected === null && <section className="panel"><p className="operation-help">{user.solo_lectura ? 'Selecciona una sesión para ver su ficha.' : 'Selecciona una sesión o registra una nueva.'}</p></section>}
    </div>
  </div>
}
