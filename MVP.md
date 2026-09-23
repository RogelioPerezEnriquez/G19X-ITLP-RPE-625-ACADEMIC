# MVP — Sistema Inteligente de Optimización de Compras

**Versión:** 1.0 (MVP)
**Basado en:** PRD_Sistema_Optimizacion_Compras
**Estado:** Documento de alcance y definición del producto mínimo viable

---

## 1. Propósito del MVP

Construir un sistema de soporte a la decisión de compras que genere **recomendaciones cuantificadas y explicables** sobre qué comprar, cuánto, cuándo y a qué proveedor, a partir de un dataset sintético de inventario, demanda y desempeño de proveedores.

El MVP cubre **una sola capacidad de punta a punta**: reabastecimiento de inventario con evaluación explicada por criterios, más un agente conversacional de consulta en lenguaje natural.

> **Frase guía:** el valor del sistema no está en la interfaz, sino en el cálculo que produce las recomendaciones y en la justificación explícita de cada una.

---

## 2. Problema que resuelve el MVP

Las decisiones de compra suelen tomarse de forma reactiva y sin criterio cuantitativo repetible, lo que produce:

- Sobre-stock o quiebres de inventario.
- Selección subóptima de proveedores.
- Oportunidades de ahorro no detectadas (consolidación, descuentos por volumen).

Una hoja de cálculo permite registrar y consultar datos, pero **no calcula puntos de reorden, EOQ ni evalúa recomendaciones contra criterios explícitos de forma automática y consistente**.

### Qué NO es este MVP

No es un WMS ni un módulo de inventario de ERP. **No captura entradas ni salidas de producto.** Asume que los datos ya existen (dataset sintético) y se enfoca exclusivamente en la capa de decisión.

---

## 3. Objetivo del MVP

Demostrar, con una sola capacidad de punta a punta, que el sistema puede:

1. Calcular parámetros de inventario (ABC/XYZ, ROP, EOQ, stock de seguridad).
2. Evaluar cada recomendación contra seis criterios explícitos y configurables.
3. Explicar cada recomendación en lenguaje natural mediante un agente conversacional grounded.
4. Ser validado contra un dataset sintético con reglas de negocio conocidas.

---

## 4. Usuarios del MVP

| Usuario | Uso en el MVP |
|---|---|
| Comprador / analista de compras | Consume la cola de recomendaciones, revisa el panel de explicabilidad y consulta al agente. |
| Gerente de compras / supply chain | Consulta KPIs básicos y estado general de recomendaciones. |
| Administrador | Gestiona catálogos y parámetros de la rúbrica (sin modificar código). |

---

## 5. Alcance del MVP

### 5.1 Incluido

- **Ingesta** de dataset sintético (productos, proveedores, producto_proveedor, historial_demanda) vía CSV/Excel → Supabase.
- **Motor de optimización (OR):**
  - Clasificación ABC por valor económico acumulado.
  - Clasificación XYZ por coeficiente de variación.
  - Estimación de demanda (promedio móvil o suavizado exponencial simple).
  - EOQ, stock de seguridad y punto de reorden (ROP).
- **Rúbrica de evaluación** de 6 criterios con estados y umbrales configurables.
- **Agente conversacional** de solo lectura, grounded en datos calculados.
- **Interfaz:**
  - Cola de recomendaciones priorizada.
  - Panel de explicabilidad por recomendación.
  - Vista de proveedores.
  - Chat con el agente.
  - Panel de KPIs básicos.

### 5.2 Excluido (roadmap, sección 16)

- Machine Learning para forecasting.
- Integración con ERP real.
- Scoring multi-proveedor avanzado.
- Ejecución automática de órdenes de compra.
- Dashboards ejecutivos avanzados.
- Autoajuste automático de umbrales.
- SSO corporativo.
- Carga de archivos desde la interfaz (la ingesta es manual en el MVP).

---

## 6. Requisitos funcionales del MVP

