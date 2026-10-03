// Coordinación entre la capa HTTP y el diálogo de reautenticación (docs/rfc-001 §2.4).
//
// Cuando la API responde `401 reautenticacion_requerida`, api.js llama a `pedirReautenticacion()`: se emite
// un evento que atiende <ReautenticacionDialog /> y la promesa se resuelve cuando la persona confirma su
// identidad (o se rechaza si cancela). Varias solicitudes simultáneas comparten un único diálogo.

let pendiente = null

export function pedirReautenticacion() {
  if (!pendiente) {
    pendiente = new Promise((resolve, reject) => {
      window.dispatchEvent(new CustomEvent('auth:reauth', { detail: { resolve, reject } }))
    }).finally(() => {
      pendiente = null
    })
  }
  return pendiente
}
