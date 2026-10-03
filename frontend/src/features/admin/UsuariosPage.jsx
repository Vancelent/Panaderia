import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Link2Off, Lock, Monitor, Pencil, Plus, Smartphone, Unlock } from 'lucide-react'
import { useAuth } from '../../auth/context'
import { Button } from '../../components/ui/Button'
import { Field, Input, Select } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Badge, EmptyState, ErrorState, PageHeader, Segmented } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { del, mensajeError, patch, post, put } from '../../lib/api'
import { fmtFecha, fmtFechaHora } from '../../lib/format'
import { qk, useDispositivos, useTerminales, useUsuarios } from '../../lib/queries'
import { ROL } from '../../lib/roles'
import RegistrarEquipoModal from './RegistrarEquipoModal'

const TONO_ROL = { Admin: 'violet', Encargada: 'blue', Vendedora: 'green', Panadero: 'brand', Repartidor: 'amber' }
// Quiénes pueden usar PIN (docs/rfc-001 §2.1): la caja y la cuadra, no el dueño ni el reparto
const ROLES_CON_PIN = [ROL.ENCARGADA, ROL.VENDEDORA, ROL.PANADERO]

export default function UsuariosPage() {
  const [tab, setTab] = useState('personas')
  return (
    <div>
      <PageHeader
        title="Usuarios"
        subtitle="Accesos al sistema: personas, PIN y equipos registrados. Cada rol ve solo lo que necesita."
        actions={
          <Segmented
            value={tab}
            onChange={setTab}
            options={[
              { value: 'personas', label: 'Personas' },
              { value: 'equipos', label: 'Equipos' },
            ]}
          />
        }
      />
      {tab === 'personas' ? <Personas /> : <Equipos />}
    </div>
  )
}

function Personas() {
  const { user } = useAuth()
  const { data, isLoading, isError, error, refetch } = useUsuarios()
  const [editando, setEditando] = useState(null)

  if (isLoading) return <PantallaCarga />
  if (isError) return <ErrorState error={error} onRetry={refetch} />
  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button icon={Plus} onClick={() => setEditando('nuevo')}>
          Nuevo usuario
        </Button>
      </div>
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
              <p className="truncate text-sm text-stone-500">
                @{u.username}
                {u.email && ` · ${u.email}`}
                {u.creado_en && ` · desde ${fmtFecha(u.creado_en)}`}
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-1.5">
              {u.google_vinculado && <Badge tone="blue">Google</Badge>}
              {u.pin_bloqueado ? (
                <Badge tone="red">
                  <Lock className="h-3 w-3" /> PIN bloqueado
                </Badge>
              ) : (
                u.tiene_pin && (
                  <Badge tone="green">
                    <KeyRound className="h-3 w-3" /> PIN
                  </Badge>
                )
              )}
              <Badge tone={TONO_ROL[u.rol]}>{u.rol}</Badge>
              {!u.activo && <Badge>Inactivo</Badge>}
            </div>
            <Button size="icon-sm" variant="ghost" icon={Pencil} aria-label={`Editar ${u.username}`} onClick={() => setEditando(u)} />
          </div>
        ))}
      </div>
      {editando && (
        <UsuarioModal
          usuario={editando === 'nuevo' ? null : data.find((u) => u.id === editando.id) ?? editando}
          esYo={editando?.id === user.id}
          onClose={() => setEditando(null)}
        />
      )}
    </>
  )
}