| ID | Requisito |
|---|---|
| RF-01 | Cargar datos desde CSV/Excel a Supabase mediante script de ingesta separado del motor. |
| RF-02 | Calcular clasificación ABC y XYZ por producto. |
| RF-03 | Estimar demanda futura (promedio móvil o suavizado exponencial). |
| RF-04 | Calcular EOQ, stock de seguridad y ROP por producto. |
| RF-05 | Generar recomendación de compra (producto, proveedor, cantidad, fecha) cuando el stock lo amerite. |
| RF-06 | Evaluar cada recomendación contra los 6 criterios y asignar estado. |
| RF-07 | Presentar recomendaciones ordenadas por prioridad en una cola. |
| RF-08 | Mostrar detalle y justificación de criterios por recomendación. |
| RF-09 | Permitir consultas al agente sobre recomendaciones o criterios, citando datos reales. |
| RF-10 | Indicar explícitamente cuando no hay datos suficientes para responder. |
| RF-11 | Permitir al administrador modificar umbrales de la rúbrica sin tocar código. |
| RF-12 | Autenticar usuarios mediante Supabase Auth y restringir el acceso a la configuración de parámetros exclusivamente al rol Administrador. |

> **Nota de implementación:** no hay registro público de usuarios en el MVP. Las cuentas (comprador, gerente, administrador) se crean directamente en Supabase como parte de la configuración inicial, no mediante una pantalla de la aplicación.

---

## 7. Requisitos no funcionales del MVP

- **Explicabilidad:** ninguna recomendación sin justificación desglosada.
- **Trazabilidad:** cada recomendación rastreable a sus datos de entrada.
- **Configurabilidad:** umbrales en tabla de configuración, no en código.
- **Desacoplamiento de la ingesta:** el motor no depende del formato de origen.
- **Restricción de escritura del agente:** solo lectura; sin create/update/delete.
- **Control de acceso por rol:** configuración de parámetros restringida al rol Administrador; los demás roles solo consultan.

---

## 8. Arquitectura del MVP

| Componente | Tecnología |
|---|---|
| Motor de optimización | Python (pandas, numpy) |
| Persistencia y auth | Supabase (Postgres) |
| Agente conversacional | API de LLM con function calling |
| Frontend | Vue 3 (Vite, Vue Router, Pinia) |
| Visualización | Librería de gráficos embebida |

### 8.1 Pipeline

```
Dataset sintético (CSV/Excel)
        ↓
Script de ingesta (pandas → Supabase)
        ↓
Motor OR (ABC · XYZ · EOQ · ROP)
        ↓
Evaluación por criterios (rúbrica de 6)
        ↓
Agente conversacional (solo lectura)
        ↓
Interfaz (cola + explicabilidad + chat + KPIs)
```

### 8.2 Decisión de diseño: sin ML en el MVP

Se prioriza un componente de IA **verificable y acotado** (agente con funciones predefinidas) sobre un modelo predictivo que requeriría entrenamiento, validación y ajuste. El valor central del MVP es la **evaluación de recomendaciones contra criterios explícitos**, no el forecasting.

### 8.3 Ingesta (resumen)

1. Se genera un CSV/Excel por entidad con columnas del modelo de datos (sección 11).
2. Script de ingesta lee con pandas y valida columnas y campos clave.
3. Inserta en Supabase vía cliente Python.
4. A partir de ahí, motor, agente e interfaz consultan **solo Supabase**.

> La ingesta es una **operación manual** en el MVP, no una acción de la interfaz.

---

## 9. Motor de optimización — especificación

- **ABC:** ordenar por valor económico acumulado (precio × cantidad). A = 80% acumulado; B = 80–95%; C = 95–100%.
- **XYZ:** CV = desviación estándar / media. X: CV ≤ 0.5; Y: 0.5 < CV ≤ 1.0; Z: CV > 1.0.
  - El CV se calcula **una sola vez** por producto y se reutiliza para XYZ y para el criterio de confianza en la demanda.
- **Demanda estimada:** promedio móvil o suavizado exponencial simple.
- **ROP:** nivel de inventario que dispara un nuevo pedido (demanda estimada × lead time).
- **Stock de seguridad:** margen para cubrir variabilidad de demanda o lead time.
- **EOQ:** cantidad que minimiza costo de ordenar + costo de mantener.

---

## 10. Rúbrica de evaluación (6 criterios)

Todos los umbrales son **parámetros configurables**.

**1. Riesgo de quiebre de stock**
| Estado | Condición |
|---|---|
| Crítico | stock actual ≤ stock de seguridad |
| Atención | stock seguridad < stock actual ≤ ROP |
| Sin riesgo | stock actual > ROP |

**2. Eficiencia de la cantidad de pedido (vs. EOQ)**
| Estado | Condición |
|---|---|
| Pedido muy pequeño | cantidad < 90% EOQ |
| Óptima | 90%–110% EOQ |
| Pedido excesivo | cantidad > 110% EOQ |

