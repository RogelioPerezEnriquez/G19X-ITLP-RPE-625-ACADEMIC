# PRD — Sistema Inteligente de Optimización de Compras

## 1. Resumen ejecutivo

Este documento especifica un sistema de soporte a la decisión de compras que, a partir de datos históricos de inventario, demanda y desempeño de proveedores, genera recomendaciones cuantificadas y explicadas sobre qué comprar, cuánto, cuándo y a qué proveedor. El sistema no gestiona movimientos de almacén (entradas/salidas): asume que esos datos ya existen y se enfoca en la capa de decisión posterior a ellos.

El MVP descrito en este documento cubre una sola capacidad de punta a punta: reabastecimiento de inventario con evaluación explicada por criterios y un agente conversacional de consulta. El resto de las capacidades planeadas se documenta como roadmap en la sección 16.

## 2. Problemática

Las decisiones de compra en una organización suelen tomarse de forma reactiva y sin un criterio cuantitativo repetible: cuánto comprar, cuándo hacerlo y a qué proveedor recurrir dependen de la experiencia individual del comprador más que de un análisis sistemático de demanda, inventario y desempeño histórico de proveedores. Esto produce tres síntomas recurrentes:

- **Sobre-stock o quiebres de inventario**, por no calcular puntos de reorden ni demanda esperada de forma sistemática.
- **Selección de proveedores subóptima**, por ausencia de un criterio objetivo y ponderado (precio, tiempo de entrega, cumplimiento, calidad).
- **Oportunidades de ahorro no detectadas** (consolidación de pedidos, umbrales de descuento por volumen), por falta de un cruce sistemático de esas variables.

El valor del sistema no está en la interfaz que presenta la información, sino en el cálculo que produce las recomendaciones: herramientas como una hoja de cálculo permiten registrar y consultar datos, pero no calculan puntos de reorden, cantidades económicas de pedido ni evalúan recomendaciones contra criterios explícitos de forma automática y consistente.

### Qué no es este sistema

Este sistema **no es un módulo de gestión de movimientos de almacén** (tipo WMS o el módulo de inventario de un ERP). No captura entradas y salidas de producto; asume que los datos de inventario, historial de demanda y desempeño de proveedores ya existen —en este proyecto, mediante un dataset sintético con fines de desarrollo y validación— y se enfoca exclusivamente en la capa de decisión: qué comprar, cuánto, cuándo y a quién, con evaluación explicada.

## 3. Objetivos

**Objetivo general:** desarrollar un sistema de soporte a la decisión de compras que genere recomendaciones cuantificadas y explicables a partir de datos históricos y reglas de negocio configurables.

**Objetivos específicos:**
- Diseñar y construir un motor de cálculo de optimización de inventario (clasificación ABC/XYZ, punto de reorden, cantidad económica de pedido).
- Implementar una rúbrica de evaluación explícita que traduzca los resultados del motor en recomendaciones priorizadas y justificadas.
- Incorporar un componente de inteligencia artificial que permita consultar y explicar las recomendaciones en lenguaje natural, grounded en los datos calculados.
- Validar el funcionamiento del sistema mediante un dataset sintético con reglas de negocio conocidas.
- Documentar la arquitectura y las decisiones de diseño de forma que el sistema pueda extenderse en fases futuras sin rediseñar el núcleo.

## 4. Usuarios

| Usuario | Rol |
|---|---|
| Comprador / analista de compras | Consume la cola de recomendaciones, las revisa y las aprueba o ajusta. Consulta al agente conversacional para entender el porqué de una recomendación. |
| Gerente de compras / supply chain | Consulta KPIs agregados y el estado general de las recomendaciones. |
| Administrador | Gestiona catálogos (productos, proveedores) y los parámetros de configuración de la rúbrica de evaluación. |

## 5. Alcance

### 5.1 Incluido en el MVP

- Ingesta de un dataset sintético de productos, proveedores, relación producto-proveedor e historial de demanda.
- Motor de optimización (Investigación de Operaciones):
  - Clasificación ABC por valor económico acumulado.
  - Clasificación XYZ por variabilidad de demanda (coeficiente de variación).
  - Estimación de demanda mediante promedio móvil o suavizado exponencial simple.
  - Cálculo de cantidad económica de pedido (EOQ), stock de seguridad y punto de reorden (ROP).