function UsuarioModal({ usuario, esYo, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [username, setUsername] = useState('')
  const [nombre, setNombre] = useState(usuario?.nombre ?? '')
  const [email, setEmail] = useState(usuario?.email ?? '')
  const [rol, setRol] = useState(usuario?.rol ?? ROL.VENDEDORA)
  const [activo, setActivo] = useState(usuario?.activo ?? true)
  const [password, setPassword] = useState('')

  const guardar = useMutation({
    mutationFn: () =>
      usuario
        ? patch(`/usuarios/${usuario.id}`, {
            nombre: nombre.trim() || null,
            email: email.trim() || null,
            rol,
            activo,
            password: password || null,
          })
        : post('/usuarios', {
            username: username.trim(),
            nombre: nombre.trim() || null,
            email: email.trim() || null,
            rol,
            password,
          }),
    onSuccess: () => {
      toast.ok(usuario ? 'Usuario actualizado.' : 'Usuario creado.')
      qc.invalidateQueries({ queryKey: qk.usuarios })
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
      size="lg"
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
        <Field
          label="Correo (para ingresar con Google)"
          hint="Es el correo de la cuenta de Google de la persona. No hay alta automática: solo entra quien tiene su correo cargado acá."
        >
          {(id) => <Input id={id} type="email" autoComplete="off" maxLength={120} value={email} onChange={(e) => setEmail(e.target.value)} />}
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

        {usuario && <SeccionPin usuario={usuario} />}
        {usuario?.google_vinculado && <SeccionGoogle usuario={usuario} />}
        {usuario && <SeccionDispositivos usuario={usuario} />}
      </div>
    </Modal>
  )
}

function Seccion({ titulo, icono: Icono, children, derecha }) {
  return (
    <section className="rounded-2xl border border-stone-200 p-4 dark:border-stone-800">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-bold">
          <Icono className="h-4 w-4 text-stone-500" /> {titulo}
        </h3>
        {derecha}
      </div>
      {children}
    </section>
  )
}

function SeccionPin({ usuario }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [pin, setPin] = useState('')
  const refrescar = () => qc.invalidateQueries({ queryKey: qk.usuarios })
  const cambiar = useMutation({
    mutationFn: () => put(`/usuarios/${usuario.id}/pin`, { pin }),
    onSuccess: () => {
      toast.ok('PIN guardado. Se cerraron las sesiones que tenía abiertas.')
      setPin('')
      refrescar()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const quitar = useMutation({
    mutationFn: () => del(`/usuarios/${usuario.id}/pin`),
    onSuccess: () => {
      toast.ok('PIN quitado.')
      refrescar()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const desbloquear = useMutation({
    mutationFn: () => post(`/usuarios/${usuario.id}/pin/desbloqueo`),
    onSuccess: () => {
      toast.ok('PIN desbloqueado.')
      refrescar()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })

  if (!ROLES_CON_PIN.includes(usuario.rol)) {
    return (
      <Seccion titulo="PIN de caja" icono={KeyRound}>
        <p className="text-sm text-stone-500">El PIN es para la encargada, las vendedoras y el panadero.</p>
      </Seccion>
    )
  }
  return (
    <Seccion
      titulo="PIN de caja"
      icono={KeyRound}
      derecha={
        usuario.pin_bloqueado ? (
          <Badge tone="red">Bloqueado</Badge>
        ) : usuario.tiene_pin ? (
          <Badge tone="green">Cargado</Badge>
        ) : (
          <Badge>Sin PIN</Badge>
        )
      }
    >
      <p className="mb-3 text-sm text-stone-500">
        De 4 a 6 dígitos. Solo sirve en un equipo registrado y no habilita la gestión (precios, usuarios…).
        {usuario.pin_bloqueado && ' Se bloqueó por intentos fallidos: se libera acá, o cuando la persona ingresa con contraseña o Google.'}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label="Nuevo PIN"
          className="tabular w-36 text-center text-lg tracking-widest"
          type="password"
          inputMode="numeric"
          autoComplete="off"
          maxLength={6}
          placeholder="••••"
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
        />
        <Button size="sm" loading={cambiar.isPending} disabled={pin.length < 4} onClick={() => cambiar.mutate()}>
          {usuario.tiene_pin ? 'Cambiar PIN' : 'Cargar PIN'}
        </Button>
        {usuario.pin_bloqueado && (
          <Button size="sm" variant="secondary" icon={Unlock} loading={desbloquear.isPending} onClick={() => desbloquear.mutate()}>
            Desbloquear
          </Button>
        )}
        {usuario.tiene_pin && (
          <Button size="sm" variant="ghost" loading={quitar.isPending} onClick={() => window.confirm('¿Quitar el PIN?') && quitar.mutate()}>
            Quitar
          </Button>
        )}
      </div>
    </Seccion>
  )
}

function SeccionGoogle({ usuario }) {
  const qc = useQueryClient()
  const toast = useToast()
  const desvincular = useMutation({
    mutationFn: () => del(`/usuarios/${usuario.id}/google`),
    onSuccess: () => {
      toast.ok('Cuenta de Google desvinculada.')
      qc.invalidateQueries({ queryKey: qk.usuarios })
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  return (
    <Seccion titulo="Google" icono={Link2Off} derecha={<Badge tone="blue">Vinculada</Badge>}>
      <p className="mb-3 text-sm text-stone-500">
        Ingresa con Google. Si la desvinculás, se cierran sus sesiones y puede volver a vincular otra cuenta con su correo.
      </p>
      <Button
        size="sm"
        variant="secondary"
        loading={desvincular.isPending}
        onClick={() => window.confirm('¿Desvincular la cuenta de Google de este usuario?') && desvincular.mutate()}
      >
        Desvincular
      </Button>
    </Seccion>
  )
}

function SeccionDispositivos({ usuario }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { data = [] } = useDispositivos(usuario.id)
  const revocar = useMutation({
    mutationFn: (id) => del(`/usuarios/${usuario.id}/dispositivos/${id}`),
    onSuccess: () => {
      toast.ok('Dispositivo revocado: se cerró su sesión.')
      qc.invalidateQueries({ queryKey: qk.dispositivos(usuario.id) })
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const activos = data.filter((d) => !d.revocado_en)
  return (
    <Seccion titulo="Celulares con sesión" icono={Smartphone}>
      {activos.length === 0 ? (
        <p className="text-sm text-stone-500">Ninguno. Aparecen acá los celulares donde la persona ingresó a la app.</p>
      ) : (
        <ul className="divide-y divide-stone-100 dark:divide-stone-800">
          {activos.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{d.nombre}</p>
                <p className="text-xs text-stone-500">
                  {d.plataforma} · último uso {d.ultimo_uso ? fmtFechaHora(d.ultimo_uso) : 'nunca'}
                </p>
              </div>
              <Button size="sm" variant="ghost" loading={revocar.isPending} onClick={() => revocar.mutate(d.id)}>
                Cerrar sesión
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Seccion>
  )
}

function Equipos() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading, isError, error, refetch } = useTerminales()
  const [registrando, setRegistrando] = useState(false)
  const cambiar = useMutation({
    mutationFn: ({ id, activo }) => patch(`/auth/terminales/${id}`, { activo }),
    onSuccess: (t) => {
      toast.ok(t.activo ? 'Equipo activado.' : 'Equipo desactivado: se cerraron sus sesiones con PIN.')
      qc.invalidateQueries({ queryKey: qk.terminales })
      qc.invalidateQueries({ queryKey: qk.metodos })
    },
    onError: (e) => toast.error(mensajeError(e)),
  })

  if (isLoading) return <PantallaCarga />
  if (isError) return <ErrorState error={error} onRetry={refetch} />
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-xl text-sm text-stone-500">
          El PIN solo funciona en estos equipos. Para sumar uno, abrí el sistema en esa PC o tablet y elegí
          «Registrar este equipo».
        </p>
        <Button icon={Monitor} onClick={() => setRegistrando(true)}>
          Registrar este equipo
        </Button>
      </div>
      {data.length === 0 ? (
        <div className="card">
          <EmptyState icon={Monitor} title="Todavía no hay equipos registrados">
            Registrá la PC del mostrador para que las vendedoras entren con su PIN.
          </EmptyState>
        </div>
      ) : (
        <div className="card divide-y divide-stone-100 dark:divide-stone-800">
          {data.map((t) => (
            <div key={t.id} className={`flex items-center gap-4 px-4 py-3 ${t.activo ? '' : 'opacity-50'}`}>
              <Monitor className="h-5 w-5 shrink-0 text-stone-400" />
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{t.nombre}</p>
                <p className="text-sm text-stone-500">
                  {t.tipo} · registrado {fmtFecha(t.creado_en)} · último uso {t.ultimo_uso ? fmtFechaHora(t.ultimo_uso) : 'nunca'}
                </p>
              </div>
              <Badge tone={t.activo ? 'green' : 'neutral'}>{t.activo ? 'Activo' : 'Desactivado'}</Badge>
              <Button
                size="sm"
                variant="secondary"
                loading={cambiar.isPending && cambiar.variables?.id === t.id}
                onClick={() => cambiar.mutate({ id: t.id, activo: !t.activo })}
              >
                {t.activo ? 'Desactivar' : 'Activar'}
              </Button>
            </div>
          ))}
        </div>
      )}
      <RegistrarEquipoModal open={registrando} onClose={() => setRegistrando(false)} />
    </>
  )
}
