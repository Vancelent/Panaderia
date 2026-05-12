import { useContext } from 'react';
import { Navigate } from 'react-router-dom';
import { AuthContext } from './AuthContext';

const ProtectedRoute = ({ children, rolesPermitidos }) => {
  const { user, loading } = useContext(AuthContext);

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-50 text-gray-500 font-medium">Cargando sistema...</div>;
  }

  if (!user) {
    // Si no hay usuario en contexto, redirigir al login
    return <Navigate to="/login" replace />;
  }

  // Si la ruta exige roles específicos y el usuario no lo tiene
  if (rolesPermitidos && !rolesPermitidos.includes(user.rol)) {
    // Lo redirigimos a su "Home" natural según su Rol para evitar errores 403
    switch (user.rol) {
      case 'Admin': 
      case 'Encargada':
        return <Navigate to="/admin" replace />;
      case 'Vendedora': 
        return <Navigate to="/caja" replace />;
      case 'Panadero': 
        return <Navigate to="/produccion" replace />;
      default: 
        return <Navigate to="/login" replace />;
    }
  }

  // Si tiene los permisos, renderizar el componente hijo normalmente
  return children;
};

export default ProtectedRoute;
