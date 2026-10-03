import { useQuery } from '@tanstack/react-query'
import { qk, REFRESCO_STOCK_MS } from '@panaderia/core/consultas'
import { get } from './api'

// Las claves de caché y los intervalos de refresco son los del paquete compartido (packages/core):
// invalidar ['productos'] refresca todas sus variantes, en la web y en la app.
export { qk, REFRESCO_STOCK_MS }

export const useProductos = (params) =>
  useQuery({
    queryKey: qk.productos(params),
    queryFn: () => get('/productos', params),
    refetchInterval: REFRESCO_STOCK_MS,
  })

export const useMateriasPrimas = () =>
  useQuery({
    queryKey: qk.materiasPrimas,
    queryFn: () => get('/materias-primas'),
    refetchInterval: REFRESCO_STOCK_MS,
  })

export const useReceta = (productoId) =>
  useQuery({
    queryKey: qk.receta(productoId),
    queryFn: () => get(`/productos/${productoId}/receta`),
    enabled: !!productoId,
  })

export const useTurnoActual = () =>
  useQuery({ queryKey: qk.turnoActual, queryFn: () => get('/turnos/actual') })

export const useVentasTurno = (enabled = true) =>
  useQuery({ queryKey: qk.ventasTurno, queryFn: () => get('/turnos/actual/ventas'), enabled })

export const useTurnosAbiertos = () =>
  useQuery({ queryKey: qk.turnosAbiertos, queryFn: () => get('/turnos/abiertos') })

export const usePedidos = (params) =>
  useQuery({
    queryKey: qk.pedidos(params),
    queryFn: () => get('/pedidos', params),
    refetchInterval: 15_000, // el tablero de comandas se mantiene al día solo
  })

export const usePendienteProduccion = () =>
  useQuery({
    queryKey: qk.pendienteProduccion,
    queryFn: () => get('/produccion/pendiente'),
    refetchInterval: 15_000,
  })

export const useClientes = (buscar) =>
  useQuery({
    queryKey: qk.clientes(buscar),
    queryFn: () => get('/clientes', buscar ? { buscar } : undefined),
    placeholderData: (prev) => prev,
  })

export const useResumen = (desde, hasta) =>
  useQuery({
    queryKey: qk.resumen(desde, hasta),
    queryFn: () => get('/finanzas/resumen', { desde, hasta }),
    placeholderData: (prev) => prev,
  })

export const useAlertas = () => useQuery({ queryKey: qk.alertas, queryFn: () => get('/stock/alertas') })
export const useArqueos = () => useQuery({ queryKey: qk.arqueos, queryFn: () => get('/arqueos') })
export const useUsuarios = () => useQuery({ queryKey: qk.usuarios, queryFn: () => get('/usuarios') })
export const useProveedores = () =>
  useQuery({ queryKey: qk.proveedores, queryFn: () => get('/proveedores') })
export const useCompras = () => useQuery({ queryKey: qk.compras, queryFn: () => get('/compras') })
export const useGastos = () => useQuery({ queryKey: qk.gastos, queryFn: () => get('/gastos') })

// Medios que ofrece la caja (los define el servidor); cuenta corriente aparte, si hay cliente
export const useMediosPago = () =>
  useQuery({ queryKey: qk.mediosPago, queryFn: () => get('/medios-pago'), staleTime: 5 * 60_000 })

export const useDiaAnterior = (enabled = true) =>
  useQuery({
    queryKey: qk.diaAnterior,
    queryFn: () => get('/stock/dia-anterior'),
    enabled,
    refetchInterval: REFRESCO_STOCK_MS,
  })

export const usePuntosEntrega = (params) =>
  useQuery({
    queryKey: qk.puntosEntrega(params),
    queryFn: () => get('/contabilidad/puntos-entrega', params),
    placeholderData: (prev) => prev,
  })

export const usePlantillas = (puntoId) =>
  useQuery({
    queryKey: qk.plantillas(puntoId),
    queryFn: () => get(`/contabilidad/puntos-entrega/${puntoId}/plantillas`),
    enabled: !!puntoId,
  })

export const useDescuentos = (puntoId) =>
  useQuery({
    queryKey: qk.descuentos(puntoId),
    queryFn: () => get(`/contabilidad/puntos-entrega/${puntoId}/descuentos`),
    enabled: !!puntoId,
  })

export const useSaldos = () =>
  useQuery({ queryKey: qk.saldos, queryFn: () => get('/contabilidad/saldos'), refetchInterval: 30_000 })

export const useCuentaCorriente = (clienteId) =>
  useQuery({
    queryKey: qk.cuentaCorriente(clienteId),
    queryFn: () => get(`/contabilidad/clientes/${clienteId}/cuenta-corriente`),
    enabled: !!clienteId,
  })

// ---------- Reparto ----------

export const useHojas = (fecha) =>
  useQuery({
    queryKey: qk.hojas(fecha),
    queryFn: () => get('/entregas/hojas', { fecha }),
    placeholderData: (prev) => prev,
    refetchInterval: 20_000, // las entregas de la calle se ven al rato en la gestión
  })

export const useHoja = (id) =>
  useQuery({
    queryKey: qk.hoja(id),
    queryFn: () => get(`/entregas/hojas/${id}`),
    enabled: !!id,
    refetchInterval: 20_000,
  })

export const useResumenEntregas = (fecha) =>
  useQuery({
    queryKey: qk.resumenEntregas(fecha),
    queryFn: () => get('/entregas/resumen', { fecha }),
    placeholderData: (prev) => prev,
    refetchInterval: 20_000,
  })

export const useRepartidores = () =>
  useQuery({ queryKey: qk.repartidores, queryFn: () => get('/entregas/repartidores') })

export const useRecorrido = (hojaId, enabled = true) =>
  useQuery({
    queryKey: qk.recorrido(hojaId),
    queryFn: () => get(`/entregas/hojas/${hojaId}/recorrido`),
    enabled: !!hojaId && enabled,
    refetchInterval: 30_000,
  })

// ---------- Ingreso y seguridad ----------

export const useMetodosIngreso = () =>
  useQuery({ queryKey: qk.metodos, queryFn: () => get('/auth/metodos'), staleTime: 60_000 })

export const useTerminales = (enabled = true) =>
  useQuery({ queryKey: qk.terminales, queryFn: () => get('/auth/terminales'), enabled })

export const useDispositivos = (usuarioId) =>
  useQuery({
    queryKey: qk.dispositivos(usuarioId),
    queryFn: () => get(`/usuarios/${usuarioId}/dispositivos`),
    enabled: !!usuarioId,
  })
