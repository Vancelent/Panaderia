import { useQuery } from '@tanstack/react-query'
import { Smartphone, Truck } from 'lucide-react'
import { Badge, EmptyState, ErrorState, PageHeader } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { get } from '../../lib/api'
import { fmtDinero } from '../../lib/format'
import { TONO_ENTREGA, TONO_HOJA, ventana } from './estados'

/**
 * Vista del repartidor en la web: solo lectura. Las entregas, el cobro y el registro del recorrido se
 * hacen desde la aplicación del celular (fase siguiente del proyecto).
 */
export default function MiRutaPage() {
  const { data: hoja, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['hoja', 'hoy'],
    queryFn: () => get('/entregas/hojas/hoy'),
    retry: false,
    refetchInterval: 30_000,
  })
  const sinHoja = isError && error?.response?.data?.error?.code === 'sin_hoja'

  return (
    <div>
      <PageHeader title="Mi ruta" subtitle="Tu hoja de reparto de hoy." />

      <div className="mb-4 flex items-start gap-3 rounded-2xl bg-sky-50 p-4 text-sm text-sky-900 dark:bg-sky-950/40 dark:text-sky-100">
        <Smartphone className="mt-0.5 h-5 w-5 shrink-0" />
        <p>
          Las entregas y los cobros se registran desde la aplicación del celular. Desde acá solo podés consultar tu hoja.
        </p>
      </div>

      {isLoading ? (
        <PantallaCarga />
      ) : sinHoja ? (
        <div className="card">
          <EmptyState icon={Truck} title="No tenés una hoja de ruta para hoy">
            Cuando la gestión confirme tu hoja, la vas a ver acá.
          </EmptyState>
        </div>
      ) : isError ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Badge tone={TONO_HOJA[hoja.estado]}>{hoja.estado}</Badge>
            <span className="text-sm text-stone-500">
              {hoja.entregas.length} paradas · {fmtDinero(hoja.total_planificado)}
            </span>
          </div>
          <ol className="space-y-2">
            {hoja.entregas.map((e) => (
              <li key={e.id} className="card p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-bold">
                      {e.orden_sugerido}. {e.punto_nombre}
                    </p>
                    <p className="text-sm text-stone-500">
                      {e.direccion}
                      {ventana(e) && ` · recibe ${ventana(e)}`}
                    </p>
                  </div>
                  <Badge tone={TONO_ENTREGA[e.estado]}>{e.estado}</Badge>
                </div>
                <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
                  {e.items.map((i) => `${i.cantidad_planificada} ${i.nombre}`).join(' · ')}
                </p>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}
