import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Field, Input, Select, Textarea } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { EmptyState, ErrorState, PageHeader, Segmented } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, patch, post, put } from '../../lib/api'
import { fmtDinero, fmtFechaHora, fmtNumero } from '../../lib/format'
import { useCompras, useGastos, useMateriasPrimas, useProveedores } from '../../lib/queries'

const TABS = [
  { value: 'compras', label: 'Compras' },
  { value: 'insumos', label: 'Insumos' },
  { value: 'proveedores', label: 'Proveedores' },
  { value: 'gastos', label: 'Gastos' },
]

export default function ComprasPage() {
  const [tab, setTab] = useState('compras')
  const [modal, setModal] = useState(null) // { tipo, item }
  const abrir = (tipo, item = null) => setModal({ tipo, item })
  const etiquetaNuevo = { compras: 'Registrar compra', insumos: 'Nuevo insumo', proveedores: 'Nuevo proveedor', gastos: 'Registrar gasto' }

  return (
    <div>
      <PageHeader
        title="Compras y gastos"
        subtitle="Las compras suman stock de insumos y actualizan su costo promedio."
        actions={
          <Button icon={Plus} onClick={() => abrir(tab)}>
            {etiquetaNuevo[tab]}
          </Button>
        }
      />
      <Segmented className="mb-4" options={TABS} value={tab} onChange={setTab} />
      {tab === 'compras' && <TablaCompras />}
      {tab === 'insumos' && <TablaInsumos onEditar={(m) => abrir('insumos', m)} />}
      {tab === 'proveedores' && <TablaProveedores onEditar={(p) => abrir('proveedores', p)} />}
      {tab === 'gastos' && <TablaGastos />}

      {modal?.tipo === 'compras' && <CompraModal onClose={() => setModal(null)} />}
      {modal?.tipo === 'insumos' && <InsumoModal insumo={modal.item} onClose={() => setModal(null)} />}
      {modal?.tipo === 'proveedores' && <ProveedorModal proveedor={modal.item} onClose={() => setModal(null)} />}
      {modal?.tipo === 'gastos' && <GastoModal onClose={() => setModal(null)} />}
    </div>
  )
}

