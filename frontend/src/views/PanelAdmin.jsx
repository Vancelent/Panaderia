import React, { useState, useEffect } from 'react';
import { LayoutDashboard, Truck, PackageSearch, Users, Wallet, TrendingUp, DollarSign, PlusCircle } from 'lucide-react';
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
    </div>
  );
};

const ProveedoresTab = () => {
  const [proveedores, setProveedores] = useState([]);
  
  useEffect(() => {
    const fetchProv = async () => {
      const res = await api.get('/proveedores/');
      setProveedores(res.data);
    };
    fetchProv();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-black text-slate-800">Proveedores y Compras</h2>
        <button className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-xl font-bold flex items-center gap-2">
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
                  <button className="text-indigo-600 font-bold hover:underline">Registrar Compra</button>
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

// ==========================================
// COMPONENTE PRINCIPAL (PANEL ADMIN)
// ==========================================

const PanelAdmin = () => {
  const [activeTab, setActiveTab] = useState('dashboard');

  const menuItems = [
    { id: 'dashboard', label: 'Resumen y Finanzas', icon: <LayoutDashboard /> },
    { id: 'proveedores', label: 'Proveedores y Compras', icon: <Truck /> },
    { id: 'inventario', label: 'Gestión de Inventario', icon: <PackageSearch /> },
    { id: 'gastos', label: 'Gastos Varios', icon: <Wallet /> },
    { id: 'rrhh', label: 'Personal y Auditoría', icon: <Users /> },
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
        {activeTab === 'proveedores' && <ProveedoresTab />}
        {activeTab === 'inventario' && <ConstruccionTab titulo="Gestión de Inventario" />}
        {activeTab === 'gastos' && <ConstruccionTab titulo="Gastos Varios" />}
        {activeTab === 'rrhh' && <ConstruccionTab titulo="Personal y Auditoría" />}
      </div>
    </div>
  );
};

export default PanelAdmin;
