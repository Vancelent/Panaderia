import {
  BarChart3,
  ChefHat,
  ClipboardList,
  Package,
  NotebookTabs,
  Receipt,
  ShoppingCart,
  Store,
  MapPinned,
  Truck,
  Users,
  UserCog,
} from 'lucide-react'

export const ROL = {
  ADMIN: 'Admin',
  ENCARGADA: 'Encargada',
  VENDEDORA: 'Vendedora',
  PANADERO: 'Panadero',
  REPARTIDOR: 'Repartidor',
}

export const GESTION = [ROL.ADMIN, ROL.ENCARGADA]
export const MOSTRADOR = [ROL.ADMIN, ROL.ENCARGADA, ROL.VENDEDORA]
export const PRODUCCION = [ROL.ADMIN, ROL.ENCARGADA, ROL.PANADERO]
// Todo el personal del local: el repartidor solo ve su hoja de ruta
export const INTERNOS = [ROL.ADMIN, ROL.ENCARGADA, ROL.VENDEDORA, ROL.PANADERO]
export const TODOS = Object.values(ROL)

export const esGestion = (u) => !!u && GESTION.includes(u.rol)
export const puedeCobrar = (u) => !!u && MOSTRADOR.includes(u.rol)

export function inicioPorRol(rol) {
  if (GESTION.includes(rol)) return '/admin'
  if (rol === ROL.VENDEDORA) return '/caja'
  if (rol === ROL.PANADERO) return '/produccion'
  if (rol === ROL.REPARTIDOR) return '/reparto'
  return '/login'
}

// Navegación: el backend es quien realmente autoriza; esto solo ordena la UI.
export const NAV = [
  { to: '/admin', label: 'Tablero', icon: BarChart3, roles: GESTION },
  { to: '/caja', label: 'Caja', icon: ShoppingCart, roles: MOSTRADOR },
  { to: '/pedidos', label: 'Pedidos', icon: ClipboardList, roles: INTERNOS },
  { to: '/produccion', label: 'Producción', icon: ChefHat, roles: PRODUCCION },
  { to: '/stock', label: 'Stock', icon: Package, roles: INTERNOS },
  { to: '/clientes', label: 'Clientes', icon: Users, roles: MOSTRADOR },
  { to: '/admin/productos', label: 'Productos', icon: Store, roles: GESTION },
  { to: '/admin/compras', label: 'Compras', icon: Truck, roles: GESTION },
  { to: '/admin/reparto', label: 'Reparto', icon: MapPinned, roles: GESTION },
  { to: '/reparto', label: 'Mi ruta', icon: MapPinned, roles: [ROL.REPARTIDOR] },
  { to: '/admin/contabilidad', label: 'Contabilidad', icon: NotebookTabs, roles: GESTION },
  { to: '/admin/arqueos', label: 'Arqueos', icon: Receipt, roles: GESTION },
  { to: '/admin/usuarios', label: 'Usuarios', icon: UserCog, roles: [ROL.ADMIN] },
]
