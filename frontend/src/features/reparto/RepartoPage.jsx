import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, MapPinned, Plus, Route, Sparkles, Truck } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Badge, EmptyState, ErrorState, PageHeader } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { fmtDinero, isoLocal, sumarDias } from '../../lib/format'
import { useHojas, useResumenEntregas } from '../../lib/queries'
import HojaDetalle from './HojaDetalle'
import HojaFormModal from './HojaFormModal'
import { TONO_HOJA } from './estados'

function Kpi({ label, value, hint, tone }) {
  const color = tone === 'warn' ? 'text-amber-700 dark:text-amber-400' : ''
  return (
    <div className="card p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">{label}</p>
      <p className={`tabular mt-1 text-2xl font-extrabold ${color}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-stone-500">{hint}</p>}
    </div>
  )
}

export default function RepartoPage() {
  const toast = useToast()
  const qc = useQueryClient()
  const [fecha, setFecha] = useState(isoLocal())
  const [seleccionada, setSeleccionada] = useState(null)
  const [formulario, setFormulario] = useState(false)
  const [omitidos, setOmitidos] = useState(null)
  const hojas = useHojas(fecha)
  const resumen = useResumenEntregas(fecha)

  const generar = useMutation({
    mutationFn: () => post(`/entregas/hojas/generacion?fecha=${fecha}`),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['hojas'] })
      qc.invalidateQueries({ queryKey: ['resumen-entregas'] })
      if (r.hojas.length) {
        toast.ok(`${r.hojas.length} ${r.hojas.length === 1 ? 'hoja generada' : 'hojas generadas'} como borrador.`)
        setSeleccionada(r.hojas[0].id)
      } else {
        toast.info('No hay nada nuevo para generar en esa fecha.')
      }
      if (r.omitidos.length) setOmitidos(r.omitidos)
    },
    onError: (e) => toast.error(mensajeError(e)),
  })

  const r = resumen.data
  const lista = hojas.data ?? []

  return (
    <div>
      <PageHeader
        title="Reparto"
        subtitle="Armá las hojas de ruta, cargá el vehículo y controlá el recorrido y la rendición."
        actions={
          <>
            <div className="flex items-center gap-1">
              <Button variant="secondary" size="icon" aria-label="Día anterior" onClick={() => setFecha(isoLocal(sumarDias(new Date(`${fecha}T12:00:00`), -1)))}>
                ‹
              </Button>
              <div className="relative">
                <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
                <Input type="date" className="w-44 pl-9" value={fecha} onChange={(e) => e.target.value && setFecha(e.target.value)} aria-label="Fecha" />
              </div>
              <Button variant="secondary" size="icon" aria-label="Día siguiente" onClick={() => setFecha(isoLocal(sumarDias(new Date(`${fecha}T12:00:00`), 1)))}>
                ›
              </Button>
            </div>
            <Button variant="secondary" icon={Sparkles} loading={generar.isPending} onClick={() => generar.mutate()}>
              Generar desde plantillas
            </Button>
            <Button icon={Plus} onClick={() => setFormulario(true)}>
              Nueva hoja
            </Button>
          </>
        }
      />

      {r && (
        <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Kpi label="Paradas" value={r.paradas} hint={`${r.hojas} ${r.hojas === 1 ? 'hoja' : 'hojas'}`} />
          <Kpi
            label="Resueltas"
            value={r.completadas + r.parciales + r.no_entregadas}
            hint={`${r.completadas} completas · ${r.parciales} parciales · ${r.no_entregadas} no entregadas`}
          />
          <Kpi label="Pendientes" value={r.pendientes} tone={r.pendientes ? 'warn' : undefined} />
          <Kpi
            label="Facturado en reparto"
            value={fmtDinero(r.facturacion_reparto)}
            hint={`${fmtDinero(r.cobrado)} cobrado · ${fmtDinero(r.a_cuenta_corriente)} a cuenta`}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <section className="min-w-0">
          {hojas.isLoading ? (
            <PantallaCarga />
          ) : hojas.isError ? (
            <ErrorState error={hojas.error} onRetry={hojas.refetch} />
          ) : lista.length === 0 ? (
            <div className="card">
              <EmptyState icon={Truck} title="No hay hojas de ruta para esta fecha">
                Generalas desde las plantillas de los puntos de entrega o armá una a mano.
              </EmptyState>
            </div>
          ) : (
            <ul className="space-y-2">
              {lista.map((h) => (
                <li key={h.id}>
                  <button
                    onClick={() => setSeleccionada(h.id)}
                    className={`card w-full p-4 text-left transition hover:shadow-md ${
                      seleccionada === h.id ? 'ring-2 ring-brand-400' : ''
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate font-bold">{h.repartidor}</p>
                      <Badge tone={TONO_HOJA[h.estado]}>{h.estado}</Badge>
                    </div>
                    <p className="mt-1 text-sm text-stone-500">
                      {h.entregadas}/{h.paradas} paradas resueltas
                      {h.distancia_sugerida_km != null && ` · ${Number(h.distancia_sugerida_km).toFixed(1)} km`}
                    </p>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-800">
                      <div
                        className="h-full rounded-full bg-emerald-500"
                        style={{ width: `${h.paradas ? (h.entregadas / h.paradas) * 100 : 0}%` }}
                      />
                    </div>
                    <p className="tabular mt-2 text-sm font-semibold">{fmtDinero(h.total_planificado)}</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="min-w-0">
          {seleccionada ? (
            <HojaDetalle key={seleccionada} hojaId={seleccionada} />
          ) : (
            <div className="card">
              <EmptyState icon={Route} title="Elegí una hoja">
                Vas a ver sus paradas, la carga del vehículo y el mapa del recorrido.
              </EmptyState>
            </div>
          )}
        </section>
      </div>

      {formulario && (
        <HojaFormModal
          fechaInicial={fecha}
          onClose={() => setFormulario(false)}
          onGuardada={(h) => {
            setFormulario(false)
            if (h.fecha === fecha) setSeleccionada(h.id)
            else setFecha(h.fecha)
          }}
        />
      )}

      <Modal
        open={!!omitidos}
        onClose={() => setOmitidos(null)}
        title="Puntos que no se incluyeron"
        description="Revisalos para armarlos a mano o completar sus datos."
        footer={<Button onClick={() => setOmitidos(null)}>Entendido</Button>}
      >
        <ul className="divide-y divide-stone-100 dark:divide-stone-800">
          {(omitidos ?? []).map((o) => (
            <li key={o.punto} className="flex items-start gap-3 py-2.5">
              <MapPinned className="mt-0.5 h-4 w-4 shrink-0 text-stone-400" />
              <div>
                <p className="font-semibold">{o.punto}</p>
                <p className="text-sm text-stone-500">{o.motivo}</p>
              </div>
            </li>
          ))}
        </ul>
      </Modal>
    </div>
  )
}
