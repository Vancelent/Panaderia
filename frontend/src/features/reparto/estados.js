// Tonos de cada estado de hoja y de entrega (los valores son los del backend).
export const TONO_HOJA = {
  Borrador: 'neutral',
  Confirmada: 'blue',
  Cargada: 'violet',
  'En ruta': 'amber',
  Rendida: 'green',
  Anulada: 'red',
}

export const TONO_ENTREGA = {
  Pendiente: 'neutral',
  'En el local': 'amber',
  Entregada: 'green',
  Parcial: 'blue',
  'No entregada': 'red',
}

// Colores de los marcadores del mapa (hex, porque Leaflet no usa clases de Tailwind)
export const COLOR_ENTREGA = {
  Pendiente: '#78716c',
  'En el local': '#d97706',
  Entregada: '#059669',
  Parcial: '#0284c7',
  'No entregada': '#dc2626',
}

export const hhmm = (t) => (t ? t.slice(0, 5) : '')

export const ventana = (e) =>
  e.ventana_desde && e.ventana_hasta ? `${hhmm(e.ventana_desde)}–${hhmm(e.ventana_hasta)}` : null

// Lunes = 0 … domingo = 6, como el backend (Date.getDay() arranca en domingo)
export const diaSemana = (isoFecha) => (new Date(`${isoFecha}T12:00:00`).getDay() + 6) % 7
