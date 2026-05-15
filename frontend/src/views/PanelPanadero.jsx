import { useState, useEffect } from 'react';
import { ChefHat, CheckCircle2, AlertTriangle, PlusCircle } from 'lucide-react';
import api from '../api/api';

const PanelPanadero = () => {
    const [productos, setProductos] = useState([]);
    const [productoSeleccionado, setProductoSeleccionado] = useState('');
    const [cantidad, setCantidad] = useState('');

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMsg, setSuccessMsg] = useState('');

    useEffect(() => {
        const fetchProductos = async () => {
            try {
                const res = await api.get('/productos/');
                setProductos(res.data);
            } catch (err) {
                setError("Error al cargar la lista de productos.");
            }
        };
        fetchProductos();
    }, []);

    const handleRegistrarTanda = async (e) => {
        e.preventDefault();
        setError('');
        setSuccessMsg('');

        if (!productoSeleccionado || !cantidad || cantidad <= 0) {
            setError('Por favor, selecciona un producto y una cantidad válida.');
            return;
        }

        setLoading(true);
        try {
            const payload = {
                producto_id: parseInt(productoSeleccionado),
                cantidad_producida: parseInt(cantidad)
            };

            await api.post('/produccion/', payload);

            setSuccessMsg("¡Tanda registrada exitosamente! El stock ha sido sumado.");
            setProductoSeleccionado('');
            setCantidad('');

            setTimeout(() => setSuccessMsg(''), 4000);
        } catch (err) {
            setError(err.response?.data?.detail || "Error crítico al registrar la producción.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-orange-50 flex items-center justify-center p-6 font-sans">
            <div className="max-w-2xl w-full bg-white rounded-3xl shadow-2xl overflow-hidden border border-orange-100">

                {/* Cabecera Tablet-Friendly */}
                <div className="bg-orange-500 p-8 text-center relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-8 opacity-10">
                        <ChefHat className="w-32 h-32 text-white" />
                    </div>
                    <div className="relative z-10 flex flex-col items-center">
                        <div className="bg-white/20 p-4 rounded-full mb-4 backdrop-blur-sm">
                            <ChefHat className="w-12 h-12 text-white" />
                        </div>
                        <h1 className="text-4xl font-black text-white tracking-tight">Registro de Producción</h1>
                        <p className="text-orange-100 text-lg font-medium mt-2">Área exclusiva de cuadra y horneado</p>
                    </div>
                </div>

                <div className="p-10">

                    {/* Alertas */}
                    {error && (
                        <div className="bg-red-50 text-red-600 p-5 rounded-2xl text-lg font-medium flex items-center gap-3 mb-8 border border-red-200 shadow-sm animate-pulse">
                            <AlertTriangle className="w-8 h-8 flex-shrink-0" />
                            {error}
                        </div>
                    )}

                    {successMsg && (
                        <div className="bg-emerald-50 text-emerald-600 p-5 rounded-2xl text-lg font-bold flex items-center gap-3 mb-8 border border-emerald-200 shadow-sm">
                            <CheckCircle2 className="w-8 h-8 flex-shrink-0" />
                            {successMsg}
                        </div>
                    )}

                    {/* Formulario adaptado para dedos grandes (Touch UI) */}
                    <form onSubmit={handleRegistrarTanda} className="space-y-8">

                        <div>
                            <label className="block text-xl font-bold text-slate-700 mb-4">¿Qué se horneó?</label>
                            <select
                                value={productoSeleccionado}
                                onChange={(e) => setProductoSeleccionado(e.target.value)}
                                className="w-full px-6 py-6 text-2xl font-bold text-slate-800 bg-slate-50 border-2 border-slate-200 rounded-2xl focus:ring-4 focus:ring-orange-500/20 focus:border-orange-500 outline-none transition-all appearance-none cursor-pointer"
                                required
                            >
                                <option value="" disabled>Seleccione el producto de la lista...</option>
                                {productos.map((prod) => (
                                    <option key={prod.id} value={prod.id}>
                                        {prod.nombre}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div>
                            <label className="block text-xl font-bold text-slate-700 mb-4">Cantidad Producida (Unidades)</label>
                            <div className="relative flex items-center">
                                <input
                                    type="number"
                                    min="1"
                                    value={cantidad}
                                    onChange={(e) => setCantidad(e.target.value)}
                                    className="w-full pl-6 pr-16 py-6 text-4xl font-black text-center text-orange-600 bg-orange-50 border-2 border-orange-200 rounded-2xl focus:ring-4 focus:ring-orange-500/30 focus:border-orange-500 outline-none transition-all placeholder-orange-200"
                                    placeholder="0"
                                    required
                                />
                                <span className="absolute right-6 text-2xl font-bold text-orange-400 pointer-events-none">u.</span>
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className={`w-full flex items-center justify-center gap-3 py-6 mt-4 rounded-2xl font-black text-3xl text-white shadow-xl transition-all ${loading
                                    ? 'bg-slate-400 cursor-not-allowed'
                                    : 'bg-emerald-500 hover:bg-emerald-600 hover:-translate-y-1 active:scale-95 shadow-emerald-500/30'
                                }`}
                        >
                            {loading ? 'REGISTRANDO...' : (
                                <>
                                    <PlusCircle className="w-8 h-8" />
                                    REGISTRAR TANDA
                                </>
                            )}
                        </button>
                    </form>

                </div>
            </div>
        </div>
    );
};

export default PanelPanadero;
