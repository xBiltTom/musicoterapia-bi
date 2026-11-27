import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useSession } from './Auth'
import { populationLabels, scenarioLabels, useOperationQuery } from './operations'
import type { Population, Scenario } from './operations'
import './indicators.css'

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

type Status = 'verde' | 'ambar' | 'rojo' | 'sin_datos'
type Rated<T> = T & { estado: Status }
type Filters = { escenario: Scenario | 'COMPARAR'; poblacion: Population; desde: string; hasta: string }
type Monthly = { mes: string; tasa_positiva: number | null }
type Dashboard = {
  filtros: { escenario: Scenario; alcance: 'global' | 'propios' }
  datos_desactualizados?: boolean
  k1?: Rated<{ tasa_positiva: number | null; positivas: number; neutras: number; negativas: number; participaciones_validas: number }>
  k2?: Rated<{ reduccion_promedio: number | null; pacientes_con_par: number; tasa_respondedores: number | null }>
  k3?: Rated<{ reduccion_promedio: number | null; pacientes_con_par: number; tasa_cruce_corte: number | null }>
  k4?: Rated<{ tasa_adherencia: number | null; paciente_semanas: number; cumplen: number }>
  k5?: Rated<{ promedio: number | null; pacientes: number; variacion: number | null; pacientes_con_variacion: number }>
  k6?: Rated<{ tiempo_promedio_minutos: number | null; con_respuesta: number; tasa_sin_respuesta: number | null }>
  k7?: Rated<{ reduccion_promedio: number | null; pacientes_comparables: number; turnos_comparados: number }>
  respuesta_mensual?: Monthly[]
}
type Comparison = { escenarios: Record<Scenario, Dashboard> }
type ScenarioSize = { escenario: Scenario; pacientes: number | null; incluidos: number | null }
type Metric = {
  id: string
  label: string
  value: number | null
  unit: string
  base: number
  baseLabel: string
  status: Status
  detail?: string
}

const integer = new Intl.NumberFormat('es-PE')
const decimals = new Intl.NumberFormat('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const signedDecimals = new Intl.NumberFormat('es-PE', {
  minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'exceptZero',
})
const stageLabel: Record<Status, string> = { verde: 'Verde', ambar: 'Ámbar', rojo: 'Rojo', sin_datos: 'Sin datos' }
const colors: Record<Scenario, string> = { HIBRIDO: '#12887c', SINTETICO_IA: '#6659b5' }
const initialFilters: Filters = { escenario: 'COMPARAR', poblacion: 'incluidos', desde: '2022-01-01', hasta: '2024-12-31' }

function number(value: number | null, unit = '') {
  return value === null ? '—' : decimals.format(value) + (unit ? ' ' + unit : '')
}