- Evaluación de cada recomendación contra seis criterios explícitos (ver sección 9), con estados y umbrales configurables.
- Agente conversacional de solo lectura que consulta y explica las recomendaciones y sus criterios en lenguaje natural.
- Interfaz: cola de recomendaciones priorizada, panel de explicabilidad por recomendación y chat con el agente.

### 5.2 Fuera de alcance del MVP (ver roadmap, sección 16)

- Modelo de Machine Learning para forecasting de demanda.
- Integración real con un sistema ERP existente.
- Scoring multi-proveedor más allá del cálculo base incluido en el MVP.
- Ejecución automática de órdenes de compra (e-procurement).
- Dashboards ejecutivos avanzados más allá de KPIs básicos.
- Autoajuste automático de umbrales de evaluación según desempeño histórico.
- Autenticación de nivel empresarial (SSO corporativo).

## 6. Requisitos funcionales

| ID | Requisito |
|---|---|
| RF-01 | El sistema debe cargar datos de productos, proveedores, relación producto-proveedor e historial de demanda desde archivos CSV/Excel hacia las tablas correspondientes en Supabase, mediante un proceso de ingesta ejecutado por separado del motor de cálculo (ver sección 8.3). |
| RF-02 | El sistema debe calcular la clasificación ABC y XYZ de cada producto a partir de su historial de demanda y valor económico. |
| RF-03 | El sistema debe estimar la demanda futura de cada producto mediante un método estadístico (promedio móvil o suavizado exponencial). |
| RF-04 | El sistema debe calcular EOQ, stock de seguridad y punto de reorden por producto. |
| RF-05 | El sistema debe generar una recomendación de compra (producto, proveedor sugerido, cantidad, fecha) cuando el stock de un producto lo amerite. |
| RF-06 | El sistema debe evaluar cada recomendación contra los seis criterios definidos en la sección 9 y asignar un estado a cada uno. |
| RF-07 | El sistema debe presentar las recomendaciones ordenadas por prioridad en una cola. |
| RF-08 | El sistema debe mostrar, por cada recomendación, el detalle de los criterios evaluados y su justificación. |
| RF-09 | El sistema debe permitir consultar al agente conversacional preguntas sobre una recomendación o criterio específico, y responder citando datos reales ya calculados. |
| RF-10 | El agente conversacional debe indicar explícitamente cuando no cuenta con datos suficientes para responder, sin generar información no verificada. |
| RF-11 | El administrador debe poder modificar los parámetros de configuración (umbrales de la rúbrica) sin modificar código. |
| RF-12 | El sistema debe autenticar usuarios mediante Supabase Auth y restringir el acceso a la pantalla de configuración de parámetros exclusivamente al rol Administrador. |

> **Nota de implementación:** no existe registro público de usuarios en el MVP. Las cuentas de los tres roles (comprador, gerente, administrador) se crean directamente en Supabase como parte de la configuración inicial del sistema, no mediante una pantalla de la aplicación.

## 7. Requisitos no funcionales

- **Explicabilidad:** ninguna recomendación debe presentarse sin su justificación desglosada por criterio.
- **Trazabilidad:** cada recomendación debe poder rastrearse a los datos de entrada que la originaron.
- **Configurabilidad:** los umbrales de evaluación deben residir en una tabla de configuración, nunca como constantes fijas en el código de cálculo.
- **Desacoplamiento de la ingesta:** el módulo de carga de datos debe estar separado del motor de cálculo, de forma que una futura fuente de datos (por ejemplo, un ERP) pueda sustituir al dataset sintético sin modificar el motor ni la lógica de evaluación.
- **Restricción de escritura del agente:** el agente conversacional únicamente debe tener acceso de lectura a los datos calculados; no debe poder crear, modificar ni eliminar registros.
- **Control de acceso por rol:** las acciones de configuración (modificar parámetros de la rúbrica) deben estar restringidas al rol Administrador; los demás roles solo tienen acceso de consulta.

