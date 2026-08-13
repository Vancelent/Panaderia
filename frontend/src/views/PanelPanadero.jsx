import React, { useState, useEffect, useMemo } from 'react';
import { Plus, Minus, CheckCircle2, AlertTriangle, Send, X, Search, LayoutGrid, List, Filter, ShoppingBag, RotateCcw } from 'lucide-react';
import api from '../api/api';

const PanelPanadero = () => {
  const [productos, setProductos] = useState([]);
  const [cantidades, setCantidades] = useState({});
  const [loading, setLoading] = useState(false);
  const [mensajeExito, setMensajeExito] = useState('');
  const [error, setError] = useState('');

  // Nuevos estados de control visual y búsqueda
  const [busqueda, setBusqueda] = useState('');
  const [vistaModo, setVistaModo] = useState('lista'); // 'lista' o 'tarjetas'
  const [categoriaActiva, setCategoriaActiva] = useState('Todos');

  const [mostrarTicket, setMostrarTicket] = useState(false);
  const [productosAEnviar, setProductosAEnviar] = useState([]);

  const [showBajaModal, setShowBajaModal] = useState(false);
  const [bajaProductoId, setBajaProductoId] = useState('');
  const [bajaCantidad, setBajaCantidad] = useState('');
  const [bajaMotivo, setBajaMotivo] = useState('');

  const fetchProductos = async () => {
    try {
      const response = await api.get('/productos/');
      setProductos(response.data);
    } catch (err) {
      console.error("Error al cargar productos:", err);
      setError("Error al cargar la lista de productos.");
    }
  };

  useEffect(() => {
    fetchProductos();
  }, []);

  const modificarCantidad = (productoId, valor) => {
    setCantidades((prev) => {
      const actual = prev[productoId] || 0;
      const nueva = actual + valor;
      return {
        ...prev,
        [productoId]: nueva < 0 ? 0 : nueva,
      };
    });
  };

  const setCantidadManual = (productoId, valor) => {
    const numerico = parseInt(valor, 10);
    setCantidades((prev) => ({
      ...prev,
      [productoId]: isNaN(numerico) || numerico < 0 ? 0 : numerico,
    }));
  };

  const limpiarSeleccion = () => {
    setCantidades({});
  };

  // Clasificación dinámica de categorías según nombre de producto
  const obtenerCategoria = (nombre) => {
    const n = nombre.toLowerCase();
    if (n.includes('pan') || n.includes('miga') || n.includes('flauta') || n.includes('miñón') || n.includes('bollo') || n.includes('baguette') || n.includes('lactal')) {
      return 'Panes';
    }
    if (n.includes('factura') || n.includes('medialuna') || n.includes('vigilante') || n.includes('sacramento') || n.includes('croissant') || n.includes('berlinesa') || n.includes('donas')) {
      return 'Facturas y Bollería';
    }
    if (n.includes('bizcoch') || n.includes('cremona') || n.includes('librito') || n.includes('rosquita') || n.includes('chipá') || n.includes('scon')) {
      return 'Bizcochería y Salados';
    }
    if (n.includes('tarta') || n.includes('torta') || n.includes('pastafrola') || n.includes('alfajor') || n.includes('budín') || n.includes('pasta') || n.includes('masas')) {
      return 'Pastelería y Dulces';
    }
    return 'Otros';
  };

  // Obtener lista de categorías únicas disponibles
  const categoriasDisponibles = useMemo(() => {
    const cats = new Set(['Todos']);
    productos.forEach(p => cats.add(obtenerCategoria(p.nombre)));
    return Array.from(cats);
  }, [productos]);

  // Filtrado en tiempo real por búsqueda y por categoría
  const productosFiltrados = useMemo(() => {
    return productos.filter(p => {
      const coincideBusqueda = p.nombre.toLowerCase().includes(busqueda.toLowerCase());
      const catProd = obtenerCategoria(p.nombre);
      const coincideCategoria = categoriaActiva === 'Todos' || catProd === categoriaActiva;
      return coincideBusqueda && coincideCategoria;
    });
  }, [productos, busqueda, categoriaActiva]);

  // Totales acumulados de la selección actual
  const seleccionTotales = useMemo(() => {
    let itemsCount = 0;
    let unidadesCount = 0;
    Object.entries(cantidades).forEach(([_, cant]) => {
      if (cant > 0) {
        itemsCount += 1;
        unidadesCount += cant;
      }
    });
    return { itemsCount, unidadesCount };
  }, [cantidades]);

  const preRegistrarProduccion = () => {
    const seleccionados = Object.entries(cantidades)
      .filter(([_, cantidad]) => cantidad > 0)
      .map(([id, cantidad]) => {
        const prod = productos.find(p => p.id === parseInt(id, 10));
        return {
          producto_id: parseInt(id, 10),
          nombre: prod ? prod.nombre : 'Producto Desconocido',
          cantidad: cantidad,
        };
      });

    if (seleccionados.length === 0) {
      setError("No has ingresado ninguna cantidad para registrar.");
      setTimeout(() => setError(''), 3000);
      return;
    }
    
    setProductosAEnviar(seleccionados);
    setMostrarTicket(true);
  };

  const confirmarProduccion = async () => {
    setLoading(true);
    setError('');
    
    try {
      await api.post('/produccion/', {
        productos: productosAEnviar.map(p => ({ producto_id: p.producto_id, cantidad: p.cantidad })),
      });

      setMensajeExito("¡Producción masiva registrada con éxito!");
      setCantidades({}); 
      setMostrarTicket(false);
      fetchProductos(); 
      
      setTimeout(() => setMensajeExito(''), 4000);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      setError("Error al registrar la producción en bloque.");
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setLoading(false);
    }
  };

  const solicitarBaja = async (e) => {
    e.preventDefault();
    if (!bajaProductoId || !bajaCantidad || !bajaMotivo) {
      setError("Completa todos los campos de la baja.");
      return;
    }
    try {
      await api.post('/produccion/merma', {
        producto_id: parseInt(bajaProductoId, 10),
        cantidad_perdida: parseInt(bajaCantidad, 10),
        motivo: bajaMotivo
      });
      setMensajeExito("Baja/Merma registrada con éxito.");
      setShowBajaModal(false);
      setBajaProductoId('');
      setBajaCantidad('');
      setBajaMotivo('');
      fetchProductos();
    } catch (err) {
      setError(err.response?.data?.detail || "Error al registrar la baja.");
    }
    setTimeout(() => { setError(''); setMensajeExito(''); }, 4000);
  };

  return (
    <div className="min-h-screen bg-slate-100 font-sans pb-36">
      {/* Header Fijo */}
      <div className="bg-gradient-to-r from-amber-600 to-orange-500 p-4 md:p-6 sticky top-0 z-20 shadow-md text-white">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-black uppercase tracking-wider text-center md:text-left">
              Planilla de Producción
            </h1>
            <p className="text-orange-100 text-xs md:text-sm text-center md:text-left font-medium mt-0.5">
              Registrá fácil y rápido toda la horneada del día
            </p>
          </div>

          <div className="flex items-center gap-3">
            {seleccionTotales.itemsCount > 0 && (
              <button 
                onClick={limpiarSeleccion}
                className="bg-orange-700/60 hover:bg-orange-700 text-orange-100 px-3 py-2 rounded-xl text-xs md:text-sm font-bold flex items-center gap-1.5 transition-colors border border-orange-400/40"
                title="Limpiar cantidades ingresadas"
              >
                <RotateCcw className="w-4 h-4" />
                <span>Limpiar</span>
              </button>
            )}

            <button 
              onClick={() => setShowBajaModal(true)}
              className="bg-red-600 hover:bg-red-700 text-white px-3 py-2 md:px-4 md:py-2.5 rounded-xl font-bold flex items-center gap-2 transition-colors shadow-sm text-xs md:text-sm"
            >
              <AlertTriangle className="w-4 h-4" />
              <span>Reportar Baja</span>
            </button>
          </div>
        </div>
      </div>

      <div className="p-4 max-w-6xl mx-auto mt-2 space-y-4">
        
        {/* Alertas */}
        {error && (
          <div className="bg-red-100 text-red-700 p-4 rounded-xl font-bold flex items-center gap-2 shadow-sm">
            <AlertTriangle className="w-6 h-6 shrink-0" />
            {error}
          </div>
        )}
        
        {mensajeExito && (
          <div className="bg-emerald-100 text-emerald-700 p-4 rounded-xl font-bold flex items-center gap-2 shadow-sm">
            <CheckCircle2 className="w-6 h-6 shrink-0" />
            {mensajeExito}
          </div>
        )}

        {/* BARRA DE HERRAMIENTAS: Buscador, Categorías y Toggle Vista */}
        <div className="bg-white rounded-2xl p-4 shadow-sm border border-slate-200 space-y-4">
          <div className="flex flex-col md:flex-row gap-3 items-center justify-between">
            
            {/* Buscador de Producto */}
            <div className="relative w-full md:w-96">
              <Search className="w-5 h-5 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Buscar producto por nombre..."
                value={busqueda}
                onChange={e => setBusqueda(e.target.value)}
                className="w-full pl-10 pr-10 py-2.5 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-800 focus:outline-none focus:border-orange-500 focus:bg-white text-sm"
              />
              {busqueda && (
                <button 
                  onClick={() => setBusqueda('')} 
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Alternador de Modo de Vista (Tabla Compacta vs Tarjetas) */}
            <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl w-full md:w-auto justify-center">
              <button
                onClick={() => setVistaModo('lista')}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold text-xs md:text-sm transition-all ${
                  vistaModo === 'lista'
                    ? 'bg-white text-orange-600 shadow-sm'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                <List className="w-4 h-4" />
                <span>Lista Compacta</span>
              </button>
              <button
                onClick={() => setVistaModo('tarjetas')}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold text-xs md:text-sm transition-all ${
                  vistaModo === 'tarjetas'
                    ? 'bg-white text-orange-600 shadow-sm'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                <LayoutGrid className="w-4 h-4" />
                <span>Mosaico / Tarjetas</span>
              </button>
            </div>
          </div>

          {/* Filtro de Categorías Rápidas */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none pt-2 border-t border-slate-100">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider shrink-0 flex items-center gap-1">
              <Filter className="w-3.5 h-3.5" />
              Filtrar:
            </span>
            {categoriasDisponibles.map(cat => (
              <button
                key={cat}
                onClick={() => setCategoriaActiva(cat)}
                className={`px-3.5 py-1.5 rounded-xl font-bold text-xs whitespace-nowrap transition-all ${
                  categoriaActiva === cat
                    ? 'bg-orange-500 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* LISTADO DE PRODUCTOS */}
        {productosFiltrados.length === 0 ? (
          <div className="bg-white rounded-2xl p-12 text-center border border-slate-200 shadow-sm">
            <ShoppingBag className="w-16 h-16 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500 font-bold text-lg">No se encontraron productos.</p>
            <p className="text-slate-400 text-sm mt-1">Prueba cambiando la búsqueda o el filtro de categoría.</p>
          </div>
        ) : vistaModo === 'lista' ? (

          /* VISTA A: LISTA COMPACTA (Ideal para manejar 30-50+ productos sin scrollear tanto) */
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 text-xs font-extrabold uppercase">
                  <tr>
                    <th className="py-3 px-4">Producto</th>
                    <th className="py-3 px-4 text-center">Stock Actual</th>
                    <th className="py-3 px-4 text-center">Cantidad Elaborada</th>
                    <th className="py-3 px-4 text-right">Accesos Rápidos</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {productosFiltrados.map((producto) => {
                    const cantidadActual = cantidades[producto.id] || 0;
                    const tieneCantidad = cantidadActual > 0;

                    return (
                      <tr 
                        key={producto.id}
                        className={`transition-colors hover:bg-orange-50/40 ${
                          tieneCantidad ? 'bg-orange-50/60 font-semibold' : ''
                        }`}
                      >
                        <td className="py-3 px-4">
                          <div className="font-bold text-slate-800 text-base md:text-lg">{producto.nombre}</div>
                          <div className="text-xs font-semibold text-slate-400">{obtenerCategoria(producto.nombre)}</div>
                        </td>

                        <td className="py-3 px-4 text-center">
                          <span className="bg-slate-100 text-slate-700 px-3 py-1 rounded-lg text-xs md:text-sm font-extrabold">
                            {producto.stock_mostrador} u.
                          </span>
                        </td>

                        <td className="py-3 px-4">
                          <div className="flex items-center justify-center gap-2 max-w-[200px] mx-auto">
                            <button 
                              onClick={() => modificarCantidad(producto.id, -1)}
                              className="w-10 h-10 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-700 active:scale-95 transition-transform shrink-0 font-bold"
                            >
                              <Minus className="w-4 h-4" />
                            </button>

                            <input 
                              type="number"
                              min="0"
                              value={cantidadActual || ''}
                              onChange={(e) => setCantidadManual(producto.id, e.target.value)}
                              placeholder="0"
                              className="w-20 h-10 text-center text-xl font-black text-orange-600 bg-white border-2 border-orange-200 rounded-lg focus:outline-none focus:border-orange-500"
                            />

                            <button 
                              onClick={() => modificarCantidad(producto.id, 1)}
                              className="w-10 h-10 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-700 active:scale-95 transition-transform shrink-0 font-bold"
                            >
                              <Plus className="w-4 h-4" />
                            </button>
                          </div>
                        </td>

                        <td className="py-3 px-4 text-right">
                          <div className="flex justify-end gap-1.5">
                            <button 
                              onClick={() => modificarCantidad(producto.id, 10)}
                              className="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg text-slate-700 font-bold text-xs active:scale-95"
                            >
                              +10
                            </button>
                            <button 
                              onClick={() => modificarCantidad(producto.id, 50)}
                              className="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg text-slate-700 font-bold text-xs active:scale-95"
                            >
                              +50
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ) : (

          /* VISTA B: MOSAICO / TARJETAS (Vista clásica ampliada) */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {productosFiltrados.map((producto) => {
              const cantidadActual = cantidades[producto.id] || 0;
              const tieneCantidad = cantidadActual > 0;

              return (
                <div 
                  key={producto.id}
                  className={`bg-white rounded-2xl shadow-sm border-2 transition-all p-5 flex flex-col gap-4 ${
                    tieneCantidad ? 'border-orange-500 shadow-md ring-2 ring-orange-100' : 'border-slate-200'
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <h2 className="text-xl font-bold text-slate-800 leading-tight">
                        {producto.nombre}
                      </h2>
                      <span className="text-xs font-semibold text-slate-400">
                        {obtenerCategoria(producto.nombre)}
                      </span>
                    </div>
                    <span className="bg-slate-100 text-slate-500 px-3 py-1 rounded-lg text-sm font-bold whitespace-nowrap ml-2">
                      Stock: {producto.stock_mostrador}
                    </span>
                  </div>

                  {/* Controles de Cantidad */}
                  <div className="flex items-center justify-between gap-3 mt-auto">
                    <button 
                      onClick={() => modificarCantidad(producto.id, -1)}
                      className="w-14 h-14 rounded-xl bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 active:scale-95 transition-transform shrink-0"
                    >
                      <Minus className="w-6 h-6" />
                    </button>

                    <input 
                      type="number"
                      min="0"
                      value={cantidadActual || ''}
                      onChange={(e) => setCantidadManual(producto.id, e.target.value)}
                      placeholder="0"
                      className="w-full h-14 text-center text-3xl font-black text-orange-600 bg-orange-50 border-2 border-orange-100 rounded-xl focus:outline-none focus:border-orange-500 focus:bg-white"
                    />

                    <button 
                      onClick={() => modificarCantidad(producto.id, 1)}
                      className="w-14 h-14 rounded-xl bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 active:scale-95 transition-transform shrink-0"
                    >
                      <Plus className="w-6 h-6" />
                    </button>
                  </div>

                  {/* Acceso rápido */}
                  <div className="flex gap-2">
                    <button 
                      onClick={() => modificarCantidad(producto.id, 10)}
                      className="flex-1 py-2 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg text-slate-600 font-bold text-sm active:scale-95"
                    >
                      +10
                    </button>
                    <button 
                      onClick={() => modificarCantidad(producto.id, 50)}
                      className="flex-1 py-2 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg text-slate-600 font-bold text-sm active:scale-95"
                    >
                      +50
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Barra Flotante Inferior (Sticky Bottom con Resumen Dinámico) */}
      <div className="fixed bottom-0 left-0 w-full bg-white/95 backdrop-blur-md border-t border-slate-200 p-4 shadow-[0_-10px_40px_rgba(0,0,0,0.1)] z-20">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          
          {/* Contador de Ítems Seleccionados */}
          <div className="flex items-center gap-3 w-full sm:w-auto justify-center sm:justify-start">
            <div className="bg-orange-100 text-orange-600 font-black p-3 rounded-2xl text-xl flex items-center justify-center min-w-[50px]">
              {seleccionTotales.itemsCount}
            </div>
            <div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Productos Seleccionados</p>
              <p className="text-base font-black text-slate-800">
                Total a Ingresar: <span className="text-orange-600">{seleccionTotales.unidadesCount} unidades</span>
              </p>
            </div>
          </div>

          {/* Botón de Enviar */}
          <button
            onClick={preRegistrarProduccion}
            disabled={loading || seleccionTotales.itemsCount === 0}
            className="w-full sm:w-auto px-8 bg-emerald-500 hover:bg-emerald-600 active:scale-[0.98] transition-all text-white py-4 rounded-2xl text-xl font-black uppercase flex items-center justify-center gap-3 shadow-lg disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? 'Enviando...' : (
              <>
                <Send className="w-6 h-6" />
                Guardar Planilla
              </>
            )}
          </button>
        </div>
      </div>

      {/* MODAL TICKET DE CONFIRMACIÓN */}
      {mostrarTicket && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col">
            <div className="bg-slate-800 p-6 text-center">
              <h2 className="text-3xl font-black text-white uppercase">Ticket de Producción</h2>
              <p className="text-slate-300 font-medium">Revisa las cantidades antes de guardar</p>
            </div>
            
            <div className="p-6 max-h-[60vh] overflow-y-auto">
              <ul className="divide-y divide-slate-200">
                {productosAEnviar.map((prod, idx) => (
                  <li key={idx} className="py-4 flex justify-between items-center">
                    <span className="text-xl font-bold text-slate-700">{prod.nombre}</span>
                    <span className="text-2xl font-black text-emerald-600 bg-emerald-50 px-4 py-1 rounded-xl">
                      +{prod.cantidad} u.
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="p-6 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row gap-4">
              <button 
                onClick={() => setMostrarTicket(false)}
                disabled={loading}
                className="flex-1 bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold py-4 rounded-xl text-lg transition-colors"
              >
                Cancelar
              </button>
              <button 
                onClick={confirmarProduccion}
                disabled={loading}
                className="flex-[2] bg-emerald-500 hover:bg-emerald-600 text-white font-black py-4 rounded-xl text-lg uppercase shadow-lg disabled:opacity-50 transition-colors"
              >
                {loading ? 'Guardando...' : 'Confirmar y Guardar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL DE BAJA / MERMA */}
      {showBajaModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg overflow-hidden">
            <div className="bg-red-600 p-6 flex justify-between items-center text-white">
              <h3 className="text-2xl font-black flex items-center gap-2">
                <AlertTriangle className="w-6 h-6" />
                Reportar Baja / Error
              </h3>
              <button onClick={() => setShowBajaModal(false)} className="hover:text-red-200"><X className="w-8 h-8"/></button>
            </div>
            
            <form onSubmit={solicitarBaja} className="p-8 flex flex-col gap-6">
              <div>
                <label className="block text-lg font-bold text-slate-700 mb-2">Producto</label>
                <select 
                  required
                  value={bajaProductoId}
                  onChange={e => setBajaProductoId(e.target.value)}
                  className="w-full text-xl border-2 border-slate-300 rounded-xl p-4 outline-none focus:border-red-400 bg-slate-50 font-bold"
                >
                  <option value="">Seleccione un producto</option>
                  {productos.map(p => (
                    <option key={p.id} value={p.id}>{p.nombre} (Stock: {p.stock_mostrador})</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label className="block text-lg font-bold text-slate-700 mb-2">Cantidad a dar de baja</label>
                <input 
                  type="number" 
                  required 
                  min="1"
                  value={bajaCantidad}
                  onChange={e => setBajaCantidad(e.target.value)}
                  className="w-full text-2xl font-black text-center border-2 border-slate-300 rounded-xl p-4 outline-none focus:border-red-400 bg-slate-50"
                />
              </div>

              <div>
                <label className="block text-lg font-bold text-slate-700 mb-2">Motivo (Ej. Caída, Vencido)</label>
                <input 
                  type="text" 
                  required 
                  value={bajaMotivo}
                  onChange={e => setBajaMotivo(e.target.value)}
                  className="w-full text-lg border-2 border-slate-300 rounded-xl p-4 outline-none focus:border-red-400 bg-slate-50 font-bold"
                  placeholder="Escribí el motivo aquí..."
                />
              </div>

              <button 
                type="submit" 
                className="w-full bg-red-600 hover:bg-red-700 text-white font-black py-5 rounded-xl text-xl mt-4 transition-colors shadow-lg uppercase"
              >
                Confirmar Baja
              </button>
            </form>
          </div>
        </div>
      )}

    </div>
  );
};

export default PanelPanadero;