function metricList(report: Dashboard): Metric[] {
  const { k1, k2, k3, k4, k5, k6, k7 } = report
  const result: Metric[] = []
  if (k1) result.push({ id: 'K1', label: 'Experiencia positiva', value: k1.tasa_positiva, unit: '%',
    base: k1.participaciones_validas, baseLabel: 'participaciones valoradas', status: k1.estado })
  if (k2) result.push({ id: 'K2', label: 'Reducción de agitación · CMAI', value: k2.reduccion_promedio, unit: 'pts',
    base: k2.pacientes_con_par, baseLabel: 'pares válidos', status: k2.estado,
    detail: k2.tasa_respondedores === null ? undefined : number(k2.tasa_respondedores, '%') + ' respondió (≥6 pts)' })
  if (k3) result.push({ id: 'K3', label: 'Reducción de síntomas depresivos · CSDD', value: k3.reduccion_promedio, unit: 'pts',
    base: k3.pacientes_con_par, baseLabel: 'pares válidos', status: k3.estado,
    detail: k3.tasa_cruce_corte === null ? undefined : number(k3.tasa_cruce_corte, '%') + ' pasó de >10 a ≤10' })
  if (k4) result.push({ id: 'K4', label: 'Adherencia semanal', value: k4.tasa_adherencia, unit: '%',
    base: k4.paciente_semanas, baseLabel: 'paciente-semanas en intervención', status: k4.estado,
    detail: integer.format(k4.cumplen) + ' cumplieron la dosis' })
  if (k5) result.push({ id: 'K5', label: 'Último MMSE válido', value: k5.promedio, unit: 'pts',
    base: k5.pacientes, baseLabel: 'pacientes con MMSE', status: k5.estado,
    detail: k5.variacion === null ? undefined
      : signedDecimals.format(k5.variacion) + ' pts desde el primer MMSE · ' + integer.format(k5.pacientes_con_variacion) + ' pacientes' })
  if (k6) result.push({ id: 'K6', label: 'Tiempo hasta la primera respuesta positiva', value: k6.tiempo_promedio_minutos, unit: 'min',
    base: k6.con_respuesta, baseLabel: 'participaciones con latencia válida', status: k6.estado,
    detail: k6.tasa_sin_respuesta === null ? undefined : number(k6.tasa_sin_respuesta, '%') + ' sin respuesta confirmada' })
  if (k7) result.push({ id: 'K7', label: 'Reducción de episodios de agitación', value: k7.reduccion_promedio, unit: 'por turno',
    base: k7.pacientes_comparables, baseLabel: 'pacientes con dos trimestres', status: k7.estado,
    detail: integer.format(k7.turnos_comparados) + ' turnos válidos comparados' })
  return result
}

function MetricReading({ metric }: { metric: Metric }) {
  return <div className="indicator-reading">
    <div><strong>{number(metric.value)}</strong>{metric.value !== null && <small>{metric.unit}</small>}
      <span className={'indicator-status status-' + metric.status}>{stageLabel[metric.status]}</span></div>
    <p>{integer.format(metric.base)} {metric.baseLabel}</p>
    {metric.detail && <p>{metric.detail}</p>}
  </div>
}

function MetricComparison({ first, second }: { first: Metric[]; second: Metric[] }) {
  return <div className="panel indicator-table-wrap">
    <table className="indicator-table">
      <thead><tr><th scope="col">Indicador</th><th scope="col">Híbrido</th><th scope="col">Sintético IA</th>
        <th scope="col">Diferencia IA − híbrido</th></tr></thead>
      <tbody>{first.map(metric => {
        const other = second.find(item => item.id === metric.id)
        const delta = metric.value === null || other?.value == null ? null : other.value - metric.value
        const unit = metric.unit === '%' ? 'pp' : metric.unit
        return <tr key={metric.id}>
          <th scope="row"><span className="kpi-code">{metric.id}</span><span>{metric.label}</span></th>
          <td><MetricReading metric={metric} /></td>
          <td>{other && <MetricReading metric={other} />}</td>
          <td className="indicator-delta">{delta === null ? '—' : signedDecimals.format(delta) + ' ' + unit}</td>
        </tr>
      })}</tbody>
    </table>
  </div>
}

