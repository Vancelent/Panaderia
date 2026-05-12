import { useState, useEffect } from 'react';
import { DollarSign, AlertCircle, ShoppingCart, Trash2, Plus, Minus, CheckCircle2 } from 'lucide-react';
import api from '../api/api';

const CajaRegistradora = () => {
  const [turnoActivo, setTurnoActivo] = useState(null);
  const [efectivoInicial, setEfectivoInicial] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Estados de la Fase 2 (POS)
  const [productos, setProductos] = useState([]);
  const [carrito, setCarrito] = useState([]);
  const [cobrando, setCobrando] = useState(false);
  const [verificando, setVerificando] = useState(true);

  // Verificar si ya hay un turno abierto al cargar la página
  const verificarTurno = async () => {
    try {
      const res = await api.get('/turnos/activo');
      if (res.data && res.data.turno_id) {
        setTurnoActivo(res.data.turno_id);
      }
    } catch (err) {
      // 404 significa que no hay turno, lo cual es correcto.
      console.log("No hay turnos activos.");
    } finally {
      setVerificando(false);
    }
  };

  useEffect(() => {
    verificarTurno();
  }, []);

  // Cargar productos cuando hay un turno activo
  const fetchProductos = async () => {
    try {
      const res = await api.get('/productos/');
      setProductos(res.data);
    } catch (err) {
      setError("Error al cargar el catálogo de productos.");
    }
  };

  useEffect(() => {
    if (turnoActivo) {
      fetchProductos();
    }
  }, [turnoActivo]);

  const handleAbrirTurno = async (e) => {
    e.preventDefault();
    setError('');
    
    if (efectivoInicial === '' || isNaN(efectivoInicial) || Number(efectivoInicial) < 0) {
      setError('Por favor ingrese un monto válido para el fondo de caja.');
      return;
    }

    setLoading(true);
    try {
      const response = await api.post('/turnos/abrir', {
        efectivo_inicial: parseFloat(efectivoInicial)
      });
      setTurnoActivo(response.data.turno_id);
    } catch (err) {
      const errorMsg = err.response?.data?.detail || "";
      if (err.response?.status === 400 && errorMsg.includes("ya tiene un turno abierto")) {
        setError("Ya tienes un turno abierto. Recuperando tu sesión automáticamente...");
        setTimeout(() => {
          verificarTurno();
          setError('');
        }, 2000);
      } else {
        setError(errorMsg || "Error crítico al abrir el turno.");
      }
    } finally {
      setLoading(false);
    }
  };

  // --- LÓGICA DE FASE 2 (POS) ---
  const agregarAlCarrito = (producto) => {
    if (producto.stock_mostrador <= 0) return;
    
    setCarrito((prevCarrito) => {
      const existe = prevCarrito.find(item => item.producto_id === producto.id);
      
      if (existe) {
        if (existe.cantidad >= producto.stock_mostrador) {
           setError(`Stock insuficiente de ${producto.nombre}.`);
           setTimeout(() => setError(''), 3000);
           return prevCarrito;
        }
        return prevCarrito.map(item => 
          item.producto_id === producto.id 
            ? { ...item, cantidad: item.cantidad + 1, subtotal: (item.cantidad + 1) * item.precio }
            : item
        );
      }
      
      return [...prevCarrito, { 
        producto_id: producto.id, 
        nombre: producto.nombre, 
        precio: producto.precio_venta, 
        cantidad: 1,
        subtotal: producto.precio_venta
      }];
    });
  };

  const modificarCantidad = (producto_id, delta) => {
    setCarrito((prevCarrito) => {
      return prevCarrito.map(item => {
        if (item.producto_id === producto_id) {
          const nuevaCantidad = item.cantidad + delta;
          if (nuevaCantidad <= 0) return null; // Será filtrado después
          
          const prodOriginal = productos.find(p => p.id === producto_id);
          if (prodOriginal && nuevaCantidad > prodOriginal.stock_mostrador) {
             return item; 
          }
          
          return { ...item, cantidad: nuevaCantidad, subtotal: nuevaCantidad * item.precio };
        }
        return item;
      }).filter(Boolean); // Remueve los null
    });
  };

  const eliminarDelCarrito = (producto_id) => {
    setCarrito((prev) => prev.filter(item => item.producto_id !== producto_id));
  };

  const calcularTotal = () => {
    return carrito.reduce((total, item) => total + item.subtotal, 0);
  };

  const handleCobrar = async () => {
    if (carrito.length === 0) return;
    
    setCobrando(true);
    setError('');
    setSuccessMsg('');
    
    try {
      const payload = {
        turno_id: turnoActivo,
        detalles: carrito.map(item => ({
          producto_id: item.producto_id,
          cantidad: item.cantidad
        }))
      };
      
      await api.post('/ventas/registrar', payload);
      
      setCarrito([]);
      setSuccessMsg("¡Venta registrada y cobrada exitosamente!");
      setTimeout(() => setSuccessMsg(''), 4000);
      
      fetchProductos(); // Actualizar catálogo
    } catch (err) {
      setError(err.response?.data?.detail || "Error al procesar la venta.");
      setTimeout(() => setError(''), 4000);
    } finally {
      setCobrando(false);
    }
  };

  // --- RENDERIZADO DE FASE 1 ---
  if (verificando) {
    return <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-500 font-medium font-sans">Sincronizando caja...</div>;
  }

  if (!turnoActivo) {
    return (
      <div className="min-h-screen bg-slate-100 flex flex-col items-center justify-center p-4 font-sans">
        <div className="max-w-md w-full bg-white rounded-2xl shadow-xl overflow-hidden border border-slate-200">
          <div className="bg-blue-600 p-6 text-center">
            <h2 className="text-2xl font-bold text-white flex items-center justify-center gap-2">
              <DollarSign className="w-6 h-6" />
              Apertura de Caja
            </h2>
            <p className="text-blue-100 text-sm mt-1">Ingrese el fondo inicial del turno</p>
          </div>
          
          <div className="p-8">
            <form onSubmit={handleAbrirTurno} className="space-y-6">
              {error && (
                <div className="bg-red-50 text-red-600 p-4 rounded-xl text-sm flex items-center gap-2 border border-red-100">
                  <AlertCircle className="w-5 h-5 flex-shrink-0" />
                  <p className="font-medium">{error}</p>
                </div>
              )}
              
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-2">
                  Efectivo Inicial Físico ($)
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                    <span className="text-slate-400 font-bold text-lg">$</span>
                  </div>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    required
                    className="block w-full pl-8 pr-4 py-4 text-xl border border-slate-200 rounded-xl focus:ring-4 focus:ring-blue-500/20 focus:border-blue-500 outline-none transition-all text-slate-800 font-semibold bg-slate-50 focus:bg-white"
                    placeholder="0.00"
                    value={efectivoInicial}
                    onChange={(e) => setEfectivoInicial(e.target.value)}
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className={`w-full py-4 px-4 text-white font-bold rounded-xl shadow-lg transition-all text-lg ${
                  loading
                    ? 'bg-blue-400 cursor-not-allowed'
                    : 'bg-blue-600 hover:bg-blue-700 hover:shadow-blue-200 hover:-translate-y-1'
                }`}
              >
                {loading ? 'Procesando...' : 'Abrir Turno'}
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  // --- RENDERIZADO DE FASE 2 (POS) ---
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      
      {/* Header del POS */}
      <header className="bg-white shadow-sm border-b border-slate-200 px-6 py-4 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="bg-blue-100 p-2 rounded-lg">
            <ShoppingCart className="text-blue-600 w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-800">Caja Registradora</h1>
            <p className="text-xs font-semibold text-slate-500">Turno Activo: #{turnoActivo}</p>
          </div>
        </div>
        
        {/* Notificaciones flotantes */}
        {error && (
          <div className="bg-red-100 text-red-700 px-4 py-2 rounded-lg font-medium text-sm flex items-center gap-2 shadow-sm animate-pulse">
            <AlertCircle className="w-4 h-4" /> {error}
          </div>
        )}
        {successMsg && (
          <div className="bg-emerald-100 text-emerald-700 px-4 py-2 rounded-lg font-bold text-sm flex items-center gap-2 shadow-sm">
            <CheckCircle2 className="w-4 h-4" /> {successMsg}
          </div>
        )}
      </header>

      {/* Área Principal (Layout Grid) */}
      <main className="flex-1 flex overflow-hidden">
        
        {/* IZQUIERDA: Catálogo de Productos */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-50">
          <h2 className="text-lg font-bold text-slate-700 mb-6">Productos Disponibles</h2>
          
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {productos.map((prod) => (
              <button
                key={prod.id}
                onClick={() => agregarAlCarrito(prod)}
                disabled={prod.stock_mostrador <= 0}
                className={`relative flex flex-col h-32 p-4 rounded-2xl border-2 text-left transition-all ${
                  prod.stock_mostrador > 0
                    ? 'bg-white border-transparent shadow-sm hover:shadow-md hover:border-blue-400 hover:-translate-y-1 active:scale-95'
                    : 'bg-slate-100 border-slate-200 opacity-60 cursor-not-allowed grayscale'
                }`}
              >
                <div className="flex-1 w-full">
                  <h3 className="font-bold text-slate-800 line-clamp-2 leading-tight">{prod.nombre}</h3>
                  <p className="text-blue-600 font-black mt-1">${prod.precio_venta.toFixed(2)}</p>
                </div>
                
                <div className="w-full flex justify-between items-end mt-2">
                  <span className={`text-xs font-bold px-2 py-1 rounded-md ${
                    prod.stock_mostrador > 0 ? 'bg-blue-50 text-blue-700' : 'bg-slate-200 text-slate-600'
                  }`}>
                    Stock: {prod.stock_mostrador}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* DERECHA: El Ticket / Carrito */}
        <div className="w-96 bg-white border-l border-slate-200 shadow-xl flex flex-col z-10">
          <div className="p-5 border-b border-slate-100 bg-slate-50">
            <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
              Detalle de Venta
              <span className="bg-blue-600 text-white text-xs px-2 py-0.5 rounded-full">{carrito.length}</span>
            </h2>
          </div>
          
          {/* Lista de Items */}
          <div className="flex-1 overflow-y-auto p-2">
            {carrito.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-400 space-y-3">
                <ShoppingCart className="w-12 h-12 opacity-20" />
                <p className="font-medium">El carrito está vacío</p>
              </div>
            ) : (
              <ul className="space-y-2 p-2">
                {carrito.map((item) => (
                  <li key={item.producto_id} className="bg-white border border-slate-100 shadow-sm rounded-xl p-3 flex flex-col gap-2 relative group hover:border-blue-200 transition-colors">
                    
                    <div className="flex justify-between items-start">
                      <span className="font-bold text-slate-800 leading-tight pr-6">{item.nombre}</span>
                      <span className="font-black text-slate-900">${item.subtotal.toFixed(2)}</span>
                    </div>

                    <div className="flex items-center justify-between mt-1">
                      <div className="flex items-center bg-slate-100 rounded-lg p-1">
                        <button onClick={() => modificarCantidad(item.producto_id, -1)} className="w-8 h-8 flex items-center justify-center bg-white rounded shadow-sm text-slate-600 hover:text-blue-600 hover:bg-blue-50 active:scale-95 transition-all">
                          <Minus className="w-4 h-4" />
                        </button>
                        <span className="w-10 text-center font-bold text-slate-800">{item.cantidad}</span>
                        <button onClick={() => modificarCantidad(item.producto_id, 1)} className="w-8 h-8 flex items-center justify-center bg-white rounded shadow-sm text-slate-600 hover:text-blue-600 hover:bg-blue-50 active:scale-95 transition-all">
                          <Plus className="w-4 h-4" />
                        </button>
                      </div>
                      
                      <button 
                        onClick={() => eliminarDelCarrito(item.producto_id)}
                        className="text-slate-400 hover:text-red-500 hover:bg-red-50 p-2 rounded-lg transition-colors"
                      >
                        <Trash2 className="w-5 h-5" />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Footer del Ticket (Total y Botón) */}
          <div className="p-6 bg-slate-50 border-t border-slate-200">
            <div className="flex justify-between items-end mb-6">
              <span className="text-slate-500 font-bold uppercase text-sm tracking-wider">Total a Pagar</span>
              <span className="text-4xl font-black text-slate-900">${calcularTotal().toFixed(2)}</span>
            </div>
            
            <button
              onClick={handleCobrar}
              disabled={cobrando || carrito.length === 0}
              className={`w-full py-5 rounded-2xl font-black text-xl flex items-center justify-center gap-2 shadow-lg transition-all ${
                carrito.length === 0 
                  ? 'bg-slate-300 text-slate-500 cursor-not-allowed shadow-none'
                  : cobrando
                    ? 'bg-emerald-400 text-white cursor-wait'
                    : 'bg-emerald-500 text-white hover:bg-emerald-600 hover:shadow-emerald-500/30 hover:-translate-y-1 active:scale-95'
              }`}
            >
              {cobrando ? 'PROCESANDO...' : 'COBRAR TICKET'}
            </button>
          </div>
        </div>
      </main>

    </div>
  );
};

export default CajaRegistradora;
