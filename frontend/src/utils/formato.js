// Formateadores centralizados de la aplicación: español de México (es-MX),
// con separador de miles "," y punto decimal "." (p. ej. $1,470.64 y 66.7 %).
// es-MX agrupa desde números de cuatro cifras por defecto, así que no hace
// falta forzar useGrouping.

// Montos en pesos mexicanos: incluye el símbolo "$" y dos decimales.
export const moneda = new Intl.NumberFormat('es-MX', {
  style: 'currency',
  currency: 'MXN',
})

// Cantidades y números generales: no fuerza decimales (5,000 y no 5,000.00).
export const numero = new Intl.NumberFormat('es-MX', {
  maximumFractionDigits: 2,
})

// Porcentajes ya expresados en escala 0-100 (por eso NO es style: 'percent',
// que multiplicaría el valor por 100). En México el decimal es punto:
// "66.7", no "66,7".
export const porcentaje = new Intl.NumberFormat('es-MX', {
  maximumFractionDigits: 1,
})

// Valores con mayor precisión (p. ej. el CV de la demanda o los parámetros
// de configuración).
export const numeroPreciso = new Intl.NumberFormat('es-MX', {
  maximumFractionDigits: 4,
})

// Score de proveedor: siempre un decimal para que los cortes de estado sean
// legibles (60.0 vs 60).
export const score = new Intl.NumberFormat('es-MX', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})
