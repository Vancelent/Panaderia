import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './context/ProtectedRoute';

import Login from './views/Login';
import DashboardContador from './views/DashboardContador';
import CajaRegistradora from './views/CajaRegistradora';

// Componentes "Placeholder" para vistas aún no desarrolladas

const Produccion = () => (
  <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-8">
    <h1 className="text-4xl font-extrabold text-slate-800 mb-4">🥐 Módulo de Producción</h1>
    <p className="text-lg text-slate-500 font-medium">Panel de horneado y mermas en construcción.</p>
  </div>
);

const PanelAdmin = () => (
  <div className="min-h-screen bg-gray-50">
    <div className="bg-slate-900 text-white p-4 shadow-md flex justify-between items-center">
      <h1 className="text-xl font-bold">ERP Panadería - Admin</h1>
      <span className="text-sm bg-blue-600 px-3 py-1 rounded-full font-medium">Administración General</span>
    </div>
    <DashboardContador />
  </div>
);

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Ruta Pública */}
          <Route path="/login" element={<Login />} />

          {/* ----- RUTAS PROTEGIDAS Y GESTIONADAS POR ROL ----- */}
          
          <Route 
            path="/admin" 
            element={
              <ProtectedRoute rolesPermitidos={['Admin', 'Encargada']}>
                <PanelAdmin />
              </ProtectedRoute>
            } 
          />
          
          <Route 
            path="/caja" 
            element={
              <ProtectedRoute rolesPermitidos={['Admin', 'Encargada', 'Vendedora']}>
                <CajaRegistradora />
              </ProtectedRoute>
            } 
          />
          
          <Route 
            path="/produccion" 
            element={
              <ProtectedRoute rolesPermitidos={['Admin', 'Encargada', 'Panadero']}>
                <Produccion />
              </ProtectedRoute>
            } 
          />

          {/* Rutas de redirección o Catch-all */}
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
          
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
