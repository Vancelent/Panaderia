import {
  BarChart3,
  ChefHat,
  ClipboardList,
  MapPinned,
  NotebookTabs,
  Package,
  Receipt,
  ShoppingCart,
  Store,
  Truck,
  UserCog,
  Users,
} from 'lucide-react'
import { NAV as ITEMS } from '@panaderia/core/roles'

// Los roles, grupos y la navegación viven en el paquete compartido con la app móvil (packages/core);
// acá solo se les pone el ícono, que es de la librería de la web.
export * from '@panaderia/core/roles'

const ICONOS = {
  tablero: BarChart3,
  caja: ShoppingCart,
  pedidos: ClipboardList,
  produccion: ChefHat,
  stock: Package,
  clientes: Users,
  productos: Store,
  compras: Truck,
  reparto: MapPinned,
  contabilidad: NotebookTabs,
  arqueos: Receipt,
  usuarios: UserCog,
}

export const NAV = ITEMS.map((n) => ({ ...n, icon: ICONOS[n.icono] }))
