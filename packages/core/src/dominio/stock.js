/** Semáforo de stock: rojo sin stock o bajo mínimo, ámbar cerca del mínimo. */
export function nivelStock(actual, minimo) {
  const a = Number(actual)
  const m = Number(minimo)
  if (a <= 0) return { tone: 'red', label: 'Sin stock' }
  if (m > 0 && a <= m) return { tone: 'red', label: 'Bajo mínimo' }
  if (m > 0 && a <= m * 1.5) return { tone: 'amber', label: 'Reponer pronto' }
  return { tone: 'green', label: 'OK' }
}
