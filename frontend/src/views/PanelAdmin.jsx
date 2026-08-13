import React, { useState, useEffect } from 'react';
import { LayoutDashboard, Truck, PackageSearch, Users, Wallet, TrendingUp, DollarSign, PlusCircle, ClipboardCheck, BookOpen, Trash2 } from 'lucide-react';
import api from '../api/api';

// ==========================================
// TABS DE NAVEGACIÓN
// ==========================================

const DashboardTab = () => {
  const [resumen, setResumen] = useState(null);

  useEffect(() => {
    const fetchResumen = async () => {
      try {
        const res = await api.get('/finanzas/resumen/');
        setResumen(res.data);
      } catch (err) {
        console.error("Error al cargar resumen:", err);
      }
    };
    fetchResumen();
  }, []);

  if (!resumen) return <div className="p-8 text-center text-slate-500 font-bold">Cargando métricas...</div>;

  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-black text-slate-800">Resumen Financiero</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Tarjeta de Ventas */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4">
          <div className="bg-blue-100 p-4 rounded-xl text-blue-600">
            <TrendingUp className="w-8 h-8" />
          </div>
          <div>
            <p className="text-sm font-bold text-slate-400 uppercase tracking-wider">Ventas Totales</p>
            <p className="text-3xl font-black text-slate-800">${resumen.ventas_totales.toLocaleString()}</p>
          </div>
        </div>

        {/* Tarjeta de Compras */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4">
          <div className="bg-orange-100 p-4 rounded-xl text-orange-600">
            <Truck className="w-8 h-8" />
          </div>
          <div>
            <p className="text-sm font-bold text-slate-400 uppercase tracking-wider">Compras (Insumos)</p>
            <p className="text-3xl font-black text-slate-800">${resumen.compras_materias_primas.toLocaleString()}</p>
          </div>
        </div>

        {/* Tarjeta de Gastos */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4">
          <div className="bg-red-100 p-4 rounded-xl text-red-600">
            <Wallet className="w-8 h-8" />
          </div>
          <div>
            <p className="text-sm font-bold text-slate-400 uppercase tracking-wider">Gastos Varios</p>
            <p className="text-3xl font-black text-slate-800">${resumen.gastos_operativos.toLocaleString()}</p>
          </div>
        </div>

        {/* Tarjeta de Ganancia Neta */}
        <div className="bg-gradient-to-br from-emerald-500 to-emerald-700 p-6 rounded-2xl shadow-lg flex items-center gap-4 text-white">
          <div className="bg-white/20 p-4 rounded-xl">
            <DollarSign className="w-8 h-8" />
          </div>
          <div>
            <p className="text-sm font-bold text-emerald-100 uppercase tracking-wider">Ganancia Neta</p>
            <p className="text-4xl font-black">${resumen.ganancia_neta.toLocaleString()}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <h3 className="text-xl font-bold text-slate-800 mb-6">Ingresos vs Gastos (Últimos 7 días)</h3>
          <div className="h-80 flex items-end justify-between gap-2 px-2 pb-6 border-b border-slate-100">
            {(resumen.datos_grafico || []).map((dia, idx) => {
              const maxVal = Math.max(...(resumen.datos_grafico || []).map(d => Math.max(d.ventas, d.costos)));
              const alturaVentas = maxVal > 0 ? (dia.ventas / maxVal) * 100 : 0;
              const alturaCostos = maxVal > 0 ? (dia.costos / maxVal) * 100 : 0;
              return (
                <div key={idx} className="flex flex-col items-center flex-1 group">
                  <div className="flex items-end gap-1 w-full h-64 mb-4">
                    <div className="w-1/2 bg-blue-500 rounded-t-sm transition-all duration-500 group-hover:bg-blue-400 relative" style={{ height: `${alturaVentas}%` }}>
                      <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-xs py-1 px-2 rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-10 font-bold">
                        V: ${dia.ventas}
                      </div>
                    </div>
                    <div className="w-1/2 bg-red-400 rounded-t-sm transition-all duration-500 group-hover:bg-red-300 relative" style={{ height: `${alturaCostos}%` }}>
                      <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-xs py-1 px-2 rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-10 font-bold">
                        C: ${dia.costos}
                      </div>
                    </div>
                  </div>
                  <span className="text-sm font-bold text-slate-500 uppercase">{dia.dia}</span>
                </div>
              );
            })}
          </div>
          <div className="flex justify-center gap-6 mt-4">
            <div className="flex items-center gap-2"><div className="w-3 h-3 bg-blue-500 rounded-full"></div><span className="text-sm font-bold text-slate-600">Ventas</span></div>
            <div className="flex items-center gap-2"><div className="w-3 h-3 bg-red-400 rounded-full"></div><span className="text-sm font-bold text-slate-600">Costos</span></div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex flex-col">
          <h3 className="text-xl font-bold text-slate-800 mb-6">Top 3 Productos</h3>
          <div className="flex-1 flex flex-col justify-center space-y-6">
            {(resumen.top_productos || []).map((p, idx) => {
              const maxCant = Math.max(...(resumen.top_productos || []).map(x => x.cantidad));
              const ancho = maxCant > 0 ? (p.cantidad / maxCant) * 100 : 0;
              return (
                <div key={idx} className="w-full">
                  <div className="flex justify-between mb-2">
                    <span className="text-sm font-bold text-slate-700">{p.nombre}</span>
                    <span className="text-sm font-black text-emerald-600">{p.cantidad} u.</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-3">
                    <div className="bg-emerald-500 h-3 rounded-full transition-all duration-1000" style={{ width: `${ancho}%` }}></div>
                  </div>
                </div>
              );
            })}
            {(!resumen.top_productos || resumen.top_productos.length === 0) && (
              <p className="text-slate-400 font-medium text-center italic">Aún no hay ventas suficientes</p>
            )}
          </div>
          <div className="mt-4 pt-4 border-t border-slate-100">
            <p className="text-sm font-medium text-slate-500 text-center">Basado en volumen de ventas histórico</p>
          </div>
        </div>
      </div>
    </div>
  );
};

const ProveedoresTab = () => {
  const [proveedores, setProveedores] = useState([]);
  const [materiasPrimas, setMateriasPrimas] = useState([]);
  const [mostrarModalProv, setMostrarModalProv] = useState(false);
  const [mostrarModalCompra, setMostrarModalCompra] = useState(false);
  const [proveedorSeleccionado, setProveedorSeleccionado] = useState(null);

  // Form states
  const [nuevoProv, setNuevoProv] = useState({ nombre: '', cuit: '', telefono: '' });
  const [nuevaCompra, setNuevaCompra] = useState({ materia_prima_id: '', cantidad_comprada: '', precio_total: '', metodo_pago: 'Efectivo' });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    const resProv = await api.get('/proveedores/');
    setProveedores(resProv.data);
    const resMp = await api.get('/materias-primas/');
    setMateriasPrimas(resMp.data);
  };

  const handleCrearProveedor = async (e) => {
    e.preventDefault();
    try {
      await api.post('/proveedores/', nuevoProv);
      setMostrarModalProv(false);
      setNuevoProv({ nombre: '', cuit: '', telefono: '' });
      fetchData();
    } catch (err) {
      alert("Error al crear proveedor");
    }
  };

  const handleRegistrarCompra = async (e) => {
    e.preventDefault();
    try {
      await api.post('/compras/', {
        proveedor_id: proveedorSeleccionado.id,
        materia_prima_id: parseInt(nuevaCompra.materia_prima_id),
        cantidad_comprada: parseFloat(nuevaCompra.cantidad_comprada),
        precio_total: parseFloat(nuevaCompra.precio_total),
        metodo_pago: nuevaCompra.metodo_pago
      });
      setMostrarModalCompra(false);
      setNuevaCompra({ materia_prima_id: '', cantidad_comprada: '', precio_total: '', metodo_pago: 'Efectivo' });
      fetchData();
    } catch (err) {
      alert("Error al registrar compra");
    }
  };

  return (
    <div className="space-y-6 relative">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-black text-slate-800">Proveedores y Compras</h2>
        <button 
          onClick={() => setMostrarModalProv(true)}
          className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-xl font-bold flex items-center gap-2">
          <PlusCircle className="w-5 h-5" /> Nuevo Proveedor
        </button>
      </div>
      
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-slate-50 text-slate-500 text-sm uppercase font-bold">
            <tr>
              <th className="p-4">Nombre</th>
              <th className="p-4">CUIT</th>
              <th className="p-4">Teléfono</th>
              <th className="p-4 text-right">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {proveedores.map(prov => (
              <tr key={prov.id} className="hover:bg-slate-50">
                <td className="p-4 font-bold text-slate-800">{prov.nombre}</td>
                <td className="p-4 text-slate-600">{prov.cuit || '-'}</td>
                <td className="p-4 text-slate-600">{prov.telefono || '-'}</td>
                <td className="p-4 text-right">
                  <button 
                    onClick={() => { setProveedorSeleccionado(prov); setMostrarModalCompra(true); }}
                    className="text-indigo-600 font-bold hover:underline">
                    Registrar Compra
                  </button>
                </td>
              </tr>
            ))}
            {proveedores.length === 0 && (
              <tr>
                <td colSpan="4" className="p-8 text-center text-slate-400 font-medium">No hay proveedores registrados.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Modal Nuevo Proveedor */}
      {mostrarModalProv && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md overflow-hidden">
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-2xl font-black text-slate-800">Nuevo Proveedor</h2>
            </div>
            <form onSubmit={handleCrearProveedor} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-bold text-slate-500 mb-2">Nombre *</label>
                <input required type="text" value={nuevoProv.nombre} onChange={e => setNuevoProv({...nuevoProv, nombre: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-500 mb-2">CUIT</label>
                <input type="text" value={nuevoProv.cuit} onChange={e => setNuevoProv({...nuevoProv, cuit: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-500 mb-2">Teléfono</label>
                <input type="text" value={nuevoProv.telefono} onChange={e => setNuevoProv({...nuevoProv, telefono: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
              </div>
              <div className="flex gap-4 pt-4">
                <button type="button" onClick={() => setMostrarModalProv(false)} className="flex-1 py-4 font-bold text-slate-500 bg-slate-100 hover:bg-slate-200 rounded-xl">Cancelar</button>
                <button type="submit" className="flex-1 py-4 font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl">Guardar</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Registrar Compra */}
      {mostrarModalCompra && proveedorSeleccionado && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md overflow-hidden">
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-2xl font-black text-slate-800">Comprar a {proveedorSeleccionado.nombre}</h2>
            </div>
            <form onSubmit={handleRegistrarCompra} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-bold text-slate-500 mb-2">Materia Prima *</label>
                <select required value={nuevaCompra.materia_prima_id} onChange={e => setNuevaCompra({...nuevaCompra, materia_prima_id: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800">
                  <option value="">Seleccionar insumo...</option>
                  {materiasPrimas.map(mp => (
                    <option key={mp.id} value={mp.id}>{mp.nombre}</option>
                  ))}
                </select>
              </div>
              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="block text-sm font-bold text-slate-500 mb-2">Cantidad (KG/L) *</label>
                  <input required type="number" step="0.01" min="0.01" value={nuevaCompra.cantidad_comprada} onChange={e => setNuevaCompra({...nuevaCompra, cantidad_comprada: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
                </div>
                <div className="flex-1">
                  <label className="block text-sm font-bold text-slate-500 mb-2">Precio Total ($) *</label>
                  <input required type="number" step="0.01" min="0" value={nuevaCompra.precio_total} onChange={e => setNuevaCompra({...nuevaCompra, precio_total: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-500 mb-2">Método de Pago *</label>
                <select required value={nuevaCompra.metodo_pago} onChange={e => setNuevaCompra({...nuevaCompra, metodo_pago: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800">
                  <option value="Efectivo">Efectivo</option>
                  <option value="Tarjeta">Tarjeta</option>
                  <option value="Transferencia">Transferencia</option>
                </select>
              </div>
              <div className="flex gap-4 pt-4">
                <button type="button" onClick={() => setMostrarModalCompra(false)} className="flex-1 py-4 font-bold text-slate-500 bg-slate-100 hover:bg-slate-200 rounded-xl">Cancelar</button>
                <button type="submit" className="flex-1 py-4 font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl">Confirmar Compra</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

const ConstruccionTab = ({ titulo }) => (
  <div className="p-12 text-center flex flex-col items-center">
    <PackageSearch className="w-24 h-24 text-slate-300 mb-4" />
    <h2 className="text-3xl font-black text-slate-800">{titulo}</h2>
    <p className="text-slate-500 mt-2 text-lg">Módulo en construcción. Se implementará próximamente.</p>
  </div>
);

const CatalogoCostosTab = () => {
  const [productos, setProductos] = useState([]);
  const [materiasPrimas, setMateriasPrimas] = useState([]);
  const [mostrarModalProd, setMostrarModalProd] = useState(false);
  const [nuevoProd, setNuevoProd] = useState({ producto_id: null, nombre: '', precio_venta: '', recetas: [] });
  const [nuevoInsumoReceta, setNuevoInsumoReceta] = useState({ materia_prima_id: '', cantidad_necesaria: '' });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const res = await api.get('/productos/costeo');
      setProductos(res.data);
      const resMp = await api.get('/materias-primas/');
      setMateriasPrimas(resMp.data);
    } catch (err) {
      console.error("Error:", err);
    }
  };

  const agregarInsumo = () => {
    if (!nuevoInsumoReceta.materia_prima_id || !nuevoInsumoReceta.cantidad_necesaria) return;
    setNuevoProd({
      ...nuevoProd,
      recetas: [...nuevoProd.recetas, { ...nuevoInsumoReceta }]
    });
    setNuevoInsumoReceta({ materia_prima_id: '', cantidad_necesaria: '' });
  };

  const handleOcultarProducto = async (productoId) => {
    if(!window.confirm("¿Estás seguro de ocultar/dar de baja este producto? No aparecerá en caja pero mantendrá el historial.")) return;
    try {
      await api.delete(`/productos/${productoId}`);
      fetchData();
    } catch (err) {
      alert("Error al ocultar producto");
    }
  };

  const handleCrearProducto = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        nombre: nuevoProd.nombre,
        precio_venta: parseFloat(nuevoProd.precio_venta),
        recetas: nuevoProd.recetas.map(r => ({
          materia_prima_id: parseInt(r.materia_prima_id),
          cantidad_necesaria: parseFloat(r.cantidad_necesaria)
        }))
      };

      if (nuevoProd.producto_id) {
        // Edit
        await api.put(`/productos/${nuevoProd.producto_id}`, payload);
      } else {
        // Create
        payload.stock_mostrador = 0; // Solo al crear
        const res = await api.post('/productos/', payload);
        const productoId = res.data.id;
        // In the backend, recipes are added inside the PUT. For POST, we might need to add them separately since backend POST /productos doesn't handle recipes in the payload natively yet.
        // Wait, the backend POST /productos/ takes schemas.ProductoCreate which does not have recetas!
        // We will call the separate /recetas/ endpoint for new products just like before.
        for (const receta of nuevoProd.recetas) {
          await api.post('/recetas/', {
            producto_id: productoId,
            materia_prima_id: parseInt(receta.materia_prima_id),
            cantidad_necesaria: parseFloat(receta.cantidad_necesaria)
          });
        }
      }

      setMostrarModalProd(false);
      setNuevoProd({ producto_id: null, nombre: '', precio_venta: '', recetas: [] });
      fetchData();
    } catch (err) {
      alert("Error al guardar producto");
    }
  };

  const handleCambiarPrecio = async (e) => {
    e.preventDefault();
    try {
      await api.put(`/productos/${prodSeleccionado.producto_id}/precio`, {
        nuevo_precio: parseFloat(nuevoPrecio)
      });
      setMostrarModalPrecio(false);
      setNuevoPrecio('');
      fetchData();
    } catch (err) {
      alert("Error al cambiar precio");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-black text-slate-800">Catálogo y Costos (Ingeniería de Menú)</h2>
        <button 
          onClick={() => { setNuevoProd({ producto_id: null, nombre: '', precio_venta: '', recetas: [] }); setMostrarModalProd(true); }}
          className="bg-emerald-600 hover:bg-emerald-700 text-white px-6 py-3 rounded-xl font-bold flex items-center gap-2">
          <PlusCircle className="w-5 h-5" /> Nuevo Producto
        </button>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-slate-50 text-slate-500 text-sm uppercase font-bold">
            <tr>
              <th className="p-4">Producto</th>
              <th className="p-4">Precio Venta</th>
              <th className="p-4">Costo Receta</th>
              <th className="p-4">Margen Ganancia</th>
              <th className="p-4">% Margen</th>
              <th className="p-4 text-right">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {productos.map(prod => (
              <tr key={prod.producto_id} className="hover:bg-slate-50">
                <td className="p-4 font-bold text-slate-800">{prod.nombre}</td>
                <td className="p-4 text-slate-800 font-bold">${prod.precio_venta}</td>
                <td className="p-4 text-orange-600 font-medium">${prod.costo_receta}</td>
                <td className="p-4 text-emerald-600 font-bold">${prod.margen_ganancia}</td>
                <td className="p-4 text-emerald-600 font-bold">{prod.porcentaje_margen}%</td>
                <td className="p-4 text-right">
                  <div className="flex justify-end gap-3 items-center">
                    <button 
                      onClick={() => { 
                        setNuevoProd({ 
                          producto_id: prod.producto_id, 
                          nombre: prod.nombre, 
                          precio_venta: prod.precio_venta, 
                          recetas: prod.recetas || [] 
                        }); 
                        setMostrarModalProd(true); 
                      }}
                      className="text-indigo-600 font-bold hover:underline">
                      Editar / Receta
                    </button>
                    <button 
                      onClick={() => handleOcultarProducto(prod.producto_id)}
                      className="text-red-500 hover:text-red-700 transition-colors"
                      title="Dar de baja / Ocultar">
                      <Trash2 className="w-5 h-5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal Nuevo/Editar Producto */}
      {mostrarModalProd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-2xl font-black text-slate-800">{nuevoProd.producto_id ? 'Editar Producto' : 'Crear Nuevo Producto'}</h2>
            </div>
            <form onSubmit={handleCrearProducto} className="p-6 space-y-4">
              <div className="flex gap-4">
                <div className="flex-2 w-2/3">
                  <label className="block text-sm font-bold text-slate-500 mb-2">Nombre del Producto *</label>
                  <input required type="text" value={nuevoProd.nombre} onChange={e => setNuevoProd({...nuevoProd, nombre: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
                </div>
                <div className="flex-1 w-1/3">
                  <label className="block text-sm font-bold text-slate-500 mb-2">Precio Venta ($) *</label>
                  <input required type="number" step="0.01" value={nuevoProd.precio_venta} onChange={e => setNuevoProd({...nuevoProd, precio_venta: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
                </div>
              </div>
              
              <div className="mt-6 border-t border-slate-100 pt-6">
                <h3 className="text-lg font-bold text-slate-800 mb-4">Ingeniería de Menú (Receta)</h3>
                <div className="flex gap-2 mb-4">
                  <select value={nuevoInsumoReceta.materia_prima_id} onChange={e => setNuevoInsumoReceta({...nuevoInsumoReceta, materia_prima_id: e.target.value})} className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800">
                    <option value="">Seleccionar insumo...</option>
                    {materiasPrimas.map(mp => (
                      <option key={mp.id} value={mp.id}>{mp.nombre}</option>
                    ))}
                  </select>
                  <input type="number" step="0.01" placeholder="Cant. (KG/L)" value={nuevoInsumoReceta.cantidad_necesaria} onChange={e => setNuevoInsumoReceta({...nuevoInsumoReceta, cantidad_necesaria: e.target.value})} className="w-32 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
                  <button type="button" onClick={agregarInsumo} className="bg-slate-800 text-white px-4 rounded-xl font-bold">Agregar</button>
                </div>
                <ul className="space-y-2">
                  {nuevoProd.recetas.map((r, i) => {
                    const mp = materiasPrimas.find(m => m.id == r.materia_prima_id);
                    return (
                      <li key={i} className="flex justify-between items-center bg-slate-50 p-3 rounded-lg border border-slate-100">
                        <span className="font-bold text-slate-700">{mp?.nombre}</span>
                        <div className="flex items-center gap-4">
                          <span className="text-slate-500 font-medium">{r.cantidad_necesaria} {mp?.unidad_medida}</span>
                          <button type="button" onClick={() => setNuevoProd({...nuevoProd, recetas: nuevoProd.recetas.filter((_, idx) => idx !== i)})} className="text-red-500 hover:text-red-700 font-bold text-sm">Quitar</button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>

              <div className="flex gap-4 pt-4 mt-6 border-t border-slate-100">
                <button type="button" onClick={() => setMostrarModalProd(false)} className="flex-1 py-4 font-bold text-slate-500 bg-slate-100 hover:bg-slate-200 rounded-xl">Cancelar</button>
                <button type="submit" className="flex-1 py-4 font-bold text-white bg-emerald-600 hover:bg-emerald-700 rounded-xl">{nuevoProd.producto_id ? 'Guardar Cambios' : 'Crear Producto'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

const AuditoriaInventarioTab = () => {
  const [materiasPrimas, setMateriasPrimas] = useState([]);
  const [auditorias, setAuditorias] = useState([]);
  const [mermas, setMermas] = useState([]);
  const [mostrarModalMP, setMostrarModalMP] = useState(false);
  const [nuevaMP, setNuevaMP] = useState({ id: null, nombre: '', stock_actual_kg: '', unidad_medida: 'KG' });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const resMp = await api.get('/materias-primas/');
      const resAud = await api.get('/inventario/auditorias');
      const resMer = await api.get('/mermas/');
      setMateriasPrimas(resMp.data);
      setAuditorias(resAud.data);
      setMermas(resMer.data);
    } catch (err) {
      console.error("Error al cargar auditorias:", err);
    }
  };

  const handleCrearMP = async (e) => {
    e.preventDefault();
    try {
      if (nuevaMP.id) {
        await api.put(`/materias-primas/${nuevaMP.id}`, {
          nombre: nuevaMP.nombre,
          stock_actual_kg: parseFloat(nuevaMP.stock_actual_kg),
          unidad_medida: nuevaMP.unidad_medida
        });
      } else {
        await api.post('/materias-primas/', {
          nombre: nuevaMP.nombre,
          stock_actual_kg: parseFloat(nuevaMP.stock_actual_kg),
          unidad_medida: nuevaMP.unidad_medida
        });
      }
      setMostrarModalMP(false);
      setNuevaMP({ id: null, nombre: '', stock_actual_kg: '', unidad_medida: 'KG' });
      fetchData();
    } catch (err) {
      alert("Error al guardar materia prima");
    }
  };

  const handleEliminarMP = async (id) => {
    if(!window.confirm("¿Estás seguro de ocultar esta materia prima?")) return;
    try {
      await api.delete(`/materias-primas/${id}`);
      fetchData();
    } catch (err) {
      alert("Error al eliminar");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-black text-slate-800">Auditoría Físico vs Teórico</h2>
        <div className="flex gap-3">
          <button 
            onClick={() => setMostrarModalMP(true)}
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-3 rounded-xl font-bold flex items-center gap-2">
            <PlusCircle className="w-5 h-5" /> Nueva Materia Prima
          </button>
          <button className="bg-red-600 hover:bg-red-700 text-white px-6 py-3 rounded-xl font-bold flex items-center gap-2">
            <ClipboardCheck className="w-5 h-5" /> Registrar Conteo Físico
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
          <h3 className="text-xl font-bold text-slate-800 mb-4">Stock Teórico Actual</h3>
          <ul className="divide-y divide-slate-100">
            {materiasPrimas.map(mp => (
              <li key={mp.id} className="py-3 flex justify-between items-center group">
                <div>
                  <span className="font-medium text-slate-600 block">{mp.nombre}</span>
                  <span className="text-xs text-slate-400 font-bold">{mp.stock_actual_kg} {mp.unidad_medida}</span>
                </div>
                <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button onClick={() => { setNuevaMP(mp); setMostrarModalMP(true); }} className="text-blue-500 hover:text-blue-700 text-sm font-bold">Editar</button>
                  <button onClick={() => handleEliminarMP(mp.id)} className="text-red-500 hover:text-red-700 text-sm font-bold">Ocultar</button>
                </div>
              </li>
            ))}
            {materiasPrimas.length === 0 && <li className="py-4 text-slate-400">No hay materias primas registradas.</li>}
          </ul>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
          <h3 className="text-xl font-bold text-slate-800 mb-4">Registro Histórico de Mermas (Bajas)</h3>
          <ul className="divide-y divide-slate-100 max-h-64 overflow-y-auto pr-2">
            {mermas.length > 0 ? mermas.map(m => (
              <li key={m.id} className="py-3 flex flex-col gap-1">
                <div className="flex justify-between items-center">
                  <span className="font-bold text-slate-700">{m.producto}</span>
                  <span className="text-red-600 font-black">-{m.cantidad}</span>
                </div>
                <div className="flex justify-between text-xs text-slate-400">
                  <span>{new Date(m.fecha).toLocaleString()}</span>
                  <span>{m.motivo} ({m.usuario})</span>
                </div>
              </li>
            )) : <li className="py-4 text-slate-400 text-sm text-center font-medium">No hay mermas registradas.</li>}
          </ul>
        </div>
      </div>

      {/* Modal Nueva Materia Prima */}
      {mostrarModalMP && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-sm overflow-hidden">
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-2xl font-black text-slate-800">Nueva Materia Prima</h2>
            </div>
            <form onSubmit={handleCrearMP} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-bold text-slate-500 mb-2">Nombre *</label>
                <input required autoFocus type="text" value={nuevaMP.nombre} onChange={e => setNuevaMP({...nuevaMP, nombre: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
              </div>
              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="block text-sm font-bold text-slate-500 mb-2">Unidad *</label>
                  <select required value={nuevaMP.unidad_medida} onChange={e => setNuevaMP({...nuevaMP, unidad_medida: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800">
                    <option value="KG">KG</option>
                    <option value="LT">Litros</option>
                    <option value="UN">Unidades</option>
                  </select>
                </div>
                <div className="flex-1">
                  <label className="block text-sm font-bold text-slate-500 mb-2">Stock Inicial *</label>
                  <input required type="number" step="0.01" min="0" value={nuevaMP.stock_actual_kg} onChange={e => setNuevaMP({...nuevaMP, stock_actual_kg: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
                </div>
              </div>
              <div className="flex gap-4 pt-4">
                <button type="button" onClick={() => setMostrarModalMP(false)} className="flex-1 py-4 font-bold text-slate-500 bg-slate-100 hover:bg-slate-200 rounded-xl">Cancelar</button>
                <button type="submit" className="flex-1 py-4 font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl">Crear</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

const GastosTab = () => {
  const [gastos, setGastos] = useState([]);
  const [mostrarModal, setMostrarModal] = useState(false);
  const [nuevoGasto, setNuevoGasto] = useState({ concepto: '', monto: '', metodo_pago: 'Efectivo' });

  const fetchGastos = async () => {
    try {
      const res = await api.get('/gastos/');
      setGastos(res.data);
    } catch (err) {
      console.error("Error al cargar gastos:", err);
    }
  };

  useEffect(() => {
    fetchGastos();
  }, []);

  const handleRegistrarGasto = async (e) => {
    e.preventDefault();
    try {
      await api.post('/gastos/', {
        concepto: nuevoGasto.concepto,
        monto: parseFloat(nuevoGasto.monto),
        metodo_pago: nuevoGasto.metodo_pago
      });
      setMostrarModal(false);
      setNuevoGasto({ concepto: '', monto: '', metodo_pago: 'Efectivo' });
      fetchGastos();
    } catch (err) {
      alert("Error al registrar gasto");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-black text-slate-800">Flujo de Caja (Gastos)</h2>
        <button 
          onClick={() => setMostrarModal(true)}
          className="bg-red-600 hover:bg-red-700 text-white px-6 py-3 rounded-xl font-bold flex items-center gap-2">
          <Wallet className="w-5 h-5" /> Registrar Gasto
        </button>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-slate-50 text-slate-500 text-sm uppercase font-bold">
            <tr>
              <th className="p-4">Fecha</th>
              <th className="p-4">Concepto</th>
              <th className="p-4">Método de Pago</th>
              <th className="p-4 text-right">Monto</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {gastos.map(g => (
              <tr key={g.id} className="hover:bg-slate-50">
                <td className="p-4 text-slate-600">{new Date(g.fecha).toLocaleDateString()}</td>
                <td className="p-4 font-bold text-slate-800">{g.concepto}</td>
                <td className="p-4 text-slate-600">{g.metodo_pago}</td>
                <td className="p-4 text-red-600 font-bold text-right">${g.monto}</td>
              </tr>
            ))}
            {gastos.length === 0 && (
              <tr>
                <td colSpan="4" className="p-8 text-center text-slate-400 font-medium">No hay gastos registrados.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {mostrarModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md overflow-hidden">
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-2xl font-black text-slate-800">Registrar Gasto</h2>
            </div>
            <form onSubmit={handleRegistrarGasto} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-bold text-slate-500 mb-2">Concepto (Luz, Gas, Sueldos) *</label>
                <input required type="text" value={nuevoGasto.concepto} onChange={e => setNuevoGasto({...nuevoGasto, concepto: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-500 mb-2">Monto ($) *</label>
                <input required type="number" step="0.01" min="0" value={nuevoGasto.monto} onChange={e => setNuevoGasto({...nuevoGasto, monto: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800" />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-500 mb-2">Método de Pago *</label>
                <select required value={nuevoGasto.metodo_pago} onChange={e => setNuevoGasto({...nuevoGasto, metodo_pago: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-800">
                  <option value="Efectivo">Efectivo</option>
                  <option value="Tarjeta">Tarjeta</option>
                  <option value="Transferencia">Transferencia</option>
                </select>
              </div>
              <div className="flex gap-4 pt-4">
                <button type="button" onClick={() => setMostrarModal(false)} className="flex-1 py-4 font-bold text-slate-500 bg-slate-100 hover:bg-slate-200 rounded-xl">Cancelar</button>
                <button type="submit" className="flex-1 py-4 font-bold text-white bg-red-600 hover:bg-red-700 rounded-xl">Registrar</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

const AuditoriaPersonalTab = () => {
  const [arqueos, setArqueos] = useState([]);

  useEffect(() => {
    const fetchArqueos = async () => {
      try {
        const res = await api.get('/arqueos/');
        setArqueos(res.data);
      } catch (err) {
        console.error("Error al cargar arqueos:", err);
      }
    };
    fetchArqueos();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-black text-slate-800">Auditoría de Personal (Cierres de Caja)</h2>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-slate-50 text-slate-500 text-sm uppercase font-bold">
            <tr>
              <th className="p-4">ID Turno</th>
              <th className="p-4">Fondo Inicial</th>
              <th className="p-4">Total Reportado (Ciego)</th>
              <th className="p-4">Total Real (Sistema)</th>
              <th className="p-4 text-right">Diferencia</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {arqueos.map(arq => (
              <tr key={arq.id} className="hover:bg-slate-50">
                <td className="p-4 font-bold text-slate-800">#{arq.turno_id}</td>
                <td className="p-4 text-slate-600">${arq.fondo_inicial}</td>
                <td className="p-4 font-bold text-slate-800">${arq.total_ingresado_cajero}</td>
                <td className="p-4 font-bold text-slate-800">${arq.total_calculado_sistema}</td>
                <td className={`p-4 font-black text-right ${arq.diferencia < 0 ? 'text-red-600' : (arq.diferencia > 0 ? 'text-emerald-600' : 'text-slate-400')}`}>
                  {arq.diferencia > 0 ? '+' : ''}{arq.diferencia}
                </td>
              </tr>
            ))}
            {arqueos.length === 0 && (
              <tr>
                <td colSpan="5" className="p-8 text-center text-slate-400 font-medium">No hay cierres de caja registrados.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ==========================================
// COMPONENTE PRINCIPAL (PANEL ADMIN)
// ==========================================

const PanelAdmin = () => {
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem('adminActiveTab') || 'dashboard');

  useEffect(() => {
    localStorage.setItem('adminActiveTab', activeTab);
  }, [activeTab]);

  const menuItems = [
    { id: 'dashboard', label: 'Resumen y Finanzas', icon: <LayoutDashboard /> },
    { id: 'catalogo', label: 'Ingeniería de Menú (Costos)', icon: <BookOpen /> },
    { id: 'proveedores', label: 'Proveedores y Compras', icon: <Truck /> },
    { id: 'auditoria', label: 'Auditoría de Inventario', icon: <ClipboardCheck /> },
    { id: 'gastos', label: 'Gastos Varios', icon: <Wallet /> },
    { id: 'rrhh', label: 'Personal y Accesos', icon: <Users /> },
  ];

  return (
    <div className="flex min-h-screen bg-slate-50 font-sans">
      {/* Sidebar de Navegación */}
      <div className="w-80 bg-slate-900 text-white shadow-2xl flex flex-col">
        <div className="p-8 border-b border-slate-800">
          <h1 className="text-2xl font-black text-white leading-tight">Centro de<br/><span className="text-indigo-400">Comando</span></h1>
          <p className="text-slate-400 text-sm mt-2 font-medium">Módulo Contador / Dueño</p>
        </div>

        <nav className="flex-1 p-4 space-y-2">
          {menuItems.map(item => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center gap-3 px-4 py-4 rounded-xl font-bold transition-all text-left ${
                activeTab === item.id 
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30' 
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <div className={activeTab === item.id ? 'text-white' : 'text-slate-500'}>
                {React.cloneElement(item.icon, { className: 'w-6 h-6' })}
              </div>
              {item.label}
            </button>
          ))}
        </nav>
        
        <div className="p-4 border-t border-slate-800 text-center">
          <p className="text-xs text-slate-500 font-medium">ERP Panadería v2.0</p>
        </div>
      </div>

      {/* Contenido Principal */}
      <div className="flex-1 p-10 overflow-y-auto">
        {activeTab === 'dashboard' && <DashboardTab />}
        {activeTab === 'catalogo' && <CatalogoCostosTab />}
        {activeTab === 'proveedores' && <ProveedoresTab />}
        {activeTab === 'auditoria' && <AuditoriaInventarioTab />}
        {activeTab === 'gastos' && <GastosTab />}
        {activeTab === 'rrhh' && <AuditoriaPersonalTab />}
      </div>
    </div>
  );
};

export default PanelAdmin;