## 8. Arquitectura y tecnologías

| Componente | Tecnología | Justificación |
|---|---|---|
| Cálculo del motor de optimización | Python (pandas, numpy) | Permite implementar las fórmulas de ABC/XYZ, EOQ y ROP sin dependencias adicionales. |
| Persistencia y autenticación | Supabase (Postgres) | Base de datos relacional real con autenticación integrada, adecuada para el volumen de datos del MVP. |
| Agente conversacional | API de un modelo de lenguaje (function calling) | Permite implementar un agente con acceso restringido a funciones de consulta de solo lectura, sin requerir infraestructura de ML propia. |
| Frontend | Vue 3 (Vite, Vue Router, Pinia) | Framework ligero, con reactividad nativa adecuada para reflejar cambios en los datos consultados desde Supabase. |
| Visualización de datos | Librería de gráficos embebida en el frontend | Suficiente para los KPIs básicos del MVP, sin requerir licencias externas. |

### 8.1 Justificación de no incluir Machine Learning en el MVP

Se optó por estimar la demanda mediante métodos estadísticos clásicos (promedio móvil o suavizado exponencial) y por concentrar el componente de inteligencia artificial en un agente conversacional grounded en datos ya calculados, en lugar de entrenar un modelo de Machine Learning para forecasting. Esta decisión prioriza un componente de IA verificable y con comportamiento acotado (el agente solo puede consultar funciones definidas de antemano) dentro del tiempo disponible para el MVP, frente a un modelo predictivo que requeriría un proceso adicional de entrenamiento, validación estadística y ajuste que no es indispensable para demostrar el valor central del sistema: la evaluación de recomendaciones contra criterios explícitos.

### 8.2 Pipeline del sistema

```
Dataset sintético
      ↓
Motor OR (ABC · XYZ · EOQ · ROP)
      ↓
Evaluación por criterios (rúbrica de 6 criterios)
      ↓
Agente conversacional (consulta de solo lectura, explica resultados)
      ↓
Interfaz (cola de recomendaciones + panel de explicabilidad + chat)
```

### 8.3 Proceso de ingesta de datos

El archivo CSV/Excel es únicamente el **formato de origen** del dataset sintético; no es un almacén paralelo de datos. El flujo es el siguiente:

1. Se genera (o recibe) un archivo CSV/Excel por cada entidad del modelo de datos (productos, proveedores, producto_proveedor, historial_demanda), con columnas que corresponden exactamente a los campos definidos en la sección 12.
2. Un script de ingesta, separado del motor de cálculo, lee cada archivo con pandas y valida que las columnas requeridas estén presentes y sin valores faltantes en los campos clave (identificadores, cantidades, precios).
3. El script inserta los registros validados en las tablas correspondientes de Supabase, a través del cliente de Supabase para Python.
4. A partir de este punto, el motor de cálculo, el agente conversacional y la interfaz consultan exclusivamente Supabase; el archivo de origen no se vuelve a leer durante la operación normal del sistema.

> **Nota de implementación:** para el MVP, este proceso de ingesta es una operación manual (se ejecuta como paso de preparación de datos, no como una función accesible desde la interfaz de usuario). Habilitar la carga de archivos como una acción disponible dentro de la interfaz queda fuera del alcance del MVP y se deja documentado en el roadmap (sección 16).

## 9. Motor de optimización — especificación de cálculo

- **Clasificación ABC:** ordenar productos por valor económico acumulado (precio × cantidad). Clase A = primer 80% del valor acumulado; clase B = siguiente 15% (80–95%); clase C = último 5% (95–100%).
- **Clasificación XYZ:** calcular el coeficiente de variación (CV = desviación estándar / media) de la demanda histórica de cada producto. Clase X: CV ≤ 0.5. Clase Y: 0.5 < CV ≤ 1.0. Clase Z: CV > 1.0.

  > **Nota de implementación:** el CV debe calcularse una sola vez por producto y reutilizarse tanto para la clasificación XYZ como para el criterio de confianza en la demanda estimada (sección 9, criterio 3).

