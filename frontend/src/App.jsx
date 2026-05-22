import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './context/ProtectedRoute';

import Login from './views/Login';
import DashboardContador from './views/DashboardContador';
import CajaRegistradora from './views/CajaRegistradora';
import PanelPanadero from './views/PanelPanadero';

// Componentes "Placeholder" para vistas aún no desarrolladas


import PanelAdmin from './views/PanelAdmin';

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
                <PanelPanadero />
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
