import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowRight, CircleDot } from 'lucide-react'
import { Badge, ErrorState, PageHeader, Segmented } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { fmtDinero, fmtFechaHora, fmtNumero, isoLocal, sumarDias } from '../../lib/format'
import { useAlertas, useResumen, useTurnosAbiertos } from '../../lib/queries'
import { VentasDiariasChart } from './VentasDiariasChart'

const PERIODOS = [
  { value: 'hoy', label: 'Hoy', dias: 0 },
  { value: '7', label: '7 días', dias: 6 },
  { value: '30', label: '30 días', dias: 29 },
  { value: '90', label: '90 días', dias: 89 },
]

function Kpi({ label, value, hint, tone }) {
  const color = tone === 'neg' ? 'text-red-600 dark:text-red-400' : tone === 'pos' ? 'text-emerald-700 dark:text-emerald-400' : ''
  return (
    <div className="card p-4">
      <p className="text-sm text-stone-500">{label}</p>
      <p className={`mt-1 text-2xl font-extrabold tracking-tight ${color}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-stone-500">{hint}</p>}
    </div>
  )
}

function BarrasHorizontales({ filas, valor, etiqueta, detalle }) {
  const max = Math.max(...filas.map(valor), 0) || 1
  return (
    <ul className="space-y-3">
      {filas.map((f, i) => (
        <li key={i}>
          <div className="mb-1 flex justify-between gap-2 text-sm">
            <span className="truncate font-medium">{etiqueta(f)}</span>
            <span className="tabular shrink-0 text-stone-600 dark:text-stone-300">{detalle(f)}</span>
          </div>
          <div className="h-2 rounded-full bg-stone-100 dark:bg-stone-800">
            <div className="h-full rounded-full bg-brand-500 dark:bg-brand-400" style={{ width: `${(valor(f) / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

export default function DashboardPage() {
  const [periodo, setPeriodo] = useState('30')
  const hoy = new Date()
  const dias = PERIODOS.find((p) => p.value === periodo).dias
  const desde = isoLocal(sumarDias(hoy, -dias))
  const hasta = isoLocal(hoy)
  const { data: r, isLoading, isError, error, refetch, isFetching } = useResumen(desde, hasta)
  const alertas = useAlertas()
  const turnos = useTurnosAbiertos()

  const nAlertas = (alertas.data?.productos.length ?? 0) + (alertas.data?.materias_primas.length ?? 0)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Tablero"
        subtitle="Cómo viene el negocio."
        actions={<Segmented value={periodo} onChange={setPeriodo} options={PERIODOS} />}
      />

      {isLoading ? (
        <PantallaCarga />
      ) : isError ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : (
        <div className={`space-y-5 transition-opacity ${isFetching ? 'opacity-70' : ''}`}>
          {/* Cifra principal + KPIs */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="card p-5 sm:col-span-2 xl:row-span-2">
              <p className="text-sm text-stone-500">Ventas del período</p>
              <p className="mt-1 break-words text-4xl font-extrabold tracking-tight sm:text-5xl">{fmtDinero(r.ventas_totales)}</p>
              <p className="mt-2 text-sm text-stone-500">
                {r.cantidad_ventas} ventas · ticket promedio {fmtDinero(r.ticket_promedio)}
              </p>
            </div>
            <Kpi label="Compras de insumos" value={fmtDinero(r.compras_materias_primas)} />
            <Kpi label="Gastos operativos" value={fmtDinero(r.gastos_operativos)} />
            <Kpi
              label="Resultado"
              value={fmtDinero(r.resultado)}
              tone={r.resultado < 0 ? 'neg' : 'pos'}
              hint="Ventas − compras − gastos"
            />
            <Kpi
              label="Merma"
              value={`${fmtNumero(r.unidades_merma)} u`}
              hint={`${fmtDinero(r.merma_valorizada)} a precio de venta`}
            />
          </div>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
            <section className="card min-w-0 p-5 xl:col-span-2">
              <h2 className="font-bold">Ventas por día</h2>
              <p className="mb-3 text-sm text-stone-500">
                {desde === hasta ? 'Hoy' : `Del ${desde.split('-').reverse().join('/')} al ${hasta.split('-').reverse().join('/')}`}
              </p>
              <VentasDiariasChart datos={r.ventas_diarias} />
            </section>
            <section className="card p-5">
              <h2 className="mb-4 font-bold">Medios de pago</h2>
              {r.ventas_por_medio.length ? (
                <BarrasHorizontales
                  filas={r.ventas_por_medio}
                  valor={(f) => f.total}
                  etiqueta={(f) => f.metodo_pago}
                  detalle={(f) => `${fmtDinero(f.total)} · ${f.cantidad}`}
                />
              ) : (
                <p className="text-sm text-stone-500">Sin ventas en el período.</p>
              )}
            </section>
          </div>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
            <section className="card min-w-0 p-5">
              <h2 className="mb-4 font-bold">Ventas por canal</h2>
              {r.ventas_por_canal?.length ? (
                <BarrasHorizontales
                  filas={r.ventas_por_canal}
                  valor={(f) => f.total}
                  etiqueta={(f) => f.canal}
                  detalle={(f) => `${fmtDinero(f.total)} · ${f.cantidad}`}
                />
              ) : (
                <p className="text-sm text-stone-500">Sin ventas en el período.</p>
              )}
            </section>
            <section className="card min-w-0 p-5 xl:col-span-2">
              <h2 className="mb-4 font-bold">Productos más vendidos</h2>
              {r.top_productos.length ? (
                <BarrasHorizontales
                  filas={r.top_productos}
                  valor={(f) => f.total}
                  etiqueta={(f) => f.nombre}
                  detalle={(f) => `${fmtNumero(f.unidades)} u · ${fmtDinero(f.total)}`}
                />
              ) : (
                <p className="text-sm text-stone-500">Sin ventas en el período.</p>
              )}
            </section>

            <section className="card p-5">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="flex items-center gap-2 font-bold">
                  <AlertTriangle className="h-4 w-4 text-amber-600" /> Reponer
                </h2>
                <Link to="/stock" className="flex items-center gap-1 text-sm font-semibold text-brand-700 hover:underline dark:text-brand-300">
                  Stock <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
              {!nAlertas ? (
                <p className="text-sm text-stone-500">Todo en orden.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {alertas.data.productos.map((p) => (
                    <li key={`p${p.id}`} className="flex justify-between gap-2">
                      <span className="truncate">{p.nombre}</span>
                      <Badge tone="red">{p.stock_mostrador} u</Badge>
                    </li>
                  ))}
                  {alertas.data.materias_primas.map((m) => (
                    <li key={`m${m.id}`} className="flex justify-between gap-2">
                      <span className="truncate">{m.nombre}</span>
                      <Badge tone="red">
                        {fmtNumero(m.stock_actual)} {m.unidad_medida}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
              {turnos.data?.length > 0 && (
                <div className="mt-5 border-t border-stone-100 pt-4 dark:border-stone-800">
                  <h3 className="mb-2 text-sm font-semibold">Cajas abiertas</h3>
                  <ul className="space-y-1.5 text-sm">
                    {turnos.data.map((t) => (
                      <li key={t.id} className="flex items-center gap-2">
                        <CircleDot className="h-3.5 w-3.5 text-emerald-600" />
                        Turno #{t.id} · desde {fmtFechaHora(t.fecha_apertura)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          </div>
        </div>
      )}
    </div>
  )
}