- **Demanda estimada:** promedio móvil o suavizado exponencial simple sobre el historial de demanda del producto.
- **Punto de reorden (ROP):** nivel de inventario en el que debe generarse un nuevo pedido, calculado a partir de la demanda estimada y el lead time del proveedor.
- **Stock de seguridad:** margen adicional de inventario para cubrir variabilidad en la demanda o en el tiempo de entrega.
- **Cantidad económica de pedido (EOQ):** cantidad que minimiza la suma del costo de ordenar y el costo de mantener inventario.

## 10. Rúbrica de evaluación de recomendaciones

Cada recomendación generada por el motor se evalúa contra seis criterios independientes. Todos los umbrales numéricos son parámetros configurables, no constantes fijas en el código.

**1. Riesgo de quiebre de stock**
| Estado | Condición |
|---|---|
| Crítico | stock actual ≤ stock de seguridad |
| Atención | stock de seguridad < stock actual ≤ punto de reorden |
| Sin riesgo | stock actual > punto de reorden |

**2. Eficiencia de la cantidad de pedido (vs. EOQ)**
| Estado | Condición |
|---|---|
| Pedido muy pequeño | cantidad < 90% del EOQ |
| Óptima | 90%–110% del EOQ |
| Pedido excesivo | cantidad > 110% del EOQ |

**3. Confianza en la demanda estimada**
| Estado | Condición |
|---|---|
| Alta confianza | CV ≤ 0.5 |
| Confianza moderada | 0.5 < CV ≤ 1.0 |
| Baja confianza (revisión manual) | CV > 1.0 |

**4. Importancia del producto (matriz ABC × XYZ)**

| | X | Y | Z |
|---|---|---|---|
| **A** | Alta | Alta | Media |
| **B** | Alta | Media | Media |
| **C** | Media | Baja | Baja |

**5. Confiabilidad del proveedor**

`score = cumplimiento_entrega_pct × 0.6 + (100 − tasa_defectos_pct) × 0.4`

| Estado | Condición |
|---|---|
| Confiable | score ≥ 80 |
| Aceptable con reservas | 60 ≤ score < 80 |
| Riesgoso | score < 60 |

**6. Oportunidad de ahorro por volumen**

```
ahorro_bruto = cantidad_EOQ × precio_unitario × descuento_pct
               (solo si cantidad_EOQ ≥ cantidad_umbral_descuento)

costo_extra_mantener = (cantidad_EOQ − EOQ_sin_descuento)
                        × costo_unitario × costo_mantener_pct_anual

ahorro_neto = ahorro_bruto − costo_extra_mantener
```
| Estado | Condición |
|---|---|
| Ahorro detectado | ahorro neto ≥ 3% del costo total del pedido |
| Sin oportunidad adicional | ahorro neto < 3% |

> **Nota de implementación:** se asume que el exceso de inventario adquirido para aprovechar un descuento se mantiene durante un periodo completo. Esta simplificación es suficiente para el MVP; en fases futuras puede refinarse a un prorrateo temporal más preciso.

## 11. Agente conversacional — especificación

- **Rol:** analista de compras que explica recomendaciones y responde preguntas; no toma decisiones ni ejecuta acciones sobre los datos.
- **Alcance de consulta (funciones de solo lectura):**
  - `buscar_recomendaciones()`
  - `detalle_recomendacion(producto_id)`
  - `explicar_criterio(producto_id, criterio)`
  - `comparar_proveedores()`
  - `resumen_prioridad_ABC_XYZ()`
- **Restricciones:** el agente no puede crear, modificar ni eliminar registros. Si no encuentra datos suficientes para responder una pregunta, debe indicarlo explícitamente en lugar de generar una respuesta no verificada.
- **Grounding:** toda respuesta del agente debe basarse en el resultado de una de las funciones anteriores; no debe generar afirmaciones sobre datos que no haya consultado.

## 12. Modelo de datos

**productos**
`id, nombre, categoria, costo_unitario, stock_actual, costo_ordenar, costo_mantener_pct_anual`

