import axios from 'axios';

const api = axios.create({
    baseURL: 'http://localhost:8000',
});

// Interceptor: Se ejecuta ANTES de que cualquier petición salga al backend
api.interceptors.request.use(
    (config) => {
        // Leemos el token de seguridad guardado en el navegador
        const token = localStorage.getItem('jwt_token');

        // Si existe, lo inyectamos automáticamente en la cabecera
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

export default api;
