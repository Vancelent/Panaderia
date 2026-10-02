import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { MapPin, Plus, Trash2 } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Field, Input, Select } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Stepper } from '../../components/ui/misc'
import { useToast } from '../../components/ui/toast'
import { get, mensajeError, patch, post } from '../../lib/api'
import { isoLocal } from '../../lib/format'
import { useProductos, usePuntosEntrega, useRepartidores } from '../../lib/queries'
import { diaSemana } from './estados'

const parada = () => ({ punto_entrega_id: '', items: [{ producto_id: '', cantidad: 1 }] })

/** Alta o edición (solo borrador) de una hoja de ruta. */
export default function HojaFormModal({ hoja, fechaInicial, onClose, onGuardada }) {
  const toast = useToast()
  const qc = useQueryClient()
  const repartidores = useRepartidores()
  const puntos = usePuntosEntrega()
  const productos = useProductos()

  const [fecha, setFecha] = useState(hoja?.fecha ?? fechaInicial ?? isoLocal())
  const [repartidor, setRepartidor] = useState(hoja ? String(hoja.repartidor_id) : '')
  const [paradas, setParadas] = useState(
    hoja
      ? hoja.entregas.map((e) => ({
          punto_entrega_id: String(e.punto_entrega_id),
          items: e.items.map((i) => ({ producto_id: String(i.producto_id), cantidad: i.cantidad_planificada })),
        }))
      : [parada()],
  )

  const activos = (productos.data ?? []).filter((p) => p.activo)
  const usados = new Set(paradas.map((p) => p.punto_entrega_id).filter(Boolean))

  const cambiarParada = (idx, cambio) =>
    setParadas((ps) => ps.map((p, i) => (i === idx ? { ...p, ...cambio } : p)))
  const cambiarItem = (idx, j, cambio) =>
    setParadas((ps) =>
      ps.map((p, i) =>
        i === idx ? { ...p, items: p.items.map((it, k) => (k === j ? { ...it, ...cambio } : it)) } : p,
      ),
    )

  // Al elegir un punto se propone su pedido fijo del día de la semana de la hoja
  const elegirPunto = async (idx, id) => {
    cambiarParada(idx, { punto_entrega_id: id })
    if (!id) return
    try {
      const plantillas = await get(`/contabilidad/puntos-entrega/${id}/plantillas`)
      const dia = plantillas.find((p) => p.dia_semana === diaSemana(fecha))
      if (dia) {
        setParadas((ps) =>
          ps.map((p, i) =>
            i === idx && p.items.every((it) => !it.producto_id)
              ? { ...p, items: dia.items.map((it) => ({ producto_id: String(it.producto_id), cantidad: it.cantidad })) }
              : p,
          ),
        )
      }
    } catch {
      // Sin plantilla se carga a mano
    }
  }

  const cuerpo = () => ({
    fecha,
    repartidor_id: Number(repartidor),
    paradas: paradas.map((p) => ({
      punto_entrega_id: Number(p.punto_entrega_id),
      items: p.items
        .filter((it) => it.producto_id && it.cantidad > 0)
        .map((it) => ({ producto_id: Number(it.producto_id), cantidad: it.cantidad })),
    })),
  })

  const guardar = useMutation({
    mutationFn: () => (hoja ? patch(`/entregas/hojas/${hoja.id}`, cuerpo()) : post('/entregas/hojas', cuerpo())),
    onSuccess: (h) => {
      ;['hojas', 'hoja', 'resumen-entregas'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
      toast.ok(hoja ? 'Hoja actualizada.' : 'Hoja creada como borrador.')
      onGuardada(h)
    },
    onError: (e) => toast.error(mensajeError(e)),
  })

  const valido =
    repartidor &&
    paradas.length > 0 &&
    paradas.every(
      (p) => p.punto_entrega_id && p.items.some((it) => it.producto_id && it.cantidad > 0),
    )

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={hoja ? `Editar hoja #${hoja.id}` : 'Nueva hoja de ruta'}
      description="Se guarda como borrador: el stock se reserva recién al confirmarla."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button disabled={!valido} loading={guardar.isPending} onClick={() => guardar.mutate()}>
            {hoja ? 'Guardar cambios' : 'Crear hoja'}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Fecha">
          {(id) => <Input id={id} type="date" value={fecha} onChange={(e) => e.target.value && setFecha(e.target.value)} />}
        </Field>
        <Field label="Repartidor">
          {(id) => (
            <Select id={id} value={repartidor} onChange={(e) => setRepartidor(e.target.value)}>
              <option value="">Elegí…</option>
              {(repartidores.data ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.nombre || r.username}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      {repartidores.data?.length === 0 && (
        <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">
          No hay usuarios con rol Repartidor. Crealos en Usuarios.
        </p>
      )}

      <div className="mt-5 space-y-3">
        {paradas.map((p, idx) => (
          <div key={idx} className="rounded-2xl border border-stone-200 p-3 dark:border-stone-800">
            <div className="flex items-center gap-2">
              <MapPin className="h-4 w-4 shrink-0 text-stone-400" />
              <Select
                value={p.punto_entrega_id}
                onChange={(e) => elegirPunto(idx, e.target.value)}
                aria-label={`Punto de entrega de la parada ${idx + 1}`}
              >
                <option value="">Punto de entrega…</option>
                {(puntos.data ?? []).map((pt) => (
                  <option key={pt.id} value={pt.id} disabled={usados.has(String(pt.id)) && p.punto_entrega_id !== String(pt.id)}>
                    {pt.nombre} — {pt.cliente_nombre}
                  </option>
                ))}
              </Select>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Quitar parada"
                disabled={paradas.length === 1}
                onClick={() => setParadas((ps) => ps.filter((_, i) => i !== idx))}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>

            <ul className="mt-3 space-y-2">
              {p.items.map((it, j) => (
                <li key={j} className="flex items-center gap-2">
                  <Select
                    value={it.producto_id}
                    onChange={(e) => cambiarItem(idx, j, { producto_id: e.target.value })}
                    aria-label="Producto"
                  >
                    <option value="">Producto…</option>
                    {activos.map((pr) => (
                      <option
                        key={pr.id}
                        value={pr.id}
                        disabled={p.items.some((o, k) => k !== j && o.producto_id === String(pr.id))}
                      >
                        {pr.nombre}
                      </option>
                    ))}
                  </Select>
                  <Stepper value={it.cantidad} min={1} max={100000} onChange={(n) => cambiarItem(idx, j, { cantidad: n })} />
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Quitar producto"
                    disabled={p.items.length === 1}
                    onClick={() => cambiarParada(idx, { items: p.items.filter((_, k) => k !== j) })}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </li>
              ))}
            </ul>
            <Button
              variant="ghost"
              size="sm"
              icon={Plus}
              className="mt-2"
              onClick={() => cambiarParada(idx, { items: [...p.items, { producto_id: '', cantidad: 1 }] })}
            >
              Agregar producto
            </Button>
          </div>
        ))}
        <Button variant="secondary" icon={Plus} onClick={() => setParadas((ps) => [...ps, parada()])}>
          Agregar parada
        </Button>
      </div>
    </Modal>
  )
}
