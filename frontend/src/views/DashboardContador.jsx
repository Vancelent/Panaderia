import { useEffect, useState } from 'react';
import { BadgeDollarSign, AlertTriangle, CheckCircle2 } from 'lucide-react';
import api from '../api/api';

const DashboardContador = () => {
    const [arqueos, setArqueos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchArqueos = async () => {
            try {
                // Hacemos el GET al backend. Gracias a api.js, el token ya va incluido.
                const response = await api.get('/arqueos/');
                setArqueos(response.data);
                setError(null);
            } catch (err) {
                if (err.response?.status === 401) {
                    setError("No autorizado. Por favor, inicie sesión primero.");
                } else {
                    setError("Error al conectar con el servidor.");
                }
            } finally {
                setLoading(false);
            }
        };

        fetchArqueos();
    }, []);

    return (
        <div className="min-h-screen bg-gray-50 p-8 font-sans text-slate-800">
            <div className="max-w-6xl mx-auto">

                {/* Cabecera */}
                <div className="flex items-center gap-3 mb-8">
                    <div className="p-3 bg-blue-600 rounded-xl shadow-lg">
                        <BadgeDollarSign className="w-8 h-8 text-white" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Auditoría de Cajas</h1>
                        <p className="text-slate-500 font-medium mt-1">Historial de arqueos ciegos y diferencias de turnos</p>
                    </div>
                </div>

                {error && (
                    <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-6 rounded-r shadow-sm">
                        <div className="flex items-center">
                            <AlertTriangle className="h-5 w-5 text-red-500 mr-2" />
                            <p className="text-red-700 font-medium">{error}</p>
                        </div>
                    </div>
                )}

                {/* Tabla */}
                <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
                    {loading ? (
                        <div className="p-12 text-center text-slate-400 font-medium animate-pulse">Cargando arqueos...</div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="bg-slate-50 text-slate-500 uppercase text-xs tracking-wider font-semibold border-b border-gray-100">
                                        <th className="py-4 px-6">ID Arqueo</th>
                                        <th className="py-4 px-6">Turno N°</th>
                                        <th className="py-4 px-6 text-right">Monto Sistema</th>
                                        <th className="py-4 px-6 text-right">Monto Declarado</th>
                                        <th className="py-4 px-6 text-right">Diferencia</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-50">
                                    {arqueos.length === 0 ? (
                                        <tr>
                                            <td colSpan="5" className="py-8 text-center text-slate-400">No hay arqueos registrados aún.</td>
                                        </tr>
                                    ) : (
                                        arqueos.map((arqueo) => (
                                            <tr key={arqueo.id} className="hover:bg-slate-50/80 transition-colors">
                                                <td className="py-4 px-6 font-medium text-slate-900">#{arqueo.id}</td>
                                                <td className="py-4 px-6 text-slate-500">#{arqueo.turno_id}</td>
                                                <td className="py-4 px-6 text-right text-slate-600">${arqueo.monto_sistema.toFixed(2)}</td>
                                                <td className="py-4 px-6 text-right font-medium text-slate-800">${arqueo.monto_declarado.toFixed(2)}</td>

                                                {/* Lógica Visual de Diferencias */}
                                                <td className="py-4 px-6 text-right">
                                                    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-bold ${arqueo.diferencia < 0
                                                            ? 'bg-red-100 text-red-700 ring-1 ring-red-200'
                                                            : 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200'
                                                        }`}>
                                                        {arqueo.diferencia < 0 ? (
                                                            <AlertTriangle className="w-4 h-4" />
                                                        ) : (
                                                            <CheckCircle2 className="w-4 h-4" />
                                                        )}
                                                        ${Math.abs(arqueo.diferencia).toFixed(2)} {arqueo.diferencia < 0 ? 'Faltante' : ''}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

            </div>
        </div>
    );
};

export default DashboardContador;
