/** Corta la traza donde hay un hueco registrado (sin señal, permiso revocado…) para no unir con una
 * línea recta lo que en realidad no se sabe. Devuelve los tramos continuos y los huecos punteados. */
export function partirTraza(traza, eventos) {
  const puntos = traza.map((p) => ({ c: [Number(p.latitud), Number(p.longitud)], t: new Date(p.registrado_en).getTime() }))
  const cortes = new Set()
  const huecos = []
  for (const ev of eventos) {
    const desde = new Date(ev.desde).getTime()
    // Último punto anterior al corte
    let i = -1
    for (let k = 0; k < puntos.length; k++) if (puntos[k].t <= desde) i = k
    if (i === -1 || i >= puntos.length - 1) continue
    const hasta = ev.hasta ? new Date(ev.hasta).getTime() : null
    let j = i + 1
    if (hasta != null) while (j < puntos.length - 1 && puntos[j].t < hasta) j++
    cortes.add(i)
    huecos.push([puntos[i].c, puntos[j].c])
  }
  const tramos = []
  let actual = []
  puntos.forEach((p, k) => {
    actual.push(p.c)
    if (cortes.has(k)) {
      tramos.push(actual)
      actual = []
    }
  })
  if (actual.length) tramos.push(actual)
  return { tramos: tramos.filter((t) => t.length > 1), huecos }
}
