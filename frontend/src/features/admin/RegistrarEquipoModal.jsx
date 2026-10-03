import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { Field, Input, Select } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { qk } from '../../lib/queries'

/**
 * "Registrar este equipo como caja" (docs/rfc-001 §2.3): el servidor deja una cookie en este navegador y
 * guarda solo su hash. Desde entonces, el login de este equipo ofrece el PIN a las personas que lo tienen.
 */
export default function RegistrarEquipoModal({ open, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [nombre, setNombre] = useState('Caja del mostrador')
  const [tipo, setTipo] = useState('Caja')

  const registrar = useMutation({
    mutationFn: () => post('/auth/terminales', { nombre: nombre.trim(), tipo }),
    onSuccess: (t) => {
      toast.ok(`Equipo registrado: «${t.nombre}». Ya se puede ingresar con PIN desde este equipo.`)
      qc.invalidateQueries({ queryKey: qk.terminales })
      qc.invalidateQueries({ queryKey: qk.metodos })
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Registrar este equipo"
      description="Solo en un equipo registrado se puede ingresar con PIN. Hacelo desde la PC del mostrador o la tablet de cuadra."
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button loading={registrar.isPending} disabled={!nombre.trim()} onClick={() => registrar.mutate()}>
            Registrar este equipo
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Nombre del equipo" hint="Para reconocerlo en la lista de equipos.">
          {(id) => <Input id={id} maxLength={80} value={nombre} onChange={(e) => setNombre(e.target.value)} />}
        </Field>
        <Field
          label="Tipo"
          hint={tipo === 'Caja' ? 'Caja: entran con PIN la encargada y las vendedoras.' : 'Cuadra: entra con PIN el panadero.'}
        >
          {(id) => (
            <Select id={id} value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="Caja">Caja del mostrador</option>
              <option value="Cuadra">Tablet de cuadra</option>
            </Select>
          )}
        </Field>
      </div>
    </Modal>
  )
}
