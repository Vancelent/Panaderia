import { useState, useEffect } from 'react';
import { 
  Search, User, FileText, Users, Receipt, Divide, Tag, 
  ChevronRight, Delete, X, CreditCard, Banknote, Store, 
  Wifi, Signal, Home, ChevronRightCircle, Box, Trash2
} from 'lucide-react';
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
  const [verificando, setVerificando] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [numpadBuffer, setNumpadBuffer] = useState(''); // Multiplicador de cantidad

  
  // Estado para Modal de Pago
  const [showPaymentModal, setShowPaymentModal] = useState(false);

  // Verificar si ya hay un turno abierto
  const verificarTurno = async () => {
    try {
      const res = await api.get('/turnos/activo');
      if (res.data && res.data.turno_id) {
        setTurnoActivo(res.data.turno_id);
      }
    } catch (err) {
      console.log("No hay turnos activos.");
    } finally {
      setVerificando(false);
    }
  };

  useEffect(() => {
    verificarTurno();
  }, []);

  // Cargar productos
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
      setError('Monto inválido para fondo de caja.');
      return;
    }

    setLoading(true);
    try {
      const response = await api.post('/turnos/abrir', { efectivo_inicial: parseFloat(efectivoInicial) });
      setTurnoActivo(response.data.turno_id);
    } catch (err) {
      if (err.response?.status === 400 && err.response.data.detail?.includes("abierto")) {
        verificarTurno();
      } else {
        setError(err.response?.data?.detail || "Error al abrir turno.");
      }
    } finally {
      setLoading(false);
    }
  };

  // --- LÓGICA DE POS ---
  const agregarAlCarrito = (producto) => {
    if (producto.stock_mostrador <= 0) return;
    
    // Si el usuario tecleó un número, lo usamos. Si no, es 1.
    const cantAgregar = numpadBuffer === '' ? 1 : parseInt(numpadBuffer);
    setNumpadBuffer(''); // Limpiar buffer después de usar
    
    setCarrito((prev) => {
      const existe = prev.find(item => item.producto_id === producto.id);
      const nuevaCantidadTotal = existe ? existe.cantidad + cantAgregar : cantAgregar;

      if (nuevaCantidadTotal > producto.stock_mostrador) {
         setError(`Solo hay ${producto.stock_mostrador} disponibles de ${producto.nombre}.`);
         setTimeout(() => setError(''), 3000);
         // Se puede retornar el carrito sin cambios o ajustar al máximo. Lo ajustamos al máximo.
         const cantMaxima = producto.stock_mostrador;
         
         if (existe) {
             return prev.map(item => item.producto_id === producto.id ? { ...item, cantidad: cantMaxima, subtotal: cantMaxima * item.precio } : item);
         }
         return [...prev, { producto_id: producto.id, nombre: producto.nombre, precio: producto.precio_venta, cantidad: cantMaxima, subtotal: cantMaxima * producto.precio_venta, stock_max: producto.stock_mostrador }];
      }

      if (existe) {
        return prev.map(item => 
          item.producto_id === producto.id 
            ? { ...item, cantidad: nuevaCantidadTotal, subtotal: nuevaCantidadTotal * item.precio }
            : item
        );
      }
      return [...prev, { 
        producto_id: producto.id, 
        nombre: producto.nombre, 
        precio: producto.precio_venta, 
        cantidad: nuevaCantidadTotal,
        subtotal: nuevaCantidadTotal * producto.precio_venta,
        stock_max: producto.stock_mostrador
      }];
    });
  };

  const handleNumpad = (val) => {
    if (val === 'C') {
      setNumpadBuffer('');
    } else if (val === 'DEL') {
      setNumpadBuffer(prev => prev.slice(0, -1));
    } else {
      if (numpadBuffer.length < 3) { // Máximo 999 unidades por seguridad
        setNumpadBuffer(prev => prev + val);
      }
    }
  };

  const modificarCantidad = (producto_id, delta) => {
    setCarrito((prev) => prev.map(item => {
      if (item.producto_id === producto_id) {
        const nuevaCantidad = item.cantidad + delta;
        if (nuevaCantidad <= 0) return null;
        if (nuevaCantidad > item.stock_max) return item;
        return { ...item, cantidad: nuevaCantidad, subtotal: nuevaCantidad * item.precio };
      }
      return item;
    }).filter(Boolean));
  };

  const eliminarDelCarrito = (producto_id) => {
    setCarrito(prev => prev.filter(item => item.producto_id !== producto_id));
  };

  const calcularTotal = () => carrito.reduce((tot, item) => tot + item.subtotal, 0);

  const confirmarVenta = async (metodoPago) => {
    const payload = {
      turno_id: turnoActivo || 1, // Se envía el turno activo
      metodo_pago: metodoPago.toLowerCase(),
      total: calcularTotal(),
      detalles: carrito.map(i => ({ producto_id: i.producto_id, cantidad: i.cantidad }))
    };

    try {
      const response = await api.post('http://localhost:8000/ventas/', payload);
      if (response.status === 200 || response.status === 201) {
        setCarrito([]);
        setShowPaymentModal(false);
        setSuccessMsg(`Venta registrada con éxito en ${metodoPago}`);
        setTimeout(() => setSuccessMsg(''), 4000);
        fetchProductos(); // Actualiza el stock de la grilla instantáneamente
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Error al conectar con el servidor.");
      setTimeout(() => setError(''), 4000);
    }
  };

  // Filtro de búsqueda
  const productosFiltrados = productos.filter(p => 
    p.nombre.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // --- RENDER FASE 1 (Apertura) ---
  if (verificando) return <div className="h-screen flex items-center justify-center">Cargando...</div>;
  if (!turnoActivo) {
    return (
      <div className="min-h-screen bg-slate-800 flex items-center justify-center font-sans">
        <div className="w-96 bg-white p-8 rounded-lg shadow-2xl">
          <h2 className="text-2xl font-bold mb-6 text-center text-slate-800">Abrir Turno</h2>
          <form onSubmit={handleAbrirTurno}>
            <input type="number" step="0.01" required value={efectivoInicial} onChange={e => setEfectivoInicial(e.target.value)} className="w-full border-2 border-slate-300 p-3 rounded mb-4 text-xl text-center" placeholder="Fondo Inicial ($)" />
            <button type="submit" className="w-full bg-emerald-600 text-white font-bold py-3 rounded hover:bg-emerald-700">INICIAR CAJA</button>
            {error && <p className="text-red-500 text-sm mt-3 text-center">{error}</p>}
          </form>
        </div>
      </div>
    );
  }

  // --- RENDER FASE 2 (POS EMPRESARIAL) ---
  return (
    <div className="h-screen w-full flex flex-col bg-slate-200 font-sans overflow-hidden text-sm select-none">
      
      {/* Top Navbar (Oscuro) */}
      <header className="h-12 bg-slate-800 text-slate-300 flex items-center justify-between px-4 shrink-0 shadow-md z-20">
        <div className="flex items-center gap-4 font-bold text-white">
          <Store className="w-5 h-5 text-orange-500" />
          <span>ERP POS <span className="text-slate-400 font-normal">| Panadería</span></span>
        </div>
        
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 bg-emerald-500/20 text-emerald-400 px-3 py-1 rounded">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            Turno #{turnoActivo}
          </div>
          <div className="flex items-center gap-3 text-slate-400">
            <User className="w-4 h-4" /> Asesor 1
            <Signal className="w-4 h-4 text-emerald-500" />
            <Wifi className="w-4 h-4 text-emerald-500" />
          </div>
        </div>
      </header>

      {/* Main Container */}
      <div className="flex-1 flex overflow-hidden">
        
        {/* LEFT PANEL: Ticket & Controls (Aprox 35%) */}
        <div className="w-[400px] flex flex-col bg-white border-r border-slate-300 z-10 shadow-xl">
          
          {/* Header Ticket */}
          <div className="h-10 bg-slate-100 border-b border-slate-300 flex items-center px-4 font-bold text-slate-600">
            Ticket de Venta
          </div>

          {/* Ticket Items List */}
          <div className="flex-1 overflow-y-auto p-1 bg-white">
            {carrito.length === 0 ? (
              <div className="h-full flex items-center justify-center text-slate-300">Vacío</div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {carrito.map((item) => (
                  <li key={item.producto_id} className="p-3 hover:bg-slate-50 relative group">
                    <div className="flex justify-between items-start mb-1">
                      <span className="font-bold text-slate-800">{item.nombre}</span>
                      <span className="font-bold text-slate-900">${item.subtotal.toFixed(2)}</span>
                    </div>
                    <div className="text-xs text-slate-500 flex justify-between items-center">
                      <span>{item.cantidad}.00 Unidades en ${item.precio.toFixed(2)} / Unidades</span>
                      
                      {/* Controles rápidos (ocultos hasta hover para mantener diseño limpio) */}
                      <div className="hidden group-hover:flex items-center bg-slate-200 rounded border border-slate-300">
                        <button onClick={() => modificarCantidad(item.producto_id, -1)} className="px-2 py-1 hover:bg-slate-300">-</button>
                        <button onClick={() => eliminarDelCarrito(item.producto_id)} className="px-2 py-1 text-red-500 hover:bg-red-100"><Trash2 className="w-3 h-3"/></button>
                        <button onClick={() => modificarCantidad(item.producto_id, 1)} className="px-2 py-1 hover:bg-slate-300">+</button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Totals & Numpad Section */}
          <div className="border-t border-slate-300 bg-slate-50 flex flex-col z-10">
            
            {/* Teclado Multiplicador (Numpad) */}
            <div className="p-3 border-b border-slate-200 flex gap-3">
              <div className="flex-1 grid grid-cols-3 gap-1.5">
                {['1','2','3','4','5','6','7','8','9','C','0','DEL'].map(n => (
                  <button 
                    key={n} 
                    onClick={() => handleNumpad(n)}
                    className={`h-10 rounded font-bold text-sm shadow-sm border border-slate-300 transition-all active:scale-95 ${n === 'C' ? 'bg-red-50 text-red-600 hover:bg-red-100' : n === 'DEL' ? 'bg-slate-200 text-slate-600 hover:bg-slate-300' : 'bg-white text-slate-700 hover:bg-slate-100'}`}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <div className="w-[100px] flex flex-col items-center justify-center bg-indigo-50 border-2 border-indigo-200 rounded-lg text-indigo-800 p-2 text-center shadow-inner">
                <span className="text-xs font-bold uppercase mb-1">Múltiplo</span>
                <span className="text-3xl font-black">{numpadBuffer || '1'}x</span>
              </div>
            </div>

            {/* Area de Total y Cobro */}
            <div className="p-5 flex flex-col gap-4">
              <div className="flex justify-between items-end">
                <span className="text-slate-500 font-bold uppercase text-xs tracking-widest">Total</span>
                <span className="text-4xl font-black text-slate-900 tracking-tighter">${calcularTotal().toFixed(2)}</span>
              </div>
              
              <button 
                onClick={() => setShowPaymentModal(true)}
                disabled={carrito.length === 0}
                className={`w-full py-4 rounded-xl font-black text-xl flex items-center justify-center transition-all ${
                  carrito.length > 0 
                    ? 'bg-emerald-500 hover:bg-emerald-600 text-white shadow-lg shadow-emerald-500/30 active:scale-[0.98]' 
                    : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                }`}
              >
                COBRAR AHORA
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT PANEL: Products Grid (Aprox 65%) */}
        <div className="flex-1 flex flex-col bg-slate-200">
          
          {/* Toolbar / Search */}
          <div className="h-16 bg-slate-200 border-b border-slate-300 flex items-center justify-between px-6 shadow-sm z-0">
            <div className="flex items-center gap-2 text-slate-500 font-medium">
              <Home className="w-5 h-5" />
              <ChevronRight className="w-4 h-4" />
              <span>Panadería</span>
            </div>
            
            <div className="relative">
              <Search className="w-5 h-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400" />
              <input 
                type="text" 
                placeholder="Buscar Productos" 
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="pl-10 pr-4 py-2 w-64 rounded-full border border-slate-300 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 transition-all shadow-sm"
              />
            </div>
          </div>

          {/* Grid de Tarjetas de Producto */}
          <div className="flex-1 overflow-y-auto p-6">
            
            {/* Mensajes Flotantes */}
            {error && <div className="mb-4 bg-red-100 text-red-700 p-3 rounded shadow-sm border border-red-200">{error}</div>}
            {successMsg && <div className="mb-4 bg-emerald-100 text-emerald-700 p-3 rounded shadow-sm border border-emerald-200">{successMsg}</div>}

            <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {productosFiltrados.map((prod) => (
                <button
                  key={prod.id}
                  onClick={() => agregarAlCarrito(prod)}
                  disabled={prod.stock_mostrador <= 0}
                  className={`bg-white rounded-md shadow-sm border border-slate-200 h-36 flex flex-col relative overflow-hidden transition-transform active:scale-95 hover:shadow-md ${prod.stock_mostrador <= 0 ? 'opacity-50 cursor-not-allowed grayscale' : ''}`}
                >
                  {/* Badges Superiores */}
                  <div className="absolute top-0 left-0 w-full flex justify-between p-0">
                    <div className="bg-purple-400 text-white text-[10px] font-bold px-2 py-0.5 rounded-br-md z-10">
                      {prod.stock_mostrador}
                    </div>
                    <div className="bg-slate-500 text-white text-[11px] font-bold px-2 py-0.5 rounded-bl-md z-10">
                      ${prod.precio_venta.toFixed(2)}
                    </div>
                  </div>
                  
                  {/* Imagen (Mock con icono) */}
                  <div className="flex-1 w-full bg-slate-50 flex items-center justify-center mt-4">
                    <Box className="w-12 h-12 text-slate-300" />
                  </div>
                  
                  {/* Nombre */}
                  <div className="w-full p-2 text-center border-t border-slate-100">
                    <p className="text-xs font-bold text-slate-700 truncate">{prod.nombre}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

      </div>

      {/* MODAL DE PAGO (Mantiene el rediseño anterior pero adaptado) */}
      {showPaymentModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-2xl w-[500px] overflow-hidden">
            <div className="bg-slate-800 p-4 flex justify-between items-center text-white">
              <h3 className="text-lg font-bold">Procesar Pago</h3>
              <button onClick={() => setShowPaymentModal(false)} className="hover:text-red-400"><X className="w-6 h-6"/></button>
            </div>
            
            <div className="p-6">
              <div className="text-center mb-6">
                <p className="text-slate-500 text-sm">Monto a Cobrar</p>
                <p className="text-5xl font-black text-slate-800">${calcularTotal().toFixed(2)}</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <button onClick={() => confirmarVenta('Efectivo')} className="flex flex-col items-center justify-center p-6 bg-slate-50 hover:bg-emerald-50 border-2 border-slate-200 hover:border-emerald-500 rounded-xl transition-all">
                  <Banknote className="w-10 h-10 text-emerald-600 mb-2" />
                  <span className="font-bold text-slate-700">Efectivo</span>
                </button>
                <button onClick={() => confirmarVenta('Transferencia')} className="flex flex-col items-center justify-center p-6 bg-slate-50 hover:bg-blue-50 border-2 border-slate-200 hover:border-blue-500 rounded-xl transition-all">
                  <CreditCard className="w-10 h-10 text-blue-600 mb-2" />
                  <span className="font-bold text-slate-700">Tarjeta / Transf.</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default CajaRegistradora;
