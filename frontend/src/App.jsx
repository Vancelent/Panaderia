import { lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from './auth/RequireAuth'
import { useAuth } from './auth/context'
import { AppShell } from './components/layout/AppShell'
import { PantallaCarga } from './components/ui/Spinner'
import LoginPage from './features/LoginPage'
import { GESTION, MOSTRADOR, PRODUCCION, ROL, inicioPorRol } from './lib/roles'

// Cada pantalla se carga bajo demanda: la caja no descarga el tablero de finanzas.
const PosPage = lazy(() => import('./features/pos/PosPage'))
const PedidosPage = lazy(() => import('./features/pedidos/PedidosPage'))
const ProduccionPage = lazy(() => import('./features/produccion/ProduccionPage'))
const StockPage = lazy(() => import('./features/stock/StockPage'))
const ClientesPage = lazy(() => import('./features/clientes/ClientesPage'))
const DashboardPage = lazy(() => import('./features/admin/DashboardPage'))
const ProductosPage = lazy(() => import('./features/admin/ProductosPage'))
const ComprasPage = lazy(() => import('./features/admin/ComprasPage'))
const ArqueosPage = lazy(() => import('./features/admin/ArqueosPage'))
const UsuariosPage = lazy(() => import('./features/admin/UsuariosPage'))

function Inicio() {
  const { user, loading } = useAuth()
  if (loading) return <PantallaCarga />
  return <Navigate to={user ? inicioPorRol(user.rol) : '/login'} replace />
}

const conRol = (roles, el) => <RequireAuth roles={roles}>{el}</RequireAuth>

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/caja" element={conRol(MOSTRADOR, <PosPage />)} />
        <Route path="/pedidos" element={<PedidosPage />} />
        <Route path="/produccion" element={conRol(PRODUCCION, <ProduccionPage />)} />
        <Route path="/stock" element={<StockPage />} />
        <Route path="/clientes" element={conRol(MOSTRADOR, <ClientesPage />)} />
        <Route path="/admin" element={conRol(GESTION, <DashboardPage />)} />
        <Route path="/admin/productos" element={conRol(GESTION, <ProductosPage />)} />
        <Route path="/admin/compras" element={conRol(GESTION, <ComprasPage />)} />
        <Route path="/admin/arqueos" element={conRol(GESTION, <ArqueosPage />)} />
        <Route path="/admin/usuarios" element={conRol([ROL.ADMIN], <UsuariosPage />)} />
      </Route>
      <Route path="*" element={<Inicio />} />
    </Routes>
  )
}
