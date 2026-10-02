import { Fragment, useEffect, useMemo } from 'react'
import L from 'leaflet'
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { AlertTriangle, MapPinOff } from 'lucide-react'
import 'leaflet/dist/leaflet.css'
import { Badge, EmptyState, ErrorState } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { fmtFechaHora, fmtHora, fmtNumero } from '../../lib/format'
import { useRecorrido } from '../../lib/queries'
import { COLOR_ENTREGA, TONO_ENTREGA } from './estados'
import { partirTraza } from './trazas'

// Pin numerado con el orden sugerido, del color del estado (sin imágenes: no depende de los assets de Leaflet)
const iconoParada = (orden, color) =>
  L.divIcon({
    className: '',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html: `<div style="width:28px;height:28px;border-radius:9999px;background:${color};border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.45);color:#fff;font:800 12px/24px system-ui,sans-serif;text-align:center">${orden}</div>`,
  })

const num = (v) => (v == null ? null : Number(v))
const par = (lat, lon) => (lat == null || lon == null ? null : [Number(lat), Number(lon)])

function Ajustar({ puntos }) {
  const map = useMap()
  useEffect(() => {
    if (puntos.length === 0) return
    if (puntos.length === 1) map.setView(puntos[0], 15)
    else map.fitBounds(puntos, { padding: [32, 32] })
  }, [map, puntos])
  return null
}

