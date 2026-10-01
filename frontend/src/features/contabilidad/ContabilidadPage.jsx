import { useState } from 'react'
import { PageHeader, Segmented } from '../../components/ui/misc'
import CuentaCorrientePanel from './CuentaCorrientePanel'
import PuntosEntregaPanel from './PuntosEntregaPanel'

export default function ContabilidadPage() {
  const [tab, setTab] = useState('cuenta')
  return (
    <div>
      <PageHeader
        title="Contabilidad"
        subtitle="Cuenta corriente de los clientes y puntos de entrega con sus descuentos."
        actions={
          <Segmented
            value={tab}
            onChange={setTab}
            options={[
              { value: 'cuenta', label: 'Cuenta corriente' },
              { value: 'puntos', label: 'Puntos de entrega' },
            ]}
          />
        }
      />
      {tab === 'cuenta' ? <CuentaCorrientePanel /> : <PuntosEntregaPanel />}
    </div>
  )
}
