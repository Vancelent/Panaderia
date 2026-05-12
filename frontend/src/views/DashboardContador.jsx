import { useEffect, useState } from 'react';
import { LayoutDashboard, Wheat, Tag, Activity, TrendingUp, TrendingDown, Plus, AlertTriangle, CheckCircle2, Link as LinkIcon, PieChart } from 'lucide-react';
import api from '../api/api';

const DashboardContador = () => {
    const [activeTab, setActiveTab] = useState('Panel General');
    
    // Estados para las listas de datos
    const [materiasPrimas, setMateriasPrimas] = useState([]);
    const [productos, setProductos] = useState([]);
    
    // Estados de UI
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [successMsg, setSuccessMsg] = useState(null);

    // Estados para los formularios
    const [formMP, setFormMP] = useState({ nombre: '', unidad_medida: 'kg', costo_actual: '', stock_actual: '' });
    const [formProd, setFormProd] = useState({ nombre: '', precio_venta: '' });

    // Cargar datos según la pestaña activa
    const fetchData = async () => {
        if (activeTab === 'Panel General') return;
        
        setLoading(true);
        setError(null);
        try {
            if (activeTab === 'Materias Primas') {
                const res = await api.get('/materias-primas/');
                setMateriasPrimas(res.data);
            } else if (activeTab === 'Catálogo y Recetas') {
                const res = await api.get('/productos/');
                setProductos(res.data);
            }
        } catch (err) {
            setError(err.response?.data?.detail || "Error al conectar con el servidor.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeTab]);

    // Función para crear Materia Prima
    const handleCreateMP = async (e) => {
        e.preventDefault();
        setError(null);
        setSuccessMsg(null);
        try {
            await api.post('/materias-primas/', {
                nombre: formMP.nombre,
                stock_actual_kg: parseFloat(formMP.stock_actual),
                unidad_medida: formMP.unidad_medida
                // Nota: El backend actual no tiene costo_actual en el modelo, pero lo mantenemos en UI a futuro.
            });
            setSuccessMsg("Insumo registrado exitosamente en el depósito.");
            setFormMP({ nombre: '', unidad_medida: 'kg', costo_actual: '', stock_actual: '' });
            fetchData();
        } catch (err) {
            setError(err.response?.data?.detail || "Error al registrar el insumo.");
        }
    };

    // Función para crear Producto
    const handleCreateProd = async (e) => {
        e.preventDefault();
        setError(null);
        setSuccessMsg(null);
        try {
            await api.post('/productos/', {
                nombre: formProd.nombre,
                precio_venta: parseFloat(formProd.precio_venta),
                stock_mostrador: 0 // Inicia en 0. El stock lo dictamina el Panadero mediante lotes.
            });
            setSuccessMsg("Producto definido exitosamente.");
            setFormProd({ nombre: '', precio_venta: '' });
            fetchData();
        } catch (err) {
            setError(err.response?.data?.detail || "Error al definir el producto.");
        }
    };

    return (
        <div className="min-h-screen bg-slate-900 p-8 font-sans text-slate-100">
            <div className="max-w-7xl mx-auto space-y-6">

                {/* Cabecera Torre de Control */}
                <div className="flex items-center gap-5 bg-slate-800 p-6 rounded-3xl border border-slate-700 shadow-2xl">
                    <div className="p-4 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl shadow-lg">
                        <Activity className="w-8 h-8 text-white" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-black text-white tracking-tight">Torre de Control Administrativa</h1>
                        <p className="text-indigo-300 font-medium mt-1">Visión global del negocio: Métricas, Insumos y Productos.</p>
                    </div>
                </div>

                {/* Mensajes de Notificación */}
                {error && (
                    <div className="bg-red-500/10 text-red-400 px-6 py-4 rounded-2xl font-medium flex items-center gap-3 border border-red-500/20 backdrop-blur-sm">
                        <AlertTriangle className="w-5 h-5 flex-shrink-0" /> {error}
                    </div>
                )}
                {successMsg && (
                    <div className="bg-emerald-500/10 text-emerald-400 px-6 py-4 rounded-2xl font-bold flex items-center gap-3 border border-emerald-500/20 backdrop-blur-sm">
                        <CheckCircle2 className="w-5 h-5 flex-shrink-0" /> {successMsg}
                    </div>
                )}

                {/* Navegación por Pestañas */}
                <div className="flex gap-2 border-b border-slate-700 pb-px">
                    {[
                        { id: 'Panel General', icon: LayoutDashboard },
                        { id: 'Materias Primas', icon: Wheat },
                        { id: 'Catálogo y Recetas', icon: Tag }
                    ].map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`flex items-center gap-2 px-6 py-4 text-sm font-bold tracking-wider transition-all rounded-t-xl ${
                                activeTab === tab.id
                                    ? 'bg-slate-800 text-indigo-400 border-t-2 border-x-2 border-slate-700 border-b-2 border-b-slate-800'
                                    : 'bg-transparent text-slate-500 hover:text-slate-300 hover:bg-slate-800/50 border-2 border-transparent'
                            }`}
                        >
                            <tab.icon className="w-5 h-5" />
                            {tab.id}
                        </button>
                    ))}
                </div>

                {/* Contenedor Principal */}
                <div className="bg-slate-800 rounded-3xl shadow-2xl border border-slate-700 overflow-hidden min-h-[500px]">
                    
                    {/* -- SECCIÓN 1: PANEL GENERAL (Placeholder) -- */}
                    {activeTab === 'Panel General' && (
                        <div className="p-10 space-y-8">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                <div className="bg-slate-700/50 p-6 rounded-2xl border border-slate-600/50 flex flex-col justify-between h-32">
                                    <div className="flex justify-between items-start text-slate-400">
                                        <span className="font-bold text-sm uppercase tracking-wider">Ingresos del Día</span>
                                        <TrendingUp className="w-5 h-5 text-emerald-400" />
                                    </div>
                                    <div className="text-3xl font-black text-white blur-sm select-none opacity-50">
                                        $ 0.00
                                    </div>
                                </div>
                                <div className="bg-slate-700/50 p-6 rounded-2xl border border-slate-600/50 flex flex-col justify-between h-32">
                                    <div className="flex justify-between items-start text-slate-400">
                                        <span className="font-bold text-sm uppercase tracking-wider">Mermas / Pérdidas</span>
                                        <TrendingDown className="w-5 h-5 text-red-400" />
                                    </div>
                                    <div className="text-3xl font-black text-white blur-sm select-none opacity-50">
                                        $ 0.00
                                    </div>
                                </div>
                                <div className="bg-slate-700/50 p-6 rounded-2xl border border-slate-600/50 flex flex-col justify-between h-32">
                                    <div className="flex justify-between items-start text-slate-400">
                                        <span className="font-bold text-sm uppercase tracking-wider">Turnos Activos</span>
                                        <Activity className="w-5 h-5 text-indigo-400" />
                                    </div>
                                    <div className="text-3xl font-black text-white blur-sm select-none opacity-50">
                                        0
                                    </div>
                                </div>
                            </div>

                            <div className="bg-slate-700/30 p-8 rounded-2xl border border-slate-600/30 h-64 flex flex-col items-center justify-center text-slate-500">
                                <PieChart className="w-16 h-16 mb-4 opacity-20" />
                                <h3 className="text-xl font-bold">Gráficos Financieros</h3>
                                <p className="mt-2 text-sm">Esta sección se conectará a los endpoints de reportes analíticos próximamente.</p>
                            </div>
                        </div>
                    )}

                    {/* -- SECCIÓN 2: MATERIAS PRIMAS -- */}
                    {activeTab === 'Materias Primas' && (
                        <div className="flex flex-col lg:flex-row h-full">
                            
                            <div className="w-full lg:w-1/3 bg-slate-800/80 p-8 border-r border-slate-700">
                                <h2 className="text-xl font-black text-white mb-6 flex items-center gap-2">
                                    <Plus className="w-6 h-6 text-amber-500" /> Nuevo Insumo
                                </h2>
                                <form onSubmit={handleCreateMP} className="space-y-5">
                                    <div>
                                        <label className="block text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Nombre</label>
                                        <input
                                            type="text"
                                            required
                                            value={formMP.nombre}
                                            onChange={e => setFormMP({...formMP, nombre: e.target.value})}
                                            className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 outline-none transition-all text-white"
                                            placeholder="Ej. Harina 0000"
                                        />
                                    </div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Stock Actual</label>
                                            <input
                                                type="number"
                                                step="0.01"
                                                required
                                                value={formMP.stock_actual}
                                                onChange={e => setFormMP({...formMP, stock_actual: e.target.value})}
                                                className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 outline-none transition-all text-white"
                                                placeholder="0.00"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Medida</label>
                                            <select
                                                value={formMP.unidad_medida}
                                                onChange={e => setFormMP({...formMP, unidad_medida: e.target.value})}
                                                className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 outline-none transition-all text-white"
                                            >
                                                <option value="kg">Kilogramos (kg)</option>
                                                <option value="litros">Litros (L)</option>
                                                <option value="unidades">Unidades (u)</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Costo Promedio ($)</label>
                                        <input
                                            type="number"
                                            step="0.01"
                                            value={formMP.costo_actual}
                                            onChange={e => setFormMP({...formMP, costo_actual: e.target.value})}
                                            className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 outline-none transition-all text-white"
                                            placeholder="0.00"
                                        />
                                    </div>
                                    <button type="submit" disabled={loading} className="w-full py-4 mt-4 bg-amber-500 hover:bg-amber-600 text-slate-900 font-black rounded-xl shadow-lg shadow-amber-500/20 transition-all">
                                        Registrar Insumo
                                    </button>
                                </form>
                            </div>

                            <div className="w-full lg:w-2/3 p-0 bg-slate-900/30">
                                {loading ? (
                                    <div className="p-12 text-center text-slate-500 font-medium animate-pulse">Cargando inventario de depósito...</div>
                                ) : (
                                    <table className="w-full text-left border-collapse">
                                        <thead>
                                            <tr className="bg-slate-900 text-slate-400 uppercase text-xs tracking-wider font-bold border-b border-slate-700">
                                                <th className="py-5 px-8">Insumo Base</th>
                                                <th className="py-5 px-8 text-right">Stock Depósito</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-800/50">
                                            {materiasPrimas.length === 0 ? (
                                                <tr><td colSpan="2" className="py-16 text-center text-slate-500 font-medium">El depósito está vacío.</td></tr>
                                            ) : (
                                                materiasPrimas.map(mp => (
                                                    <tr key={mp.id} className="hover:bg-slate-800/50 transition-colors group">
                                                        <td className="py-4 px-8 font-bold text-white flex items-center gap-3">
                                                            <div className="w-2 h-2 rounded-full bg-amber-500 opacity-50 group-hover:opacity-100 transition-all"></div>
                                                            {mp.nombre}
                                                        </td>
                                                        <td className="py-4 px-8 text-right font-black text-amber-400">
                                                            {mp.stock_actual_kg.toFixed(2)} <span className="text-slate-500 text-xs">{mp.unidad_medida}</span>
                                                        </td>
                                                    </tr>
                                                ))
                                            )}
                                        </tbody>
                                    </table>
                                )}
                            </div>
                        </div>
                    )}

                    {/* -- SECCIÓN 3: CATÁLOGO Y RECETAS -- */}
                    {activeTab === 'Catálogo y Recetas' && (
                        <div className="flex flex-col lg:flex-row h-full">
                            
                            <div className="w-full lg:w-1/3 bg-slate-800/80 p-8 border-r border-slate-700">
                                <h2 className="text-xl font-black text-white mb-6 flex items-center gap-2">
                                    <Plus className="w-6 h-6 text-indigo-400" /> Definir Producto Final
                                </h2>
                                <form onSubmit={handleCreateProd} className="space-y-5">
                                    <div>
                                        <label className="block text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Nombre Comercial</label>
                                        <input
                                            type="text"
                                            required
                                            value={formProd.nombre}
                                            onChange={e => setFormProd({...formProd, nombre: e.target.value})}
                                            className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 outline-none transition-all text-white"
                                            placeholder="Ej. Docena de Facturas"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Precio de Venta ($)</label>
                                        <input
                                            type="number"
                                            step="0.01"
                                            min="0"
                                            required
                                            value={formProd.precio_venta}
                                            onChange={e => setFormProd({...formProd, precio_venta: e.target.value})}
                                            className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 outline-none transition-all text-white font-mono"
                                            placeholder="0.00"
                                        />
                                    </div>
                                    <div className="pt-2">
                                        <div className="p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-xs text-indigo-300 font-medium">
                                            ℹ️ El stock en mostrador de este producto iniciará en 0. Será incrementado cuando el área de Producción registre un Lote.
                                        </div>
                                    </div>
                                    <button type="submit" disabled={loading} className="w-full py-4 mt-2 bg-indigo-500 hover:bg-indigo-600 text-white font-black rounded-xl shadow-lg shadow-indigo-500/20 transition-all">
                                        Guardar Definición
                                    </button>
                                </form>
                            </div>

                            <div className="w-full lg:w-2/3 p-0 bg-slate-900/30">
                                {loading ? (
                                    <div className="p-12 text-center text-slate-500 font-medium animate-pulse">Cargando catálogo comercial...</div>
                                ) : (
                                    <table className="w-full text-left border-collapse">
                                        <thead>
                                            <tr className="bg-slate-900 text-slate-400 uppercase text-xs tracking-wider font-bold border-b border-slate-700">
                                                <th className="py-5 px-8">Producto</th>
                                                <th className="py-5 px-8 text-right">Precio Actual</th>
                                                <th className="py-5 px-8 text-center">Ingeniería</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-800/50">
                                            {productos.length === 0 ? (
                                                <tr><td colSpan="3" className="py-16 text-center text-slate-500 font-medium">No hay productos definidos.</td></tr>
                                            ) : (
                                                productos.map(prod => (
                                                    <tr key={prod.id} className="hover:bg-slate-800/50 transition-colors group">
                                                        <td className="py-4 px-8 font-bold text-white flex items-center gap-3">
                                                            <div className="w-2 h-2 rounded-full bg-indigo-500 opacity-50 group-hover:opacity-100 transition-all"></div>
                                                            {prod.nombre}
                                                        </td>
                                                        <td className="py-4 px-8 text-right font-black text-emerald-400 font-mono">
                                                            ${prod.precio_venta.toFixed(2)}
                                                        </td>
                                                        <td className="py-4 px-8 text-center">
                                                            <button 
                                                                disabled
                                                                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 text-slate-400 font-bold text-xs border border-slate-700 hover:border-slate-600 transition-all cursor-not-allowed opacity-60"
                                                                title="Próximamente"
                                                            >
                                                                <LinkIcon className="w-3 h-3" />
                                                                Asignar Receta
                                                            </button>
                                                        </td>
                                                    </tr>
                                                ))
                                            )}
                                        </tbody>
                                    </table>
                                )}
                            </div>
                        </div>
                    )}

                </div>
            </div>
        </div>
    );
};

export default DashboardContador;
