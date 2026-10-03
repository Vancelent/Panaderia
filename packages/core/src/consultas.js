// Claves de caché e intervalos de refresco de las consultas (TanStack Query), compartidos entre la web y
// la app. Cada plataforma arma sus hooks con estas claves, así invalidar ['productos'] refresca todas sus
// variantes en cualquiera de las dos.

export const qk = {
  me: ['me'],
  productos: (params) => ['productos', params ?? {}],
  materiasPrimas: ['materias-primas'],
  receta: (id) => ['receta', id],
  turnoActual: ['turno-actual'],
  ventasTurno: ['ventas-turno'],
  turnosAbiertos: ['turnos-abiertos'],
  pedidos: (params) => ['pedidos', params ?? {}],
  pendienteProduccion: ['pendiente-produccion'],
  clientes: (buscar) => ['clientes', buscar ?? ''],
  resumen: (desde, hasta) => ['resumen', desde, hasta],
  alertas: ['alertas'],
  arqueos: ['arqueos'],
  usuarios: ['usuarios'],
  proveedores: ['proveedores'],
  compras: ['compras'],
  gastos: ['gastos'],
  mediosPago: ['medios-pago'],
  diaAnterior: ['dia-anterior'],
  puntosEntrega: (params) => ['puntos-entrega', params ?? {}],
  plantillas: (id) => ['plantillas', id],
  descuentos: (id) => ['descuentos', id],
  saldos: ['saldos'],
  cuentaCorriente: (id) => ['cuenta-corriente', id],
  hojas: (fecha) => ['hojas', fecha],
  hoja: (id) => ['hoja', id],
  resumenEntregas: (fecha) => ['resumen-entregas', fecha],
  repartidores: ['repartidores'],
  recorrido: (id) => ['recorrido', id],
  metodos: ['metodos-ingreso'],
  terminales: ['terminales'],
  dispositivos: (usuarioId) => ['dispositivos', usuarioId],
}

// Cada cuánto se refresca el stock solo, para ver lo que cargan otras pantallas
// (p. ej. la producción del panadero en la caja). Solo mientras la pestaña está visible.
export const REFRESCO_STOCK_MS = 8_000

