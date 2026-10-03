// Aplica el tema antes de pintar para evitar el parpadeo claro/oscuro.
// Es un archivo aparte (y no un <script> inline) para poder usar una CSP sin 'unsafe-inline'.
try {
  var t = localStorage.getItem('tema') || 'system'
  var dark = t === 'dark' || (t === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
  if (dark) document.documentElement.classList.add('dark')
} catch {
  // Sin acceso al almacenamiento (modo privado): queda el tema del sistema
}
