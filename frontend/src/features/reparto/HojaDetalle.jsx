import { Suspense, lazy, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Ban,
  CheckCheck,
  ClipboardCheck,
  PackageCheck,
  Pencil,
  Route,
  RotateCcw,
  Undo2,
} from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Badge, EmptyState, ErrorState, Segmented } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { fmtDinero, fmtFechaHora, fmtNumero } from '../../lib/format'
import { useHoja } from '../../lib/queries'
import CargaModal from './CargaModal'
import HojaFormModal from './HojaFormModal'
import RendicionModal from './RendicionModal'
import { TONO_ENTREGA, TONO_HOJA, ventana } from './estados'

// Leaflet pesa: se descarga solo al abrir la pestaña del mapa
const MapaRecorrido = lazy(() => import('./MapaRecorrido'))

const REFRESCAR = ['hojas', 'hoja', 'resumen-entregas', 'productos', 'recorrido', 'turnos-abiertos']

export default function HojaDetalle({ hojaId }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: hoja, isLoading, isError, error, refetch } = useHoja(hojaId)
  const [tab, setTab] = useState('paradas')
  const [modal, setModal] = useState(null) // 'editar' | 'carga' | 'rendicion'

  const accion = useMutation({
    mutationFn: ({ ruta }) => post(`/entregas/hojas/${hojaId}/${ruta}`),
    onSuccess: (_, { ok }) => {
      REFRESCAR.forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
      toast.ok(ok)
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const ejecutar = (ruta, ok, confirmar) => {
    if (confirmar && !window.confirm(confirmar)) return
    accion.mutate({ ruta, ok })
  }

  if (isLoading) return <PantallaCarga />
  if (isError) return <ErrorState error={error} onRetry={refetch} />

  const e = hoja.estado
  const pendientes = hoja.entregas.filter((x) => x.estado === 'Pendiente' || x.estado === 'En el local').length
  const ocupado = accion.isPending

  return (
    <div className="space-y-4">
      <div className="card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold">{hoja.repartidor}</h2>
              <Badge tone={TONO_HOJA[e]}>{e}</Badge>
            </div>
            <p className="mt-1 text-sm text-stone-500">
              Hoja #{hoja.id} · {hoja.fecha.split('-').reverse().join('/')} · {hoja.entregas.length}{' '}
              {hoja.entregas.length === 1 ? 'parada' : 'paradas'} · {fmtDinero(hoja.total_planificado)}
            </p>
            <p className="mt-0.5 text-xs text-stone-500">
              {hoja.distancia_sugerida_km != null && `Ruta sugerida ${Number(hoja.distancia_sugerida_km).toFixed(1)} km`}
              {hoja.distancia_real_km != null && ` · recorrido real ${Number(hoja.distancia_real_km).toFixed(1)} km`}
              {hoja.cargada_en && ` · cargada ${fmtFechaHora(hoja.cargada_en)}`}
              {hoja.iniciada_en && ` · salió ${fmtFechaHora(hoja.iniciada_en)}`}
              {hoja.rendida_en && ` · rendida ${fmtFechaHora(hoja.rendida_en)}`}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {e === 'Borrador' && (
              <>
                <Button variant="secondary" icon={Pencil} onClick={() => setModal('editar')}>
                  Editar
                </Button>
                <Button
                  icon={CheckCheck}
                  loading={ocupado}
                  onClick={() => ejecutar('confirmacion', 'Hoja confirmada: el stock quedó reservado.')}
                >
                  Confirmar y reservar stock
                </Button>
              </>
            )}
            {e === 'Confirmada' && (
              <>
                <Button icon={PackageCheck} onClick={() => setModal('carga')}>
                  Cargar vehículo
                </Button>
                <Button variant="secondary" icon={Undo2} loading={ocupado} onClick={() => ejecutar('reapertura', 'Hoja reabierta: se liberó el stock reservado.')}>
                  Reabrir
                </Button>
              </>
            )}
            {(e === 'Cargada' || e === 'En ruta') && (
              <Button icon={ClipboardCheck} onClick={() => setModal('rendicion')}>
                Rendir
              </Button>
            )}
            {(e === 'Borrador' || e === 'Confirmada') && (
              <Button variant="secondary" icon={RotateCcw} loading={ocupado} onClick={() => ejecutar('ruta-sugerida', 'Ruta sugerida recalculada.')}>
                Recalcular ruta
              </Button>
            )}
            {(e === 'Borrador' || e === 'Confirmada') && (
              <Button
                variant="ghost"
                icon={Ban}
                loading={ocupado}
                onClick={() =>
                  ejecutar(
                    'anulacion',
                    'Hoja anulada.',
                    e === 'Confirmada'
                      ? '¿Anular la hoja? Se libera el stock reservado.'
                      : '¿Anular la hoja en borrador?',
                  )
                }
              >
                Anular
              </Button>
            )}
          </div>
        </div>

        {e === 'Cargada' && (
          <p className="mt-3 rounded-xl bg-violet-50 px-3 py-2 text-sm text-violet-800 dark:bg-violet-950/40 dark:text-violet-200">
            Cargada. Falta que el repartidor salga a la ruta (necesita permitir la ubicación del dispositivo).
          </p>
        )}
      </div>

      <Segmented
        value={tab}
        onChange={setTab}
        options={[
          { value: 'paradas', label: 'Paradas', count: hoja.entregas.length },
          { value: 'carga', label: 'Carga', count: hoja.carga.length || null },
          { value: 'mapa', label: 'Mapa' },
        ]}
      />

      {tab === 'paradas' && <Paradas hoja={hoja} />}
      {tab === 'carga' && <Carga hoja={hoja} />}
      {tab === 'mapa' && (
        <Suspense fallback={<PantallaCarga />}>
          <MapaRecorrido hojaId={hoja.id} />
        </Suspense>
      )}

      {modal === 'editar' && (
        <HojaFormModal
          hoja={hoja}
          onClose={() => setModal(null)}
          onGuardada={() => setModal(null)}
        />
      )}
      {modal === 'carga' && <CargaModal hoja={hoja} onClose={() => setModal(null)} />}
      {modal === 'rendicion' && (
        <RendicionModal
          hoja={hoja}
          pendientes={pendientes}
          onClose={() => setModal(null)}
          onRendida={() => setModal(null)}
        />
      )}
    </div>
  )
}

function Paradas({ hoja }) {
  if (hoja.entregas.length === 0) {
    return (
      <div className="card">
        <EmptyState icon={Route} title="Sin paradas" />
      </div>
    )
  }
  return (
    <ol className="space-y-2">
      {hoja.entregas.map((x) => (
        <li key={x.id} className="card p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="flex min-w-0 items-start gap-3">
              <span className="tabular grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand-100 text-sm font-extrabold text-brand-800 dark:bg-brand-900/50 dark:text-brand-200">
                {x.orden_sugerido}
              </span>
              <div className="min-w-0">
                <p className="font-bold">{x.punto_nombre}</p>
                <p className="truncate text-sm text-stone-500">
                  {x.cliente_nombre}
                  {x.direccion && ` · ${x.direccion}`}
                </p>
                <p className="mt-0.5 text-xs text-stone-500">
                  {ventana(x) && `Recibe ${ventana(x)}`}
                  {x.contacto && `${ventana(x) ? ' · ' : ''}${x.contacto}`}
                  {!x.latitud && ' · sin ubicación cargada'}
                </p>
              </div>
            </div>
            <div className="text-right">
              <Badge tone={TONO_ENTREGA[x.estado]}>{x.estado}</Badge>
              {x.orden_real != null && (
                <p className="mt-1 text-xs text-stone-500">
                  Atendida {x.orden_real}.ª{x.orden_real !== x.orden_sugerido && ' (fuera de orden)'}
                </p>
              )}
            </div>
          </div>

          <ul className="mt-3 divide-y divide-stone-100 text-sm dark:divide-stone-800">
            {x.items.map((i) => (
              <li key={i.producto_id} className="flex items-center justify-between gap-3 py-1.5">
                <span className="min-w-0 truncate">
                  {i.nombre}
                  {i.descuento_pct != null && (
                    <span className="ml-2 text-xs font-semibold text-emerald-700 dark:text-emerald-400">
                      −{fmtNumero(i.descuento_pct)}%
                    </span>
                  )}
                </span>
                <span className="tabular shrink-0 text-stone-600 dark:text-stone-300">
                  {x.estado === 'Pendiente' || x.estado === 'En el local'
                    ? `${i.cantidad_planificada} u`
                    : `${i.cantidad_entregada}/${i.cantidad_planificada} u`}{' '}
                  × {fmtDinero(i.precio_unitario)}
                </span>
              </li>
            ))}
          </ul>

          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-stone-100 pt-2 text-sm dark:border-stone-800">
            <span className="text-stone-500">
              {x.numero_remito != null && `Remito ${String(x.numero_remito).padStart(6, '0')}`}
              {x.motivo_no_entrega && `Motivo: ${x.motivo_no_entrega}`}
            </span>
            <span className="tabular font-semibold">
              {fmtDinero(x.total)}
              {x.numero_remito != null && Number(x.cobrado) < Number(x.total) && (
                <span className="ml-2 text-xs font-medium text-amber-700 dark:text-amber-400">
                  cobrado {fmtDinero(x.cobrado)} · a cuenta {fmtDinero(Number(x.total) - Number(x.cobrado))}
                </span>
              )}
            </span>
          </div>
        </li>
      ))}
    </ol>
  )
}

function Carga({ hoja }) {
  if (hoja.carga.length === 0) {
    return (
      <div className="card">
        <EmptyState icon={PackageCheck} title="Todavía no hay carga">
          Al confirmar la hoja se reserva el stock y acá aparece lo que hay que cargar.
        </EmptyState>
      </div>
    )
  }
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[480px] text-sm">
        <thead className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-500 dark:border-stone-800">
          <tr>
            <th className="px-4 py-3 font-semibold">Producto</th>
            <th className="px-4 py-3 text-right font-semibold">Reservado</th>
            <th className="px-4 py-3 text-right font-semibold">Cargado</th>
            <th className="px-4 py-3 text-right font-semibold">Entregado</th>
            <th className="px-4 py-3 text-right font-semibold">Devuelto</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
          {hoja.carga.map((c) => (
            <tr key={c.producto_id}>
              <td className="px-4 py-3 font-semibold">{c.nombre}</td>
              <td className="tabular px-4 py-3 text-right">{c.reservada}</td>
              <td className="tabular px-4 py-3 text-right">{c.cargada}</td>
              <td className="tabular px-4 py-3 text-right">{c.entregada}</td>
              <td className="tabular px-4 py-3 text-right">{c.devuelta}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