**3. Confianza en la demanda estimada**
| Estado | Condición |
|---|---|
| Alta confianza | CV ≤ 0.5 |
| Confianza moderada | 0.5 < CV ≤ 1.0 |
| Baja confianza (revisión manual) | CV > 1.0 |

**4. Importancia del producto (ABC × XYZ)**

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

> Simplificación MVP: el exceso de inventario por descuento se asume mantenido un periodo completo.

---

## 11. Modelo de datos (MVP)

**productos**
`id, nombre, categoria, costo_unitario, stock_actual, costo_ordenar, costo_mantener_pct_anual`

**proveedores**
`id, nombre, cumplimiento_entrega_pct, tasa_defectos_pct`

**producto_proveedor**
`producto_id (FK), proveedor_id (FK), precio_unitario, lead_time_dias, cantidad_umbral_descuento, descuento_pct`

> Relación muchos a muchos: el motor elige proveedor por score y precio.

**historial_demanda**
`id, producto_id (FK), periodo, cantidad_demandada`

**recomendaciones**
`id, producto_id (FK), proveedor_id (FK), fecha_generacion, demanda_estimada, cv_demanda, punto_reorden, stock_seguridad, cantidad_eoq, clase_abc, clase_xyz, ahorro_neto_estimado`

**evaluaciones_criterios**
`id, recomendacion_id (FK), criterio, estado, valor_numerico`

**parametros_configuracion**
`nombre_parametro (PK), valor, descripcion`

---

## 12. Agente conversacional (MVP)

- **Rol:** analista de compras que explica recomendaciones. No decide ni ejecuta acciones.
- **Funciones de solo lectura:**
  - `buscar_recomendaciones()`
  - `detalle_recomendacion(producto_id)`
  - `explicar_criterio(producto_id, criterio)`
  - `comparar_proveedores()`
  - `resumen_prioridad_ABC_XYZ()`
- **Restricciones:** sin create/update/delete. Si no hay datos suficientes, lo indica explícitamente.
- **Grounding:** toda respuesta debe basarse en el resultado de una función consultada.

---

## 13. Interfaz — alcance del MVP

- **Cola de recomendaciones:** lista priorizada por urgencia e impacto.
- **Panel de explicabilidad:** desglose de los 6 criterios con estado y valor.
- **Vista de proveedores:** comparación con score y componentes.
- **Chat con el agente:** preguntas en lenguaje natural sobre recomendaciones o estado general.
- **Panel de KPIs:** recomendaciones críticas, ahorro estimado acumulado, distribución ABC/XYZ.
- **Pantalla de inicio de sesión:** sin registro público; acceso a configuración de parámetros restringido al rol Administrador.

---

## 14. Riesgos y supuestos del MVP

| Riesgo / supuesto | Mitigación |
|---|---|
| Datos sintéticos, no reales. | Reglas de negocio conocidas permiten validar contra resultado esperado. |
| Dependencia de proveedor externo de LLM. | Acceso restringido a funciones de solo lectura predefinidas. |
| Tiempo limitado. | Alcance restringido a una sola capacidad de punta a punta. |

---

## 15. Criterios de aceptación del MVP

El MVP se considera completo cuando:

1. El script de ingesta carga el dataset sintético en Supabase sin errores de validación.
2. El motor calcula ABC, XYZ, EOQ, stock de seguridad y ROP para todos los productos.
3. Se generan recomendaciones con los 6 criterios evaluados y almacenados en `evaluaciones_criterios`.
4. La cola de recomendaciones se muestra priorizada en la interfaz.
5. El panel de explicabilidad muestra los 6 criterios con estado y valor.
6. El agente responde preguntas sobre recomendaciones citando datos reales y **rechaza responder cuando no tiene datos**.
7. El administrador puede modificar un umbral en `parametros_configuracion` y el cambio se refleja sin tocar código.
8. Un usuario no autenticado o sin rol Administrador no puede acceder a la pantalla de configuración de parámetros.

---

## 16. Roadmap (post-MVP)

- ML para forecasting de demanda.
- Integración con ERP real.
- Scoring multi-proveedor avanzado.
- Ejecución automática de órdenes de compra.
- Dashboards ejecutivos avanzados.
- Autoajuste de umbrales según desempeño histórico.
- SSO corporativo.
- Carga de archivos desde la interfaz.

---