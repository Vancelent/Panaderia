// Roles y navegación. El backend es quien realmente autoriza: esto solo ordena la interfaz.
// Los íconos van por nombre (cada plataforma los dibuja con su propia librería).

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

export const NAV = [
  { to: '/admin', label: 'Tablero', icono: 'tablero', roles: GESTION },
  { to: '/caja', label: 'Caja', icono: 'caja', roles: MOSTRADOR },
  { to: '/pedidos', label: 'Pedidos', icono: 'pedidos', roles: INTERNOS },
  { to: '/produccion', label: 'Producción', icono: 'produccion', roles: PRODUCCION },
  { to: '/stock', label: 'Stock', icono: 'stock', roles: INTERNOS },
  { to: '/clientes', label: 'Clientes', icono: 'clientes', roles: MOSTRADOR },
  { to: '/admin/productos', label: 'Productos', icono: 'productos', roles: GESTION },
  { to: '/admin/compras', label: 'Compras', icono: 'compras', roles: GESTION },
  { to: '/admin/reparto', label: 'Reparto', icono: 'reparto', roles: GESTION },
  { to: '/reparto', label: 'Mi ruta', icono: 'reparto', roles: [ROL.REPARTIDOR] },
  { to: '/admin/contabilidad', label: 'Contabilidad', icono: 'contabilidad', roles: GESTION },
  { to: '/admin/arqueos', label: 'Arqueos', icono: 'arqueos', roles: GESTION },
  { to: '/admin/usuarios', label: 'Usuarios', icono: 'usuarios', roles: [ROL.ADMIN] },
]

export const navPara = (rol) => NAV.filter((n) => n.roles.includes(rol))
