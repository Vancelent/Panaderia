import { useCallback, useEffect, useState } from 'react'

const CLAVE = 'tema'
const media = () => window.matchMedia('(prefers-color-scheme: dark)')

function leer() {
  try {
    return localStorage.getItem(CLAVE) || 'system'
  } catch {
    return 'system'
  }
}

function aplicar(tema) {
  const oscuro = tema === 'dark' || (tema === 'system' && media().matches)
  document.documentElement.classList.toggle('dark', oscuro)
}

/** Tema claro / oscuro / del sistema, recordado por navegador. */
export function useTheme() {
  const [tema, setTema] = useState(leer)

  useEffect(() => {
    aplicar(tema)
    if (tema !== 'system') return
    const m = media()
    const onChange = () => aplicar('system')
    m.addEventListener('change', onChange)
    return () => m.removeEventListener('change', onChange)
  }, [tema])

  const cambiar = useCallback((nuevo) => {
    try {
      localStorage.setItem(CLAVE, nuevo)
    } catch {
      /* almacenamiento no disponible: el tema dura la sesión */
    }
    setTema(nuevo)
  }, [])

  return [tema, cambiar]
}
