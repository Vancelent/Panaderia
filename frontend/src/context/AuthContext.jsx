import { createContext, useState, useEffect } from 'react';
import api from '../api/api';

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Decodifica el payload de un JWT usando atob sin librerías externas
  const decodeJWT = (token) => {
    try {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/, '/');
      const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(function(c) {
          return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
      }).join(''));
      return JSON.parse(jsonPayload);
    } catch (e) {
      return null;
    }
  };

  useEffect(() => {
    const token = localStorage.getItem('jwt_token');
    if (token) {
      const decoded = decodeJWT(token);
      if (decoded && decoded.exp * 1000 > Date.now()) {
        setUser({
          id: decoded.sub,
          username: decoded.username,
          rol: decoded.rol
        });
      } else {
        localStorage.removeItem('jwt_token');
      }
    }
    setLoading(false);
  }, []);

  const login = async (username, password) => {
    try {
      // OAuth2 exige enviar los datos como form-urlencoded, no JSON
      const formData = new URLSearchParams();
      formData.append('username', username);
      formData.append('password', password);

      const response = await api.post('/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      });
      
      const token = response.data.access_token;
      localStorage.setItem('jwt_token', token);
      
      // Decodificamos para actualizar el estado instantáneamente
      const decoded = decodeJWT(token);
      setUser({
        id: decoded.sub,
        username: decoded.username,
        rol: decoded.rol
      });
      return { success: true, rol: decoded.rol };
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || "Error de conexión. Verifica que el servidor Backend esté encendido." 
      };
    }
  };

  const logout = () => {
    localStorage.removeItem('jwt_token');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};
