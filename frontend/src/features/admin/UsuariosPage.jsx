import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus } from 'lucide-react'
import { useAuth } from '../../auth/context'
import { Button } from '../../components/ui/Button'
import { Field, Input, Select } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Badge, ErrorState, PageHeader } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, patch, post } from '../../lib/api'
import { fmtFecha } from '../../lib/format'
import { useUsuarios } from '../../lib/queries'
import { ROL } from '../../lib/roles'

const TONO_ROL = { Admin: 'violet', Encargada: 'blue', Vendedora: 'green', Panadero: 'brand', Repartidor: 'amber' }

export default function UsuariosPage() {
  const { user } = useAuth()
  const { data, isLoading, isError, error, refetch } = useUsuarios()
  const [editando, setEditando] = useState(null)

  return (
    <div>
      <PageHeader
        title="Usuarios"
        subtitle="Accesos al sistema. Cada rol ve solo lo que necesita."
        actions={
          <Button icon={Plus} onClick={() => setEditando('nuevo')}>
            Nuevo usuario
          </Button>
        }
      />
      {isLoading ? (
        <PantallaCarga />
      ) : isError ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : (
        <div className="card divide-y divide-stone-100 dark:divide-stone-800">
          {data.map((u) => (
            <div key={u.id} className={`flex items-center gap-4 px-4 py-3 ${u.activo ? '' : 'opacity-50'}`}>
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-stone-200 text-sm font-bold uppercase dark:bg-stone-700">
                {u.username.slice(0, 2)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {u.nombre || u.username}
                  {u.id === user.id && <span className="ml-2 text-xs font-normal text-stone-500">(vos)</span>}
                </p>
                <p className="text-sm text-stone-500">
                  @{u.username}
                  {u.creado_en && ` · desde ${fmtFecha(u.creado_en)}`}
                </p>
              </div>
              <Badge tone={TONO_ROL[u.rol]}>{u.rol}</Badge>
              {!u.activo && <Badge>Inactivo</Badge>}
              <Button size="icon-sm" variant="ghost" icon={Pencil} aria-label={`Editar ${u.username}`} onClick={() => setEditando(u)} />
            </div>
          ))}
        </div>
      )}
      {editando && <UsuarioModal usuario={editando === 'nuevo' ? null : editando} esYo={editando?.id === user.id} onClose={() => setEditando(null)} />}
    </div>
  )
}

function UsuarioModal({ usuario, esYo, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [username, setUsername] = useState('')
  const [nombre, setNombre] = useState(usuario?.nombre ?? '')
  const [rol, setRol] = useState(usuario?.rol ?? ROL.VENDEDORA)
  const [activo, setActivo] = useState(usuario?.activo ?? true)
  const [password, setPassword] = useState('')

  const guardar = useMutation({
    mutationFn: () =>
      usuario
        ? patch(`/usuarios/${usuario.id}`, { nombre: nombre.trim() || null, rol, activo, password: password || null })
        : post('/usuarios', { username: username.trim(), nombre: nombre.trim() || null, rol, password }),
    onSuccess: () => {
      toast.ok(usuario ? 'Usuario actualizado.' : 'Usuario creado.')
      qc.invalidateQueries({ queryKey: ['usuarios'] })
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const passOk = usuario ? password === '' || password.length >= 8 : password.length >= 8
  const valido = passOk && (usuario || username.trim().length >= 3)

  return (
    <Modal
      open
      onClose={onClose}
      title={usuario ? `Editar @${usuario.username}` : 'Nuevo usuario'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button loading={guardar.isPending} disabled={!valido} onClick={() => guardar.mutate()}>
            Guardar
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {!usuario && (
          <Field label="Usuario" hint="Minúsculas, números, punto o guion. Es el nombre para ingresar.">
            {(id) => <Input id={id} autoComplete="off" maxLength={50} value={username} onChange={(e) => setUsername(e.target.value.toLowerCase())} />}
          </Field>
        )}
        <Field label="Nombre para mostrar">
          {(id) => <Input id={id} maxLength={100} value={nombre} onChange={(e) => setNombre(e.target.value)} />}
        </Field>
        <Field label="Rol">
          {(id) => (
            <Select id={id} value={rol} onChange={(e) => setRol(e.target.value)} disabled={esYo}>
              {Object.values(ROL).map((r) => (
                <option key={r}>{r}</option>
              ))}
            </Select>
          )}
        </Field>
        <Field
          label={usuario ? 'Nueva contraseña' : 'Contraseña'}
          hint={usuario ? 'Dejala vacía para no cambiarla. Cambiarla cierra sus sesiones abiertas.' : 'Mínimo 8 caracteres.'}
          error={password && password.length < 8 ? 'Mínimo 8 caracteres.' : null}
        >
          {(id) => <Input id={id} type="password" autoComplete="new-password" maxLength={72} value={password} onChange={(e) => setPassword(e.target.value)} />}
        </Field>
        {usuario && !esYo && (
          <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
            <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={activo} onChange={(e) => setActivo(e.target.checked)} />
            Usuario activo (si lo desactivás, pierde el acceso al instante)
          </label>
        )}
      </div>
    </Modal>
  )
}
