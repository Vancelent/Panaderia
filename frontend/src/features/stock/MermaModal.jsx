import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { Field, Input, Select } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Stepper } from '../../components/ui/misc'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'

const MOTIVOS = ['Se cayó', 'Vencido', 'Quemado', 'Mal formado', 'Degustación']

export function MermaModal({ open, onClose, productos }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [productoId, setProductoId] = useState('')
  const [cantidad, setCantidad] = useState(1)
  const [motivo, setMotivo] = useState('')
  const producto = productos.find((p) => String(p.id) === productoId)

  const reset = () => {
    setProductoId('')
    setCantidad(1)
    setMotivo('')
  }
  const registrar = useMutation({
    mutationFn: () =>
      post('/mermas', { producto_id: Number(productoId), cantidad_perdida: cantidad, motivo }),
    onSuccess: () => {
      toast.ok(`Merma registrada: ${cantidad} × ${producto?.nombre}`)
      qc.invalidateQueries({ queryKey: ['productos'] })
      reset()
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const valido = producto && cantidad > 0 && cantidad <= producto.stock_disponible && motivo.trim()

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Registrar merma"
      description="Productos que se pierden y salen del stock del mostrador."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="danger" loading={registrar.isPending} disabled={!valido} onClick={() => registrar.mutate()}>
            Dar de baja
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Producto">
          {(id) => (
            <Select id={id} value={productoId} onChange={(e) => setProductoId(e.target.value)}>
              <option value="">Elegí un producto…</option>
              {productos
                .filter((p) => p.stock_disponible > 0)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nombre} (stock {p.stock_disponible})
                  </option>
                ))}
            </Select>
          )}
        </Field>
        <div>
          <p className="label">Cantidad</p>
          <Stepper value={cantidad} onChange={setCantidad} min={1} max={producto?.stock_disponible ?? 9999} size="lg" />
        </div>
        <div>
          <p className="label">Motivo</p>
          <div className="mb-2 flex flex-wrap gap-2">
            {MOTIVOS.map((m) => (
              <Button key={m} size="sm" variant={motivo === m ? 'primary' : 'secondary'} onClick={() => setMotivo(m)}>
                {m}
              </Button>
            ))}
          </div>
          <Input placeholder="Otro motivo…" maxLength={120} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
        </div>
      </div>
    </Modal>
  )
}
