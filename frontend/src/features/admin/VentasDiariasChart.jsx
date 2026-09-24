import { useMemo, useState } from 'react'
import { fmtDinero, fmtDineroCorto } from '../../lib/format'

/** Escala "linda" para el eje Y: 0, 25k, 50k… */
function ticksLindos(max, n = 4) {
  if (max <= 0) return [0, 1]
  const paso0 = max / n
  const mag = 10 ** Math.floor(Math.log10(paso0))
  const paso = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((p) => p >= paso0)
  const tope = Math.ceil(max / paso) * paso
  return Array.from({ length: Math.round(tope / paso) + 1 }, (_, i) => i * paso)
}

const fechaCorta = (iso) => {
  const [, m, d] = iso.split('-')
  return `${d}/${m}`
}
const fechaLarga = (iso) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long' })

/** Columnas de una sola serie (ventas por día) con tooltip por columna. */
export function VentasDiariasChart({ datos }) {
  const [activo, setActivo] = useState(null)
  const [tabla, setTabla] = useState(false)
  const ticks = useMemo(() => ticksLindos(Math.max(...datos.map((d) => d.total), 0)), [datos])
  const tope = ticks[ticks.length - 1]
  const H = 200
  // Cada cuántas columnas mostrar la fecha en el eje X
  const cadaN = Math.ceil(datos.length / 6)

  return (
    <div>
      <div className="mb-2 flex justify-end">
        <button onClick={() => setTabla((t) => !t)} className="text-xs font-semibold text-stone-500 hover:text-stone-900 dark:hover:text-white">
          {tabla ? 'Ver gráfico' : 'Ver tabla'}
        </button>
      </div>
      {tabla ? (
        <div className="max-h-[260px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white text-left text-xs text-stone-500 dark:bg-stone-900">
              <tr>
                <th className="py-1 font-medium">Día</th>
                <th className="py-1 text-right font-medium">Ventas</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {datos.map((d) => (
                <tr key={d.fecha} className="border-t border-stone-100 dark:border-stone-800">
                  <td className="py-1.5 first-letter:uppercase">{fechaLarga(d.fecha)}</td>
                  <td className="py-1.5 text-right">{fmtDinero(d.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex gap-2">
          {/* Eje Y */}
          <div className="relative w-12 shrink-0 text-right text-[11px] text-stone-500" style={{ height: H }}>
            {ticks.map((t) => (
              <span key={t} className="tabular absolute right-0 -translate-y-1/2" style={{ top: H - (t / tope) * H }}>
                {fmtDineroCorto(t)}
              </span>
            ))}
          </div>
          <div className="relative min-w-0 flex-1">
            {/* Grilla: líneas finas y recesivas */}
            <div className="absolute inset-x-0 top-0" style={{ height: H }} aria-hidden>
              {ticks.map((t) => (
                <div
                  key={t}
                  className="absolute inset-x-0 border-t border-stone-200 dark:border-stone-800"
                  style={{ top: H - (t / tope) * H }}
                />
              ))}
            </div>
            <div
              className="relative flex items-end"
              style={{ height: H }}
              role="list"
              aria-label="Ventas por día"
              onMouseLeave={() => setActivo(null)}
            >
              {datos.map((d, i) => {
                const h = tope ? (d.total / tope) * H : 0
                const on = activo === i
                return (
                  <div
                    key={d.fecha}
                    role="listitem"
                    tabIndex={0}
                    aria-label={`${fechaLarga(d.fecha)}: ${fmtDinero(d.total)}`}
                    onMouseEnter={() => setActivo(i)}
                    onFocus={() => setActivo(i)}
                    onBlur={() => setActivo(null)}
                    className="group relative flex h-full flex-1 cursor-default items-end justify-center outline-none"
                  >
                    {/* Zona de hover más grande que la columna */}
                    <div
                      className={`w-full max-w-[24px] rounded-t transition-colors ${
                        on ? 'bg-brand-700 dark:bg-brand-300' : 'bg-brand-500 dark:bg-brand-400'
                      } ${d.total === 0 ? 'opacity-0' : ''}`}
                      style={{ height: Math.max(h, d.total > 0 ? 2 : 0), marginInline: 1 }}
                    />
                    {on && (
                      <div
                        className={`pointer-events-none absolute z-10 whitespace-nowrap rounded-xl border border-stone-200 bg-white px-3 py-2 text-left shadow-lg dark:border-stone-700 dark:bg-stone-900 ${
                          i > datos.length / 2 ? 'right-1/2' : 'left-1/2'
                        }`}
                        style={{ bottom: Math.min(h + 8, H - 40) }}
                      >
                        <p className="tabular text-sm font-bold">{fmtDinero(d.total)}</p>
                        <p className="text-xs text-stone-500 first-letter:uppercase">{fechaLarga(d.fecha)}</p>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            {/* Eje X */}
            <div className="mt-1.5 flex text-[11px] text-stone-500" aria-hidden>
              {datos.map((d, i) => (
                <span key={d.fecha} className="w-0 flex-1 whitespace-nowrap text-center">
                  {i % cadaN === 0 ? fechaCorta(d.fecha) : ''}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
