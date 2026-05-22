import React, { useState, useEffect } from 'react';
import { Plus, Minus, CheckCircle2, AlertTriangle, Send, X } from 'lucide-react';
import api from '../api/api';

const PanelPanadero = () => {
  const [productos, setProductos] = useState([]);
  // El "carrito" guarda { producto_id: cantidad }
  const [cantidades, setCantidades] = useState({});
  const [loading, setLoading] = useState(false);
  const [mensajeExito, setMensajeExito] = useState('');
  const [error, setError] = useState('');

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
    <div className="min-h-screen bg-slate-100 font-sans pb-32">
      {/* Header Fijo */}
      <div className="bg-orange-500 p-6 sticky top-0 z-10 shadow-md flex flex-col items-center relative">
        <button 
          onClick={() => setShowBajaModal(true)}
          className="absolute right-4 top-4 md:right-6 md:top-6 bg-red-600 text-white px-3 py-2 md:px-4 md:py-2 rounded-lg font-bold flex items-center gap-2 hover:bg-red-700 transition-colors shadow-sm text-xs md:text-sm"
        >
          <AlertTriangle className="w-4 h-4" />
          <span className="hidden md:inline">Reportar Baja</span>
          <span className="inline md:hidden">Baja</span>
        </button>
        <h1 className="text-3xl md:text-4xl font-black text-white text-center uppercase tracking-wider mt-8 md:mt-0">
          Planilla de Producción
        </h1>
        <p className="text-orange-100 text-center font-medium mt-1">
          Carga toda la horneada de una sola vez
        </p>
      </div>

      <div className="p-4 max-w-4xl mx-auto mt-4">
        
        {/* Alertas */}
        {error && (
          <div className="bg-red-100 text-red-700 p-4 rounded-xl mb-6 font-bold flex items-center gap-2 shadow-sm">
            <AlertTriangle className="w-6 h-6" />
            {error}
          </div>
        )}
        
        {mensajeExito && (
          <div className="bg-emerald-100 text-emerald-700 p-4 rounded-xl mb-6 font-bold flex items-center gap-2 shadow-sm">
            <CheckCircle2 className="w-6 h-6" />
            {mensajeExito}
          </div>
        )}

        {/* Lista Vertical Mobile-First (Grilla en tablets/desktop) */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {productos.map((producto) => {
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
                  <h2 className="text-xl font-bold text-slate-800 leading-tight">
                    {producto.nombre}
                  </h2>
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

                {/* Botones rápidos de acceso directo (opcionales) */}
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
      </div>

      {/* Botón Flotante Inferior (Sticky Bottom) */}
      <div className="fixed bottom-0 left-0 w-full bg-white border-t border-slate-200 p-4 shadow-[0_-10px_40px_rgba(0,0,0,0.1)]">
        <div className="max-w-4xl mx-auto">
          <button
            onClick={preRegistrarProduccion}
            disabled={loading}
            className="w-full bg-emerald-500 hover:bg-emerald-600 active:scale-[0.98] transition-all text-white py-5 rounded-2xl text-2xl font-black uppercase flex items-center justify-center gap-3 shadow-lg disabled:opacity-50 disabled:active:scale-100"
          >
            {loading ? 'Enviando...' : (
              <>
                <Send className="w-8 h-8" />
                Guardar Toda la Planilla
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
                      +{prod.cantidad}
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
                  className="w-full text-xl border-2 border-slate-300 rounded-xl p-4 outline-none focus:border-red-400 bg-slate-50"
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
                  className="w-full text-lg border-2 border-slate-300 rounded-xl p-4 outline-none focus:border-red-400 bg-slate-50"
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