function Indicador({ label, value, hint, alerta }) {
  return (
    <div className={`card p-3 ${alerta ? 'ring-1 ring-red-300 dark:ring-red-800' : ''}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">{label}</p>
      <p className={`tabular mt-0.5 text-xl font-extrabold ${alerta ? 'text-red-600 dark:text-red-400' : ''}`}>{value}</p>
      {hint && <p className="text-xs text-stone-500">{hint}</p>}
    </div>
  )
}

export default function MapaRecorrido({ hojaId }) {
  const { data: m, isLoading, isError, error, refetch } = useRecorrido(hojaId)

  const origen = useMemo(() => (m?.origen ? par(m.origen.latitud, m.origen.longitud) : null), [m])
  const sugerida = useMemo(
    () => (m?.sugerida ?? []).map((p) => par(p.latitud, p.longitud)),
    [m],
  )
  const { tramos, huecos } = useMemo(() => partirTraza(m?.traza ?? [], m?.eventos ?? []), [m])
  const todos = useMemo(() => {
    if (!m) return []
    const lista = [...sugerida, ...m.traza.map((p) => [Number(p.latitud), Number(p.longitud)])]
    if (origen) lista.push(origen)
    m.entregas.forEach((e) => {
      const real = par(e.latitud, e.longitud)
      if (real) lista.push(real)
    })
    return lista.filter(Boolean)
  }, [m, sugerida, origen])

  if (isLoading) return <PantallaCarga />
  if (isError) return <ErrorState error={error} onRetry={refetch} />

  const ind = m.indicadores
  const camino = [...(origen ? [origen] : []), ...sugerida]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 2xl:grid-cols-5">
        <Indicador
          label="Distancia"
          value={ind.distancia_real_km != null ? `${fmtNumero(Number(ind.distancia_real_km).toFixed(1))} km` : '—'}
          hint={ind.distancia_sugerida_km != null ? `Sugerida ${fmtNumero(Number(ind.distancia_sugerida_km).toFixed(1))} km` : 'Real vs. sugerida'}
        />
        <Indicador label="Duración" value={ind.duracion_min != null ? `${Math.floor(ind.duracion_min / 60)} h ${ind.duracion_min % 60} min` : '—'} />
        <Indicador label="Fuera de orden" value={ind.entregas_fuera_de_orden} hint="Atendidas distinto al sugerido" />
        <Indicador label="Lejos del punto" value={ind.entregas_lejos} alerta={ind.entregas_lejos > 0} hint="Confirmadas a más de 300 m" />
        <Indicador label="Tramos sin traza" value={ind.tramos_sin_traza} alerta={ind.tramos_sin_traza > 0} hint="GPS sin señal o permiso" />
      </div>

      {todos.length === 0 ? (
        <div className="card">
          <EmptyState icon={MapPinOff} title="Sin ubicaciones para mostrar">
            Cargá la latitud y longitud de los puntos de entrega (Contabilidad → Puntos de entrega) para ver la ruta sugerida.
          </EmptyState>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <MapContainer center={todos[0]} zoom={13} scrollWheelZoom={false} className="z-0 h-[460px] w-full">
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <Ajustar puntos={todos} />

            {camino.length > 1 && (
              <Polyline positions={camino} pathOptions={{ color: '#0284c7', weight: 3, opacity: 0.8, dashArray: '8 8' }} />
            )}
            {tramos.map((t, i) => (
              <Polyline key={`t${i}`} positions={t} pathOptions={{ color: '#ea580c', weight: 4, opacity: 0.9 }} />
            ))}
            {huecos.map((h, i) => (
              <Polyline key={`h${i}`} positions={h} pathOptions={{ color: '#a8a29e', weight: 3, dashArray: '2 8' }} />
            ))}

            {origen && (
              <CircleMarker center={origen} radius={9} pathOptions={{ color: '#1c1917', fillColor: '#fbbf24', fillOpacity: 1, weight: 2 }}>
                <Tooltip>Panadería</Tooltip>
              </CircleMarker>
            )}

            {m.entregas.map((e) => {
              const punto = par(e.punto_latitud, e.punto_longitud)
              const real = par(e.latitud, e.longitud)
              return (
                <Fragment key={e.entrega_id}>
                  {punto && (
                    <Marker position={punto} icon={iconoParada(e.orden_sugerido, COLOR_ENTREGA[e.estado])}>
                      <Tooltip direction="top" offset={[0, -14]}>
                        <strong>{e.punto_nombre}</strong>
                        <br />
                        {e.estado}
                        {e.orden_real != null && ` · atendida ${e.orden_real}.ª`}
                        {e.hora && ` · ${fmtHora(e.hora)}`}
                        {e.distancia_al_punto_m != null && ` · a ${e.distancia_al_punto_m} m del punto`}
                      </Tooltip>
                    </Marker>
                  )}
                  {real && (
                    <CircleMarker
                      center={real}
                      radius={5}
                      pathOptions={{ color: e.lejos ? '#dc2626' : '#065f46', weight: 2, fillColor: e.lejos ? '#fecaca' : '#a7f3d0', fillOpacity: 1 }}
                    >
                      <Tooltip>Confirmada acá{e.lejos ? ' (lejos del punto)' : ''}</Tooltip>
                    </CircleMarker>
                  )}
                  {punto && real && e.lejos && (
                    <Polyline positions={[punto, real]} pathOptions={{ color: '#dc2626', weight: 2, dashArray: '4 4' }} />
                  )}
                </Fragment>
              )
            })}
          </MapContainer>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-stone-200 px-4 py-2 text-xs text-stone-500 dark:border-stone-800">
            <span className="flex items-center gap-1.5"><i className="inline-block h-0.5 w-5 border-t-2 border-dashed border-sky-600" /> Ruta sugerida</span>
            <span className="flex items-center gap-1.5"><i className="inline-block h-1 w-5 rounded bg-orange-600" /> Recorrido real</span>
            <span className="flex items-center gap-1.5"><i className="inline-block h-0.5 w-5 border-t-2 border-dotted border-stone-400" /> Sin traza</span>
            <span>{fmtNumero(m.puntos_totales)} puntos GPS</span>
          </div>
        </div>
      )}

      {m.eventos.length > 0 && (
        <div className="card p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-bold">
            <AlertTriangle className="h-4 w-4 text-amber-600" /> Cortes de la traza
          </h3>
          <ul className="space-y-1 text-sm">
            {m.eventos.map((ev, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2">
                <Badge tone="amber">{ev.tipo}</Badge>
                <span className="text-stone-500">
                  {fmtFechaHora(ev.desde)}
                  {ev.hasta ? ` → ${fmtHora(ev.hasta)}` : ' → sin cerrar'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-500 dark:border-stone-800">
            <tr>
              <th className="px-4 py-3 font-semibold">Sugerida</th>
              <th className="px-4 py-3 font-semibold">Punto</th>
              <th className="px-4 py-3 font-semibold">Estado</th>
              <th className="px-4 py-3 text-right font-semibold">Atendida</th>
              <th className="px-4 py-3 text-right font-semibold">Hora</th>
              <th className="px-4 py-3 text-right font-semibold">Distancia al punto</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
            {m.entregas.map((e) => (
              <tr key={e.entrega_id}>
                <td className="tabular px-4 py-3">{e.orden_sugerido}</td>
                <td className="px-4 py-3 font-semibold">{e.punto_nombre}</td>
                <td className="px-4 py-3">
                  <Badge tone={TONO_ENTREGA[e.estado]}>{e.estado}</Badge>
                </td>
                <td className="tabular px-4 py-3 text-right">{e.orden_real ?? '—'}</td>
                <td className="tabular px-4 py-3 text-right text-stone-500">{e.hora ? fmtHora(e.hora) : '—'}</td>
                <td className="tabular px-4 py-3 text-right">
                  {num(e.distancia_al_punto_m) == null ? (
                    '—'
                  ) : e.lejos ? (
                    <Badge tone="red">{fmtNumero(e.distancia_al_punto_m)} m · lejos</Badge>
                  ) : (
                    `${fmtNumero(e.distancia_al_punto_m)} m`
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