function Tabla({ q, vacio, columnas, fila }) {
  if (q.isLoading) return <PantallaCarga />
  if (q.isError) return <ErrorState error={q.error} onRetry={q.refetch} />
  if (!q.data.length)
    return (
      <div className="card">
        <EmptyState title={vacio} />
      </div>
    )
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <thead className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-500 dark:border-stone-800">
          <tr>
            {columnas.map((c) => (
              <th key={c.label} className={`px-4 py-3 font-semibold ${c.right ? 'text-right' : ''}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100 dark:divide-stone-800">{q.data.map(fila)}</tbody>
      </table>
    </div>
  )
}

const td = 'px-4 py-3'
const tdR = 'tabular px-4 py-3 text-right'

function TablaCompras() {
  return (
    <Tabla
      q={useCompras()}
      vacio="Todavía no hay compras registradas"
      columnas={[{ label: 'Fecha' }, { label: 'Proveedor' }, { label: 'Insumo' }, { label: 'Cantidad', right: true }, { label: 'Total', right: true }, { label: 'Costo unit.', right: true }]}
      fila={(c) => (
        <tr key={c.id}>
          <td className={`${td} text-stone-500`}>{fmtFechaHora(c.fecha)}</td>
          <td className={td}>{c.proveedor}</td>
          <td className={`${td} font-medium`}>{c.materia_prima}</td>
          <td className={tdR}>{fmtNumero(c.cantidad_comprada)}</td>
          <td className={tdR}>{fmtDinero(c.precio_total)}</td>
          <td className={`${tdR} text-stone-500`}>{fmtDinero(c.precio_total / c.cantidad_comprada)}</td>
        </tr>
      )}
    />
  )
}

function TablaInsumos({ onEditar }) {
  return (
    <Tabla
      q={useMateriasPrimas()}
      vacio="Cargá tus insumos (harina, manteca, levadura…)"
      columnas={[{ label: 'Insumo' }, { label: 'Stock', right: true }, { label: 'Mínimo', right: true }, { label: 'Costo prom.', right: true }, { label: '' }]}
      fila={(m) => (
        <tr key={m.id}>
          <td className={`${td} font-medium`}>{m.nombre}</td>
          <td className={tdR}>
            {fmtNumero(m.stock_actual)} {m.unidad_medida}
          </td>
          <td className={tdR}>{fmtNumero(m.stock_minimo)}</td>
          <td className={tdR}>
            {fmtDinero(m.costo_unitario_actual)} / {m.unidad_medida}
          </td>
          <td className={`${td} text-right`}>
            <Button size="icon-sm" variant="ghost" icon={Pencil} aria-label="Editar" onClick={() => onEditar(m)} />
          </td>
        </tr>
      )}
    />
  )
}

function TablaProveedores({ onEditar }) {
  return (
    <Tabla
      q={useProveedores()}
      vacio="Todavía no hay proveedores"
      columnas={[{ label: 'Nombre' }, { label: 'CUIT' }, { label: 'Teléfono' }, { label: 'Dirección' }, { label: '' }]}
      fila={(p) => (
        <tr key={p.id}>
          <td className={`${td} font-medium`}>{p.nombre}</td>
          <td className={`${td} tabular`}>{p.cuit ?? '—'}</td>
          <td className={td}>{p.telefono ?? '—'}</td>
          <td className={td}>{p.direccion ?? '—'}</td>
          <td className={`${td} text-right`}>
            <Button size="icon-sm" variant="ghost" icon={Pencil} aria-label="Editar" onClick={() => onEditar(p)} />
          </td>
        </tr>
      )}
    />
  )
}

function TablaGastos() {
  return (
    <Tabla
      q={useGastos()}
      vacio="Todavía no hay gastos registrados"
      columnas={[{ label: 'Fecha' }, { label: 'Concepto' }, { label: 'Monto', right: true }]}
      fila={(g) => (
        <tr key={g.id}>
          <td className={`${td} text-stone-500`}>{fmtFechaHora(g.fecha)}</td>
          <td className={td}>{g.concepto}</td>
          <td className={tdR}>{fmtDinero(g.monto)}</td>
        </tr>
      )}
    />
  )
}

/** Modal con formulario + mutación, para no repetir el mismo esqueleto 4 veces. */
function FormModal({ title, valido, mutationFn, invalidar, onClose, children }) {
  const qc = useQueryClient()
  const toast = useToast()
  const m = useMutation({
    mutationFn,
    onSuccess: () => {
      toast.ok('Guardado.')
      invalidar.forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button loading={m.isPending} disabled={!valido} onClick={() => m.mutate()}>
            Guardar
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">{children}</div>
    </Modal>
  )
}

function CompraModal({ onClose }) {
  const proveedores = useProveedores()
  const insumos = useMateriasPrimas()
  const [f, setF] = useState({ proveedor_id: '', materia_prima_id: '', cantidad_comprada: '', precio_total: '' })
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))
  const mp = insumos.data?.find((m) => String(m.id) === f.materia_prima_id)
  const unit = Number(f.cantidad_comprada) > 0 ? Number(f.precio_total) / Number(f.cantidad_comprada) : 0
  return (
    <FormModal
      title="Registrar compra"
      valido={f.proveedor_id && f.materia_prima_id && Number(f.cantidad_comprada) > 0 && Number(f.precio_total) > 0}
      mutationFn={() =>
        post('/compras', {
          proveedor_id: Number(f.proveedor_id),
          materia_prima_id: Number(f.materia_prima_id),
          cantidad_comprada: f.cantidad_comprada,
          precio_total: Number(f.precio_total),
        })
      }
      invalidar={['compras', 'materias-primas', 'resumen']}
      onClose={onClose}
    >
      <Field label="Proveedor">
        {(id) => (
          <Select id={id} value={f.proveedor_id} onChange={set('proveedor_id')}>
            <option value="">Elegí…</option>
            {(proveedores.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Insumo">
        {(id) => (
          <Select id={id} value={f.materia_prima_id} onChange={set('materia_prima_id')}>
            <option value="">Elegí…</option>
            {(insumos.data ?? []).map((m) => (
              <option key={m.id} value={m.id}>
                {m.nombre}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label={`Cantidad${mp ? ` (${mp.unidad_medida})` : ''}`}>
        {(id) => <Input id={id} type="number" min="0" step="0.001" value={f.cantidad_comprada} onChange={set('cantidad_comprada')} />}
      </Field>
      <Field label="Total pagado" hint={unit ? `${fmtDinero(unit)} por ${mp?.unidad_medida ?? 'unidad'}` : undefined}>
        {(id) => <Input id={id} type="number" min="0" step="0.01" value={f.precio_total} onChange={set('precio_total')} />}
      </Field>
    </FormModal>
  )
}

function InsumoModal({ insumo, onClose }) {
  const [f, setF] = useState({
    nombre: insumo?.nombre ?? '',
    unidad_medida: insumo?.unidad_medida ?? 'kg',
    stock_minimo: insumo?.stock_minimo ?? 0,
    stock_actual: insumo?.stock_actual ?? 0,
  })
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))
  return (
    <FormModal
      title={insumo ? 'Editar insumo' : 'Nuevo insumo'}
      valido={f.nombre.trim() && f.unidad_medida.trim()}
      mutationFn={() => {
        const body = { nombre: f.nombre.trim(), unidad_medida: f.unidad_medida.trim(), stock_minimo: String(f.stock_minimo || 0) }
        return insumo
          ? patch(`/materias-primas/${insumo.id}`, body)
          : post('/materias-primas', { ...body, stock_actual: String(f.stock_actual || 0) })
      }}
      invalidar={['materias-primas']}
      onClose={onClose}
    >
      <Field label="Nombre" className="sm:col-span-2">
        {(id) => <Input id={id} maxLength={120} value={f.nombre} onChange={set('nombre')} />}
      </Field>
      <Field label="Unidad de medida">
        {(id) => (
          <>
            <Input id={id} list="unidades" maxLength={20} value={f.unidad_medida} onChange={set('unidad_medida')} />
            <datalist id="unidades">
              {['kg', 'g', 'l', 'ml', 'u', 'docena'].map((u) => (
                <option key={u} value={u} />
              ))}
            </datalist>
          </>
        )}
      </Field>
      <Field label="Stock mínimo">
        {(id) => <Input id={id} type="number" min="0" step="0.001" value={f.stock_minimo} onChange={set('stock_minimo')} />}
      </Field>
      {!insumo && (
        <Field label="Stock inicial" hint="Después se mueve con compras y producción.">
          {(id) => <Input id={id} type="number" min="0" step="0.001" value={f.stock_actual} onChange={set('stock_actual')} />}
        </Field>
      )}
    </FormModal>
  )
}

function ProveedorModal({ proveedor, onClose }) {
  const [f, setF] = useState({
    nombre: proveedor?.nombre ?? '',
    cuit: proveedor?.cuit ?? '',
    telefono: proveedor?.telefono ?? '',
    direccion: proveedor?.direccion ?? '',
    notas: proveedor?.notas ?? '',
  })
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))
  return (
    <FormModal
      title={proveedor ? 'Editar proveedor' : 'Nuevo proveedor'}
      valido={f.nombre.trim()}
      mutationFn={() => {
        const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.trim() || null]))
        return proveedor ? put(`/proveedores/${proveedor.id}`, body) : post('/proveedores', body)
      }}
      invalidar={['proveedores']}
      onClose={onClose}
    >
      <Field label="Nombre" className="sm:col-span-2">
        {(id) => <Input id={id} maxLength={120} value={f.nombre} onChange={set('nombre')} />}
      </Field>
      <Field label="CUIT">{(id) => <Input id={id} maxLength={20} placeholder="30-12345678-9" value={f.cuit} onChange={set('cuit')} />}</Field>
      <Field label="Teléfono">{(id) => <Input id={id} type="tel" maxLength={40} value={f.telefono} onChange={set('telefono')} />}</Field>
      <Field label="Dirección" className="sm:col-span-2">
        {(id) => <Input id={id} maxLength={200} value={f.direccion} onChange={set('direccion')} />}
      </Field>
      <Field label="Notas" className="sm:col-span-2">
        {(id) => <Textarea id={id} maxLength={2000} value={f.notas} onChange={set('notas')} />}
      </Field>
    </FormModal>
  )
}

function GastoModal({ onClose }) {
  const [concepto, setConcepto] = useState('')
  const [monto, setMonto] = useState('')
  return (
    <FormModal
      title="Registrar gasto"
      valido={concepto.trim() && Number(monto) > 0}
      mutationFn={() => post('/gastos', { concepto: concepto.trim(), monto: Number(monto) })}
      invalidar={['gastos', 'resumen']}
      onClose={onClose}
    >
      <Field label="Concepto" hint="Luz, alquiler, gas, bolsas…">
        {(id) => <Input id={id} maxLength={120} value={concepto} onChange={(e) => setConcepto(e.target.value)} />}
      </Field>
      <Field label="Monto">
        {(id) => <Input id={id} type="number" min="0" step="0.01" value={monto} onChange={(e) => setMonto(e.target.value)} />}
      </Field>
    </FormModal>
  )
}