function Trend({ reports }: { reports: Dashboard[] }) {
  const container = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!container.current) return
    const chart = echarts.init(container.current)
    const observed = reports.flatMap(report => report.respuesta_mensual?.map(row => row.mes) ?? []).sort()
    const months: string[] = []
    if (observed.length) {
      const [fromYear, fromMonth] = observed[0].split('-').map(Number)
      const [toYear, toMonth] = observed[observed.length - 1].split('-').map(Number)
      for (let month = fromYear * 12 + fromMonth - 1; month <= toYear * 12 + toMonth - 1; month++) {
        months.push(String(Math.floor(month / 12)).padStart(4, '0') + '-' + String(month % 12 + 1).padStart(2, '0'))
      }
    }
    chart.setOption({
      grid: { left: 42, right: 14, top: 22, bottom: 34 },
      tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => typeof value === 'number' ? number(value, '%') : '—' },
      xAxis: { type: 'category', boundaryGap: false, data: months, axisLabel: { hideOverlap: true } },
      yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: '#edf1f4' } } },
      series: reports.map(report => {
        const scenario = report.filtros.escenario
        const data = new Map(report.respuesta_mensual?.map(row => [row.mes, row.tasa_positiva]))
        return { name: scenarioLabels[scenario], type: 'line', showSymbol: months.length <= 6,
          data: months.map(month => data.get(month) ?? null),
          lineStyle: { color: colors[scenario], width: 3 }, itemStyle: { color: colors[scenario] } }
      }),
    })
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(container.current)
    return () => { observer.disconnect(); chart.dispose() }
  }, [reports])
  return <div className="chart" ref={container} role="img" aria-label="Tendencia mensual de experiencias positivas por escenario" />
}

function ExperiencePanels({ reports }: { reports: Dashboard[] }) {
  return <div className="analysis-grid">
    <section className="panel">
      <div className="panel-heading"><h2>Experiencias positivas por mes</h2></div>
      <div className="indicator-legend">{reports.map(report => {
        const scenario = report.filtros.escenario
        return <span key={scenario}><i style={{ backgroundColor: colors[scenario] }} />{scenarioLabels[scenario]}</span>
      })}</div>
      {reports.some(report => report.respuesta_mensual?.length) ? <Trend reports={reports} />
        : <p className="empty-chart">Sin participaciones valoradas en el periodo.</p>}
    </section>
    <section className="panel">
      <div className="panel-heading"><h2>Distribución de experiencias</h2></div>
      {reports.map(({ filtros, k1 }) => {
        if (!k1) return null
        const portions = [
          { label: 'Positiva', value: k1.positivas, color: 'teal' },
          { label: 'Neutra', value: k1.neutras, color: 'gold' },
          { label: 'Negativa', value: k1.negativas, color: 'coral' },
        ]
        return <div className="indicator-composition" key={filtros.escenario}>
          <h3>{scenarioLabels[filtros.escenario]}</h3>
          <div className="stacked-bar" aria-hidden="true">{portions.map(item => <span key={item.label}
            className={item.color} style={{ width: (k1.participaciones_validas ? 100 * item.value / k1.participaciones_validas : 0) + '%' }} />)}</div>
          <div className="composition-list">{portions.map(item => <div key={item.label}><i className={'color-dot ' + item.color} />
            <span>{item.label}</span><strong>{integer.format(item.value)}</strong></div>)}</div>
        </div>
      })}
    </section>
  </div>
}

