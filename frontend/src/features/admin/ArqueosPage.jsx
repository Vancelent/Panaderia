import { Receipt } from 'lucide-react'
import { Badge, EmptyState, ErrorState, PageHeader } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { fmtDinero, fmtFechaHora } from '../../lib/format'
import { useArqueos } from '../../lib/queries'

function Diferencia({ valor }) {
  if (Math.abs(valor) < 0.005) return <Badge tone="green">Cuadra</Badge>
  return <Badge tone={valor < 0 ? 'red' : 'amber'}>{valor < 0 ? 'Falta ' : 'Sobra '}{fmtDinero(Math.abs(valor))}</Badge>
}

export default function ArqueosPage() {
  const { data, isLoading, isError, error, refetch } = useArqueos()
  return (
    <div>
      <PageHeader
        title="Arqueos de caja"
        subtitle="Cierres ciegos: el cajero declara lo contado y el sistema calcula la diferencia contra el efectivo esperado."
      />
      {isLoading ? (
        <PantallaCarga />
      ) : isError ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : !data.length ? (
        <div className="card">
          <EmptyState icon={Receipt} title="Todavía no hay turnos cerrados" />
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-500 dark:border-stone-800">
              <tr>
                <th className="px-4 py-3 font-semibold">Turno</th>
                <th className="px-4 py-3 font-semibold">Cajero/a</th>
                <th className="px-4 py-3 font-semibold">Cierre</th>
                <th className="px-4 py-3 text-right font-semibold">Fondo</th>
                <th className="px-4 py-3 text-right font-semibold">Ventas efvo.</th>
                <th className="px-4 py-3 text-right font-semibold">Otros medios</th>
                <th className="px-4 py-3 text-right font-semibold">Esperado</th>
                <th className="px-4 py-3 text-right font-semibold">Declarado</th>
                <th className="px-4 py-3 text-right font-semibold">Diferencia</th>
              </tr>
            </thead>
            <tbody className="tabular divide-y divide-stone-100 dark:divide-stone-800">
              {data.map((a) => (
                <tr key={a.id} className="hover:bg-stone-50 dark:hover:bg-stone-800/40">
                  <td className="px-4 py-3 font-semibold">#{a.turno_id}</td>
                  <td className="px-4 py-3">{a.usuario}</td>
                  <td className="px-4 py-3 text-stone-500">{a.fecha_cierre ? fmtFechaHora(a.fecha_cierre) : '—'}</td>
                  <td className="px-4 py-3 text-right">{fmtDinero(a.efectivo_inicial)}</td>
                  <td className="px-4 py-3 text-right">{a.ventas_efectivo != null ? fmtDinero(a.ventas_efectivo) : '—'}</td>
                  <td className="px-4 py-3 text-right">{a.ventas_otros_medios != null ? fmtDinero(a.ventas_otros_medios) : '—'}</td>
                  <td className="px-4 py-3 text-right font-semibold">{fmtDinero(a.monto_sistema)}</td>
                  <td className="px-4 py-3 text-right">{fmtDinero(a.monto_declarado)}</td>
                  <td className="px-4 py-3 text-right">
                    <Diferencia valor={a.diferencia} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
