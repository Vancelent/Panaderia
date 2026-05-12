FROM python:3.11-slim

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar solo el requirements primero para cachear la capa de instalación de dependencias
COPY requirements.txt .

# Instalar dependencias esenciales sin cache extra para mantener la imagen ligera
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto de los archivos
COPY . .

# Exponemos el puerto de FastAPI
EXPOSE 8000

# El command por defecto, aunque lo sobreescribirmos en el compose para usar hot-reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
