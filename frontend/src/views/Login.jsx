import { useState, useContext } from 'react';
import { useNavigate } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { login } = useContext(AuthContext);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    if (!username || !password) {
      setError('Por favor complete todos los campos');
      return;
    }

    setIsSubmitting(true);
    const result = await login(username, password);
    setIsSubmitting(false);

    if (result.success) {
      // Redirección inteligente basada en el rol que devolvió el token
      switch (result.rol) {
        case 'Admin':
        case 'Encargada':
          navigate('/admin');
          break;
        case 'Vendedora':
          navigate('/caja');
          break;
        case 'Panadero':
          navigate('/produccion');
          break;
        default:
          navigate('/');
      }
    } else {
      setError(result.message);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8 font-sans">
      <div className="max-w-md w-full space-y-8 bg-white p-10 rounded-2xl shadow-xl border border-gray-100">
        
        <div className="flex flex-col items-center">
          <div className="w-16 h-16 bg-blue-600 rounded-full flex items-center justify-center mb-4 shadow-lg shadow-blue-200">
             <span className="text-3xl">🍞</span>
          </div>
          <h2 className="text-center text-3xl font-extrabold text-slate-900 tracking-tight">
            Ingreso al Sistema
          </h2>
          <p className="mt-2 text-center text-sm text-slate-500 font-medium">
            ERP Panadería Artesanal
          </p>
        </div>
        
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="bg-red-50 text-red-600 p-4 rounded-xl text-sm text-center font-medium border border-red-100 shadow-sm animate-pulse">
              {error}
            </div>
          )}
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1.5">Usuario</label>
              <input
                name="username"
                type="text"
                required
                className="appearance-none block w-full px-4 py-3.5 border border-slate-200 text-slate-900 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all sm:text-sm bg-slate-50 focus:bg-white"
                placeholder="Nombre de usuario"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1.5">Contraseña</label>
              <input
                name="password"
                type="password"
                required
                className="appearance-none block w-full px-4 py-3.5 border border-slate-200 text-slate-900 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all sm:text-sm bg-slate-50 focus:bg-white"
                placeholder="Contraseña secreta"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled={isSubmitting}
              className={`w-full flex justify-center py-3.5 px-4 border border-transparent text-sm font-bold rounded-xl text-white shadow-lg transition-all ${
                isSubmitting 
                  ? 'bg-blue-400 cursor-not-allowed' 
                  : 'bg-blue-600 hover:bg-blue-700 hover:shadow-blue-200 hover:-translate-y-0.5'
              }`}
            >
              {isSubmitting ? 'Iniciando sesión...' : 'Ingresar al sistema'}
            </button>
          </div>
        </form>
      </div>
      
      <p className="mt-8 text-center text-xs text-slate-400 font-medium">
        © 2026 ERP Panadería. Todos los derechos reservados.
      </p>
    </div>
  );
};

export default Login;
