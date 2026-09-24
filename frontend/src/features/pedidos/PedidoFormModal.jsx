import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2, UserPlus, UserRound } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Field, Input, Select, Textarea } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Segmented, Stepper } from '../../components/ui/misc'
import { useToast } from '../../components/ui/toast'
import { mensajeError, patch, post } from '../../lib/api'
import { fmtDinero, isoLocal, sumarDias } from '../../lib/format'
import { useClientes, useProductos } from '../../lib/queries'

function horaLocal(iso) {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function PedidoFormModal({ pedido, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const editando = !!pedido
  const { data: productos = [] } = useProductos()

  const [modoCliente, setModoCliente] = useState(pedido?.cliente_id ? 'registrado' : 'contacto')
  const [buscar, setBuscar] = useState('')
  const { data: clientes = [] } = useClientes(modoCliente === 'registrado' ? buscar : null)
  const [clienteSel, setClienteSel] = useState(null)
  const [contacto, setContacto] = useState(pedido?.contacto ?? '')
  const [fecha, setFecha] = useState(pedido ? isoLocal(new Date(pedido.fecha_entrega)) : isoLocal(sumarDias(new Date(), 1)))
  const [hora, setHora] = useState(pedido ? horaLocal(pedido.fecha_entrega) : '09:00')
  const [notas, setNotas] = useState(pedido?.notas ?? '')
  const [items, setItems] = useState(
    () => Object.fromEntries((pedido?.detalles ?? []).map((d) => [d.producto_id, d.cantidad])),
  )
  const [agregarId, setAgregarId] = useState('')

  const porId = useMemo(() => Object.fromEntries(productos.map((p) => [p.id, p])), [productos])
  const lineas = Object.entries(items).filter(([id]) => porId[id])
  const total = lineas.reduce((t, [id, c]) => t + porId[id].precio_venta * c, 0)

  const guardar = useMutation({
    mutationFn: () => {
      const body = {
        fecha_entrega: new Date(`${fecha}T${hora}`).toISOString(),
        notas: notas.trim() || null,
        items: lineas.map(([id, cantidad]) => ({ producto_id: Number(id), cantidad })),
      }
      if (editando) return patch(`/pedidos/${pedido.id}`, { ...body, contacto: contacto.trim() || null })
      return post('/pedidos', {
        ...body,
        cliente_id: modoCliente === 'registrado' ? clienteSel?.id : null,
        contacto: modoCliente === 'contacto' ? contacto.trim() : null,
      })
    },
    onSuccess: (p) => {
      toast.ok(editando ? `Pedido #${p.id} actualizado.` : `Pedido #${p.id} creado.`)
      qc.invalidateQueries({ queryKey: ['pedidos'] })
      qc.invalidateQueries({ queryKey: ['pendiente-produccion'] })
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })

  const quienOk = editando || (modoCliente === 'registrado' ? !!clienteSel : contacto.trim().length > 0)
  const valido = quienOk && lineas.length > 0 && fecha && hora

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={editando ? `Editar pedido #${pedido.id}` : 'Nuevo pedido'}
      footer={
        <>
          <span className="mr-auto self-center text-sm text-stone-500">
            Total <strong className="tabular text-base text-stone-900 dark:text-white">{fmtDinero(total)}</strong>
          </span>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button loading={guardar.isPending} disabled={!valido} onClick={() => guardar.mutate()}>
            {editando ? 'Guardar cambios' : 'Crear pedido'}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {!editando && (
          <div>
            <Segmented
              className="mb-3"
              value={modoCliente}
              onChange={setModoCliente}
              options={[
                { value: 'contacto', label: 'Nombre y teléfono' },
                { value: 'registrado', label: 'Cliente registrado' },
              ]}
            />
            {modoCliente === 'contacto' ? (
              <Input
                placeholder="Ej: Sra. Gómez · 11 5555-1234"
                maxLength={120}
                value={contacto}
                onChange={(e) => setContacto(e.target.value)}
              />
            ) : clienteSel ? (
              <div className="flex items-center justify-between rounded-xl border border-brand-300 bg-brand-50 px-3 py-2.5 dark:border-brand-800 dark:bg-brand-950/40">
                <span className="flex items-center gap-2 font-semibold">
                  <UserRound className="h-4 w-4" /> {clienteSel.nombre}
                </span>
                <Button size="sm" variant="ghost" onClick={() => setClienteSel(null)}>
                  Cambiar
                </Button>
              </div>
            ) : (
              <div>
                <Input placeholder="Buscar por nombre o teléfono…" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
                <ul className="mt-2 max-h-40 overflow-y-auto rounded-xl border border-stone-200 dark:border-stone-800">
                  {clientes.length === 0 ? (
                    <li className="flex items-center gap-2 p-3 text-sm text-stone-500">
                      <UserPlus className="h-4 w-4" /> Sin coincidencias. Podés darlo de alta en Clientes.
                    </li>
                  ) : (
                    clientes.slice(0, 20).map((c) => (
                      <li key={c.id}>
                        <button
                          onClick={() => setClienteSel(c)}
                          className="flex w-full justify-between px-3 py-2 text-left text-sm hover:bg-stone-50 dark:hover:bg-stone-800"
                        >
                          <span className="font-medium">{c.nombre}</span>
                          <span className="text-stone-500">{c.telefono}</span>
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              </div>
            )}
          </div>
        )}
        {editando && !pedido.cliente_id && (
          <Field label="Contacto">
            {(id) => <Input id={id} maxLength={120} value={contacto} onChange={(e) => setContacto(e.target.value)} />}
          </Field>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Field label="Día de entrega">
            {(id) => <Input id={id} type="date" min={isoLocal()} value={fecha} onChange={(e) => setFecha(e.target.value)} />}
          </Field>
          <Field label="Hora">
            {(id) => <Input id={id} type="time" step="900" value={hora} onChange={(e) => setHora(e.target.value)} />}
          </Field>
        </div>

        <div>
          <p className="label">Productos</p>
          <div className="mb-3 flex gap-2">
            <Select value={agregarId} onChange={(e) => setAgregarId(e.target.value)}>
              <option value="">Agregar producto…</option>
              {productos
                .filter((p) => !items[p.id])
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nombre} — {fmtDinero(p.precio_venta)}
                  </option>
                ))}
            </Select>
            <Button
              variant="secondary"
              disabled={!agregarId}
              onClick={() => {
                setItems((it) => ({ ...it, [agregarId]: 1 }))
                setAgregarId('')
              }}
            >
              Agregar
            </Button>
          </div>
          {lineas.length > 0 && (
            <ul className="divide-y divide-stone-100 rounded-xl border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
              {lineas.map(([id, cant]) => (
                <li key={id} className="flex items-center gap-3 px-3 py-2">
                  <span className="min-w-0 flex-1 truncate font-medium">{porId[id].nombre}</span>
                  <Stepper value={cant} min={1} onChange={(n) => setItems((it) => ({ ...it, [id]: n }))} />
                  <span className="tabular w-24 text-right font-semibold">{fmtDinero(porId[id].precio_venta * cant)}</span>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    icon={Trash2}
                    aria-label="Quitar"
                    onClick={() =>
                      setItems((it) => {
                        const { [id]: _, ...resto } = it
                        return resto
                      })
                    }
                  />
                </li>
              ))}
            </ul>
          )}
        </div>

        <Field label="Notas" hint="Decoración, sin TACC, retirar por sucursal…">
          {(id) => <Textarea id={id} maxLength={2000} value={notas} onChange={(e) => setNotas(e.target.value)} />}
        </Field>
      </div>
    </Modal>
  )
}