**proveedores**
`id, nombre, cumplimiento_entrega_pct, tasa_defectos_pct`

**producto_proveedor** (relación muchos a muchos)
`producto_id (FK), proveedor_id (FK), precio_unitario, lead_time_dias, cantidad_umbral_descuento, descuento_pct`

> Un producto puede tener más de un proveedor disponible; el motor de optimización elige el proveedor recomendado por producto según score y precio, sin asumir una relación uno a uno.

**historial_demanda**
`id, producto_id (FK), periodo (mes), cantidad_demandada`

**recomendaciones**
`id, producto_id (FK), proveedor_id (FK, sugerido), fecha_generacion, demanda_estimada, cv_demanda, punto_reorden, stock_seguridad, cantidad_eoq, clase_abc, clase_xyz, ahorro_neto_estimado`

**evaluaciones_criterios**
`id, recomendacion_id (FK), criterio, estado, valor_numerico`

**parametros_configuracion**
`nombre_parametro (PK), valor, descripcion`

## 13. Interfaz — ideas conceptuales

- **Cola de recomendaciones:** lista priorizada de recomendaciones activas, ordenada por urgencia e impacto — no una tabla de captura manual.
- **Panel de explicabilidad:** al seleccionar una recomendación, se muestra el desglose de los seis criterios evaluados, su estado y el valor que lo originó.
- **Vista de proveedores:** comparación de proveedores disponibles para un producto, con su score y componentes.
- **Chat con el agente:** panel lateral o modal donde el usuario formula preguntas en lenguaje natural sobre una recomendación o el estado general del sistema.
- **Panel de KPIs:** indicadores agregados básicos (número de recomendaciones críticas, ahorro estimado acumulado, distribución ABC/XYZ del catálogo).
- **Pantalla de inicio de sesión:** punto de entrada a la aplicación, sin opción de registro público; la pantalla de configuración de parámetros solo es accesible tras autenticarse con el rol Administrador.

## 14. Riesgos y supuestos

| Riesgo / supuesto | Mitigación |
|---|---|
| Los datos utilizados son sintéticos, no datos reales de una operación. | Se diseñan con reglas de negocio conocidas, lo que permite validar que el motor calcula correctamente contra un resultado esperado. |
| El agente conversacional depende de un proveedor externo de modelo de lenguaje. | El acceso del agente se limita a funciones de solo lectura predefinidas, acotando el impacto de una respuesta incorrecta del modelo. |
| El tiempo disponible para el MVP es limitado. | El alcance se restringe deliberadamente a una sola capacidad de punta a punta (reabastecimiento de inventario), dejando el resto documentado como roadmap. |

## 15. Criterios de aceptación del MVP

El MVP se considera completo cuando:

1. El script de ingesta carga el dataset sintético en Supabase sin errores de validación.
2. El motor calcula ABC, XYZ, EOQ, stock de seguridad y ROP para todos los productos.
3. Se generan recomendaciones con los seis criterios evaluados y almacenados en `evaluaciones_criterios`.
4. La cola de recomendaciones se muestra priorizada en la interfaz.
5. El panel de explicabilidad muestra los seis criterios con estado y valor.
6. El agente responde preguntas sobre recomendaciones citando datos reales y rechaza responder cuando no tiene datos suficientes.
7. El administrador puede modificar un umbral en `parametros_configuracion` y el cambio se refleja sin necesidad de modificar código.

## 16. Roadmap (fuera del MVP)

- Incorporación de un modelo de Machine Learning para forecasting de demanda, como evolución del método estadístico actual.
- Integración con un sistema ERP real.
- Scoring multi-proveedor más completo, incluyendo variables adicionales de negociación.
- Ejecución automática de órdenes de compra hacia proveedores.
- Dashboards ejecutivos avanzados.
- Ajuste automático de umbrales de la rúbrica en función del desempeño histórico de las recomendaciones.
- Autenticación de nivel empresarial.
- Carga de archivos de datos como acción disponible desde la interfaz (en el MVP, la ingesta es un proceso manual ejecutado por separado; ver sección 8.3).