export default function DashboardPage() {
  const { user } = useSession()
  const [draft, setDraft] = useState<Filters>(initialFilters)
  const [applied, setApplied] = useState<Filters>(initialFilters)
  const dashboard = useOperationQuery<Dashboard | Comparison>('/api/tablero?' + new URLSearchParams(applied))
  const scenarioSizes = useOperationQuery<ScenarioSize[]>(user.alcance_datos === 'GLOBAL' ? '/api/escenarios' : null)
  const reports = useMemo(() => dashboard.data ? ('escenarios' in dashboard.data
    ? [dashboard.data.escenarios.HIBRIDO, dashboard.data.escenarios.SINTETICO_IA] : [dashboard.data]) : [], [dashboard.data])
  const metrics = reports.map(metricList)
  const invalidDates = draft.desde > draft.hasta

  return <div className="indicators">
    <div className="title-row"><div><h1>Indicadores de musicoterapia</h1>
      <p className="intro">Resultados de sesiones, evaluaciones y turnos para el periodo seleccionado.</p>
    </div></div>
    <form className="filter-card" onSubmit={event => { event.preventDefault(); if (!invalidDates) setApplied(draft) }}>
      <div className="filter-grid indicator-filters">
        <label>Escenario<select value={draft.escenario} onChange={event => setDraft({ ...draft, escenario: event.target.value as Filters['escenario'] })}>
          <option value="COMPARAR">Comparar escenarios</option>
          <option value="HIBRIDO">Híbrido</option><option value="SINTETICO_IA">Sintético IA</option>
        </select></label>
        <label>Población<select value={draft.poblacion} onChange={event => setDraft({ ...draft, poblacion: event.target.value as Population })}>
          <option value="incluidos">{populationLabels.incluidos}</option><option value="todos">{populationLabels.todos}</option>
        </select></label>
        <label>Desde<input type="date" value={draft.desde} max={draft.hasta} required
          onChange={event => setDraft({ ...draft, desde: event.target.value })} /></label>
        <label>Hasta<input type="date" value={draft.hasta} min={draft.desde} required
          onChange={event => setDraft({ ...draft, hasta: event.target.value })} /></label>
        <button className="apply-button" type="submit" disabled={invalidDates || dashboard.loading}>Aplicar filtros</button>
      </div>
      <div className="filter-note"><span className="note-dot" />
        {draft.poblacion === 'incluidos' ? 'Edad de 60 años o más en la primera visita, diagnóstico de Alzheimer y primer CDR válido entre 0,5 y 2.' : 'Incluye a todos los pacientes de los escenarios seleccionados.'}
      </div>
    </form>
    {dashboard.error && <div className="error-panel" role="alert"><span>{dashboard.error}</span>
      <button type="button" className="operation-secondary" onClick={dashboard.refresh}>Reintentar</button></div>}
    {dashboard.loading && <p className="operation-help indicator-loading" role="status">Consultando indicadores del Datamart…</p>}
    {!!reports.length && <>
      <div className="section-heading"><div><h2>{reports.length === 2 ? 'Comparación de escenarios' : scenarioLabels[reports[0].filtros.escenario]}</h2>
        <p className="intro">{populationLabels[applied.poblacion]} · {applied.desde} a {applied.hasta}</p>
      </div>{user.alcance_datos === 'PROPIOS' && <span className="subdued">Registros a tu cargo</span>}</div>
      <div className="indicator-populations">{reports.map(report => {
        const scenario = report.filtros.escenario
        const population = scenarioSizes.data?.find(item => item.escenario === scenario)
        const count = applied.poblacion === 'incluidos' ? population?.incluidos : population?.pacientes
        return count != null && <span key={scenario}>{scenarioLabels[scenario]} · {integer.format(count)} pacientes en la población</span>
      })}</div>
      {reports.some(report => report.datos_desactualizados) &&
        <p className="operation-help" role="status">Mostrando la última lectura disponible del Datamart.</p>}
      {metrics.length === 2 ? <MetricComparison first={metrics[0]} second={metrics[1]} />
        : <div className="kpi-grid indicator-cards">{metrics[0].map(metric => <article className="kpi-card" key={metric.id}>
          <span className="kpi-code">{metric.id}</span><h3>{metric.label}</h3><MetricReading metric={metric} />
        </article>)}</div>}
      {reports.some(report => report.k1) && <ExperiencePanels reports={reports} />}
      <section className="method-panel"><div><strong>Cómo leer los indicadores</strong>
        <p>Los colores siguen los umbrales orientativos del informe. Los resultados describen datos de prueba.</p>
        {reports[0].k2 && <p>K2 y K3 comparan el primer basal válido con el último seguimiento válido del periodo. K5 toma el último MMSE válido dentro de las fechas seleccionadas.</p>}
        {reports[0].k4 && <p>K4 incluye las semanas ISO que intersectan el periodo y exige al menos tres sesiones y 30 minutos acumulados por paciente.</p>}
        {reports[0].k7 && <p>K7 promedia, por paciente, la diferencia entre el primer y el último trimestre con turnos observados dentro del periodo.</p>}
      </div></section>
    </>}
  </div>
}
