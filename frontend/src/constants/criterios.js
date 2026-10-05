// Orden y textos de los 6 criterios de explicabilidad. El orden de este
// arreglo define el orden en que se muestran las tarjetas en el panel de
// detalle de una recomendación.
export const CRITERIOS_ORDENADOS = [
  {
    key: 'riesgo_quiebre_stock',
    titulo: 'Riesgo de quiebre de stock',
    descripcion: 'Evalúa si el stock actual cubre la demanda durante el lead time del proveedor.',
    unidad: 'unidades',
  },
  {
    key: 'eficiencia_cantidad_eoq',
    titulo: 'Eficiencia de la cantidad de pedido',
    descripcion: 'Compara la cantidad recomendada con el EOQ (cantidad económica de pedido).',
    unidad: '×EOQ',
  },
  {
    key: 'confianza_demanda',
    titulo: 'Confianza en la demanda estimada',
    descripcion: 'Mide la variabilidad de la demanda histórica mediante el coeficiente de variación (CV).',
    unidad: 'CV',
  },
  {
    key: 'importancia_producto',
    titulo: 'Importancia del producto',
    descripcion: 'Combina la clasificación ABC y XYZ del producto.',
    unidad: null,
  },
  {
    key: 'confiabilidad_proveedor',
    titulo: 'Confiabilidad del proveedor',
    descripcion: 'Score calculado a partir del cumplimiento de entrega y la tasa de defectos.',
    unidad: '/100',
  },
  {
    key: 'oportunidad_ahorro',
    titulo: 'Oportunidad de ahorro por volumen',
    descripcion: 'Estima el ahorro neto de subir el pedido al umbral de descuento.',
    unidad: '$',
  },
]

export const CRITERIOS_POR_KEY = Object.fromEntries(
  CRITERIOS_ORDENADOS.map((c) => [c.key, c])
)
