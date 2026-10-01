# Decisiones de diseño

Este documento registra las decisiones de diseño no obvias que se tomaron
durante la construcción del MVP del Sistema Inteligente de Optimización de
Compras, en formato ADR (Architecture Decision Record) simplificado: cada
decisión tiene un identificador estable (`D-NN`), el contexto en que se presentó,
las alternativas que se evaluaron, la opción elegida, su justificación y sus
consecuencias.

**Alcance.** Recoge solo lo que no se deduce del código ni de la
especificación. La definición del producto (alcance, requisitos, rúbrica de 6
criterios y modelo de datos) está en `MVP.md`; el estado de lo construido y
verificado, en `ESTADO_IMPLEMENTACION.md`; la deuda técnica abierta, en
`PENDIENTES.md`; y la guía para comprobar que el sistema funciona, en
`VERIFICACION.md`. Cuando hace falta ese nivel de detalle, este documento
referencia esos archivos en lugar de repetir su contenido.

**Cómo leerlo.** Las decisiones `D-01` a `D-10` son las que afectan el
comportamiento observable del sistema o su arquitectura, en el orden en que se
tomaron durante el desarrollo. La sección final lista, sin formato ADR, las
decisiones menores: convenciones de implementación aplicadas de forma
transversal. Cada decisión cierra con su implementación de referencia
(`archivo::función`), donde la decisión está materializada en código.

## Índice

- **D-01** — Lectura B del criterio 6 (oportunidad de ahorro por volumen)
- **D-02** — Correcciones de notación en las fórmulas del `MVP.md`
- **D-03** — Configurabilidad de alcance intermedio (Nivel 1.5)
- **D-04** — Conversiones de unidades en el consumidor
- **D-05** — Arquitectura de `recomendador.py` (función pura + E/S)
- **D-06** — Exclusiones silenciosas en `recomendador.py`
- **D-07** — Tolerancias en comparaciones de frontera
- **D-08** — Ordenamiento por urgencia con `pd.Categorical`
- **D-09** — Diseño de `guardar_recomendaciones`
- **D-10** — Datos sintéticos diseñados para ejercitar la rúbrica

---

## D-01: Lectura B del criterio 6 (oportunidad de ahorro por volumen)

**Contexto**: la fórmula abreviada del criterio 6 (`MVP.md` §10) condiciona el
ahorro bruto con un guardia: `ahorro_bruto = cantidad_EOQ × precio_unitario ×
descuento_pct`, "solo si `cantidad_EOQ >= cantidad_umbral_descuento`". El
enunciado admite dos lecturas y la nota de implementación del `PRD` (§10) no las
distingue: (A) el criterio solo reporta los casos en que el EOQ natural ya
alcanza el umbral de descuento, sin tocar la cantidad pedida; (B) el criterio
evalúa si conviene subir el pedido hasta el umbral para acceder al descuento.

**Alternativas consideradas**:

1. Lectura A: no modificar nunca la cantidad; informar únicamente los descuentos
   ya accesibles con el EOQ.
2. Lectura B: subir el pedido al umbral cuando el EOQ no lo alcanza y valorar el
   intercambio (descuento obtenido frente al costo de mantener el inventario
   adicional).
3. Diferir la decisión y dejar el criterio sin implementar hasta aclarar el
   alcance con el negocio.

**Decisión**: se implementó la lectura B en
`backend/src/motor/ahorro.py::calcular_ahorro`. La cantidad pedida es el EOQ
cuando el producto no tiene descuento declarado o cuando el EOQ ya alcanza el
umbral de descuento, y el umbral cuando el EOQ es menor; el exceso se valoriza
como costo de mantener prorrateado a un periodo y el ahorro neto se clasifica
contra un porcentaje del costo total del pedido. El módulo nunca reduce el
pedido por debajo del EOQ.

**Justificación**: el nombre del criterio ("oportunidad de ahorro *por
volumen*") describe una evaluación, no un reporte. Con la lectura A el criterio
sería inerte: el EOQ natural de los productos con descuento suele quedar por
debajo de su umbral (en el seed, los tres productos con
`cantidad_umbral_descuento` — Widget B, Engrane G7 y Tornillo M3 — tienen un EOQ
natural por debajo del umbral, así que la lectura A los declararía "Sin
oportunidad adicional", incluidos los dos que hoy tienen "Ahorro detectado").
Con la lectura B el criterio aporta la recomendación de negocio que el sistema
promete (subir el pedido cuando el descuento paga el exceso de inventario).
Además, el guardia de la fórmula se lee sin forzar el texto: describe el caso que
ya accede al descuento sin tocar la cantidad, no una prohibición de subirla.

**Consecuencias**:

- `cantidad_recomendada` puede ser mayor que `cantidad_eoq`; por eso
  `db/schema.sql` guarda las dos columnas por separado y el recomendador expone
  `cantidad_recomendada`, `ahorro_bruto`, `costo_extra_mantener` y
  `estado_ahorro`.
- El prorrateo del costo extra (una doceava parte del anual con el default de 12
  periodos) hace el criterio más permisivo que un cálculo anualizado; está
  registrado como caso conocido en `PENDIENTES.md`.
- La asimetría del contrato (`descuento_pct = 0` sube el pedido sin obtener
  ahorro) queda como caso conocido en `PENDIENTES.md`, no como defecto a
  corregir.
- Quien compare `MVP.md` con el código debe leer el docstring del módulo, que
  enuncia esta lectura de forma explícita.

**Implementación**: `backend/src/motor/ahorro.py::calcular_ahorro`; consumido por
`backend/src/recomendador.py::calcular_recomendaciones`.

## D-02: Correcciones de notación en las fórmulas del `MVP.md`

**Contexto**: las fórmulas del criterio 6 en `MVP.md` §10 (y en el `PRD`, con la
misma redacción) no son computables de forma literal: escriben `× descuento_pct`
y `× costo_mantener_pct_anual` sin división por 100 (los parámetros están en
porcentaje en `db/schema.sql`) y usan una variable `EOQ_sin_descuento` que no
existe como salida de `backend/src/motor/eoq_rop.py`.

**Alternativas consideradas**:

1. Implementar las fórmulas al pie de la letra.
2. Corregir `MVP.md` (documento de alcance ya aprobado) y dejar el código según
   el texto nuevo.
3. Implementar la interpretación matemáticamente coherente y documentar la
   desviación en el módulo, sin tocar los documentos de alcance.

**Decisión**: la opción 3. `calcular_ahorro` divide entre 100 los dos
porcentajes, prorratea el costo de mantener entre `periodos_por_año` (la
simplificación que declara la nota de implementación de `MVP.md` §10) e
interpreta `EOQ_sin_descuento` como la cantidad que en realidad se pide: la
cantidad extra `cantidad_pedido − cantidad_eoq`, que es 0 cuando no se sube el
pedido.

**Justificación**: la opción 1 produciría resultados sin sentido económico
(multiplicar por 5 o por 20 en lugar de por 0.05 y 0.20) y contradiría al resto
del motor, que ya divide los `*_pct` entre 100 (`H` en `eoq_rop.py`). El
`MVP.md` es un documento de alcance aprobado, así que se prefirió no
reescribirlo durante la implementación del motor y concentrar la desviación en
un único lugar verificable (el docstring de `ahorro.py`) en lugar de repartir
cambios entre documentos y código.

**Consecuencias**:

- `ahorro.py` pasa a ser la referencia de la notación efectiva; quien use
  `MVP.md` como fuente de cálculo debe contrastarla con este módulo (la
  alternativa 2 sigue abierta si los documentos se entregan como especificación
  formal).
- El `PRD` §10 arrastra la misma notación, de modo que la corrección aplica a
  los dos documentos.
- Efecto secundario deseado: el criterio 6 compara contra
  `costo_total_pedido × umbral_ahorro_pct / 100`, con la misma convención de
  porcentaje que el resto del sistema.

**Implementación**: `backend/src/motor/ahorro.py::calcular_ahorro` (docstring
del módulo, secciones "Resultado" y "Clasificación").

## D-03: Configurabilidad de alcance intermedio (Nivel 1.5)

**Contexto**: el requisito RF-11 y el criterio de aceptación 7 de `MVP.md` §15
exigen que un administrador pueda cambiar los umbrales de decisión sin tocar
código. El motor tenía todas sus constantes en código: los cortes de las
clasificaciones (ABC y XYZ), la ventana de demanda, los cortes del score de
proveedor y el umbral de ahorro, más otras de naturaleza técnica (periodos por
año, margen de seguridad, mínimo de periodos, pesos del score, etiquetas de
urgencia). Migrar todo a la tabla de configuración es trabajo y superficie de
error; no migrar nada incumple el requisito.

**Alternativas consideradas**:

1. Sin configurabilidad: dejar las constantes en los módulos (no cumple RF-11).
2. Alcance intermedio: configurar solo los umbrales de decisión con significado
   de negocio (los 10 que participan en la rúbrica y en las clasificaciones) y
   dejar en código las constantes estructurales o de redacción.
3. Configurabilidad total: llevar también a la tabla los periodos por año, el
   margen de seguridad, `MIN_PERIODOS`, los pesos del score y las etiquetas de
   urgencia.

**Decisión**: la opción 2. `db/schema.sql` define la tabla
`parametros_configuracion` con 10 filas; `backend/src/config.py` es el único
punto de entrada (`PARAMETROS_DEFAULT` como fuente única de verdad de los
valores por defecto y `cargar_parametros` como única función que toca Supabase);
cada módulo del motor recibe sus umbrales como argumento, con el default leído
de `config.PARAMETROS_DEFAULT`, y `recomendador.py` carga los parámetros y los
propaga ya resueltos. Las constantes que no se migraron quedan listadas, con su
motivo, en la deuda técnica de `PENDIENTES.md`.

**Justificación**: los 10 parámetros cubren RF-11 y todos los criterios de la
rúbrica, que es lo que un administrador necesita ajustar. Las constantes
restantes son estructurales (unidades de tiempo, mínimo de observaciones para
una desviación estándar), de ponderación interna del score o de redacción de
etiquetas; exponerlas obligaría a inventar semántica y validaciones para valores
que nadie pidió poder cambiar. El alcance intermedio mantiene el cambio pequeño
y verificable, y deja la puerta abierta a la configurabilidad total sin
rediseño: `cargar_parametros` no filtra claves extra, así que añadir filas a la
tabla no rompe el contrato de las 10 claves esperadas.

**Consecuencias**:

- Cambiar un umbral es un `UPDATE` sobre `parametros_configuracion` y surte
  efecto en la siguiente corrida, sin reiniciar ni tocar código; está verificado
  de punta a punta (bajar `abc_clase_a_pct` de 80 a 50 reclasificó 3 productos y
  subir `ahorro_neto_min_pct` de 3 a 10 dejó 0 productos con "Ahorro
  detectado").
- Los umbrales viajan como `float` y cada consumidor aplica la conversión que
  necesita (ver D-04).
- Las constantes no migradas son deuda técnica declarada, con el detalle en
  `PENDIENTES.md`; hoy solo `evaluador.py` tiene un test guardián que impide que
  los umbrales migrados vuelvan al módulo.
- "Nivel 1.5" es la etiqueta interna de este alcance intermedio; en los
  documentos del repositorio la misma fase se denomina "configurabilidad"
  (RF-11), así que este ADR es el que fija el nombre y su significado.

**Implementación**: `backend/src/config.py::PARAMETROS_DEFAULT` y
`::cargar_parametros`; parámetros de las firmas de `clasificar_abc`,
`clasificar_xyz`, `estimar_demanda`, `calcular_score_proveedor` y
`calcular_ahorro`; propagación en
`backend/src/recomendador.py::generar_recomendaciones`.

## D-04: Conversiones de unidades en el consumidor

**Contexto**: `parametros_configuracion.valor` es de tipo `numeric` y la tabla
guarda los valores en la unidad en la que un administrador los edita: los
`*_pct` en porcentaje (`90`, `3`) y `demanda_ventana_default` como número de
periodos. Los módulos, en cambio, necesitan fracciones en algunos casos y
enteros en otros, y cada uno tiene su propia convención de unidades documentada.

**Alternativas consideradas**:

1. Convertir en `config.py`: `cargar_parametros` devuelve ya las fracciones y
   los enteros.
2. Convertir en cada módulo consumidor, con la unidad declarada en su
   documentación.
3. Guardar en la tabla las fracciones y los enteros (`0.03`, `1.10`), de modo
   que ninguna conversión haga falta.

**Decisión**: la opción 2. `cargar_parametros` devuelve todos los valores como
`float(valor)`, sin transformaciones; `recomendador.calcular_recomendaciones`
hace `int(parametros["demanda_ventana_default"])`;
`evaluador.evaluar_recomendaciones` divide `eoq_min_pct`, `eoq_max_pct` y
`ahorro_neto_min_pct` entre 100 al resolver sus umbrales; y
`ahorro.calcular_ahorro` divide internamente su `umbral_ahorro_pct`, igual que
`eoq_rop.py` con `costo_mantener_pct_anual`. Los umbrales cuya unidad ya coincide
con la del módulo (`cv_confianza_*`, `score_proveedor_*`) se usan tal cual.

**Justificación**: `config.py` queda como un cargador simple y verificable (una
sola responsabilidad, sin reglas de negocio ni transformaciones ocultas) y cada
módulo conserva la unidad que declara en su docstring, además de seguir
validando sus propios rangos. Guardar las fracciones en la tabla (opción 3)
obligaría al administrador a escribir `0.03` para expresar 3 % y desalinearía
los valores de la tabla con los de `PARAMETROS_DEFAULT`, que están en porcentaje.

**Consecuencias**:

- La misma clave puede llegar con unidades distintas a módulos distintos
  (`ahorro_neto_min_pct` en porcentaje a `ahorro.py` y en fracción al evaluador).
  Es una convención deliberada, documentada en el docstring de `config.py`
  ("Unidades") y en el del evaluador ("Parámetros de configuración (fase 4)").
- Una unidad equivocada en la tabla no produce error: `config.py` no valida
  rangos por decisión (cada módulo valida lo suyo), así que un `3` escrito donde
  se espera `0.03` cambia clasificaciones en silencio.
- Un diccionario de parámetros incompleto no se completa con los defaults: falla
  con `KeyError` en la clave que falte.

**Implementación**: `backend/src/config.py::cargar_parametros`;
`backend/src/recomendador.py::calcular_recomendaciones`;
`backend/src/evaluador.py::evaluar_recomendaciones`;
`backend/src/motor/ahorro.py::calcular_ahorro`.

## D-05: Arquitectura de `recomendador.py` (función pura + E/S)

**Contexto**: `recomendador.py` es la primera pieza que coordina varias fuentes
de datos y, opcionalmente, escribe en Supabase (RF-05). Había que decidir cómo
separar el cálculo del acceso a datos sin perder la testabilidad de la que gozan
los seis módulos del motor, que son funciones puras y se prueban sin red ni
`.env`.

**Alternativas consideradas**:

1. Una sola función que lee, calcula y escribe.
2. Tres funciones con responsabilidades separadas: una pura que orquesta el
   motor, una de lectura y una de escritura.
3. Un servicio con estado (una clase) que reciba el cliente de Supabase por
   inyección.

**Decisión**: la opción 2.

- `calcular_recomendaciones(productos, proveedores, producto_proveedor,
  historial_demanda, parametros=None, periodos_por_año=12, dias_por_periodo=30,
  margen_seguridad_pct=0.20)` es pura: recibe DataFrames y devuelve un DataFrame,
  no accede a red, base de datos ni archivos, no imprime ni registra nada y no
  modifica sus entradas.
- `generar_recomendaciones(supabase_client)` solo lee (las cuatro tablas de datos
  más `parametros_configuracion`), normaliza los nombres de columna (`id` →
  `producto_id`/`proveedor_id`, `nombre` → `proveedor_nombre`) y delega el
  cálculo en la función pura.
- `guardar_recomendaciones` solo escribe (ver D-09).

El mismo patrón se replica en `evaluador.py`: `evaluar_recomendaciones` (pura),
`guardar_evaluaciones` (E/S) y `evaluar_y_guardar` (conveniencia).

**Justificación**: conserva el estilo del proyecto (el núcleo calculable se
prueba sin red; `backend/tests/test_recomendador.py` corre sin `.env`) y hace
explícito dónde está la lógica de negocio: las funciones de E/S no contienen
ninguna. La normalización de nombres vive en la capa de E/S para que la función
pura reciba siempre los nombres que el motor espera, sin traducciones internas.
La opción 3 (clase con estado) añadiría una indirección que el resto del código
no usa y no aporta nada mientras no existan varias implementaciones del cliente.

**Consecuencias**:

- El llamador debe leer los datos y pasarlos: no hay caché ni sesión. Los tres
  parámetros de `eoq_rop.py` (`periodos_por_año`, `dias_por_periodo`,
  `margen_seguridad_pct`) no se pueden ajustar desde `generar_recomendaciones`;
  quien los necesite debe usar la función pura.
- Los parámetros llegan como diccionario y no hay respaldo por clave: `None`
  significa "usar `PARAMETROS_DEFAULT`", pero un diccionario incompleto falla
  con `KeyError`.
- La convención (pura + E/S) es la que deben seguir los módulos futuros
  (`ingesta`, `agente`).
- El flujo de punta a punta obliga a persistir las recomendaciones antes de
  evaluarlas, porque el evaluador necesita el UUID; eso se resuelve en
  `scripts/demo_flujo_completo.py`.

**Implementación**: `backend/src/recomendador.py::calcular_recomendaciones` y
`::generar_recomendaciones`; mismo patrón en
`backend/src/evaluador.py::evaluar_recomendaciones`,
`::guardar_evaluaciones` y `::evaluar_y_guardar`.

## D-06: Exclusiones silenciosas en `recomendador.py`

**Contexto**: no todo producto del catálogo admite una recomendación. Hay
productos sin historial o con menos de 2 periodos (no hay desviación estándar
muestral), productos sin ninguna fila en `producto_proveedor` (no hay a quién
pedirle) y productos con coeficiente de variación no calculable (demanda media
0). Además, `db/schema.sql` declara `cv_demanda` y `clase_xyz` como `not null`,
así que no se pueden persistir recomendaciones con esas métricas incompletas.

**Alternativas consideradas**:

1. Incluirlos igual, con `NULL` o con la etiqueta "Sin oportunidad".
2. Lanzar `ValueError` al primer producto inválido.
3. Excluirlos en silencio y seguir con los productos válidos.
4. Excluirlos y devolver un reporte aparte con el motivo por producto.

**Decisión**: la opción 3. `calcular_recomendaciones` filtra en dos pasos: los
candidatos de `_productos_validos` (al menos `MIN_PERIODOS` filas de historial y
al menos una relación con proveedor) y, después, los que no tienen CV
calculable según la salida de `clasificar_xyz`. El resto del pipeline solo ve
productos válidos. Las exclusiones están documentadas en el docstring del módulo
("Casos borde") y el criterio está alineado a propósito con el de `xyz.py`: se
cuentan **filas** de historial, no periodos distintos, para que el mínimo
coincida con `MIN_PERIODOS`.

**Justificación**: un producto que el motor no puede calcular no es una
recomendación incompleta, es un producto fuera del alcance del sistema (sin
clase XYZ, sin proveedor o sin CV) y el `not null` de la tabla confirma que esas
filas no deben existir. Lanzar una excepción castigaría al llamador por un dato
que el esquema admite y que es normal en un catálogo real (productos nuevos sin
historial); la opción 4 añadiría un contrato de salida que hoy nadie consume.

**Consecuencias**:

- El descarte no se reporta: no hay conteo ni registro de excluidos. Si el panel
  de KPIs lo necesita, habrá que añadirlo; los tres motivos ya están descritos en
  el docstring.
- Con el seed no se percibe el efecto (los 6 productos son válidos) y la
  verificación de punta a punta genera 6 recomendaciones de 6 productos.
- Otros datos problemáticos sí fallan de forma ruidosa y deliberada: un nulo en
  una columna obligatoria de la salida dispara `_verificar_sin_nulos` y un
  `H = 0` propaga el `ValueError` de `eoq_rop.py` (el recomendador no captura
  errores del motor).

**Implementación**: `backend/src/recomendador.py::calcular_recomendaciones`,
`::_productos_validos` y `::_verificar_sin_nulos`.

## D-07: Tolerancias en comparaciones de frontera

**Contexto**: la rúbrica y las clasificaciones usan cortes inclusivos: un CV
exactamente 0.5 es clase X, un score exactamente 60 es "Aceptable con reservas",
un acumulado exactamente 80 % es clase A y un ahorro neto exactamente igual al
umbral es "Ahorro detectado". En `float64` esos valores no siempre son exactos:
un score matemático de 60 puede valer 59.99999999999999 (caso real documentado en
`proveedor.py` con cumplimiento 96 y tasa de defectos 94).

**Alternativas consideradas**:

1. Comparar de forma directa (`>=`, `<=`), aceptando el ruido.
2. Redondear a N decimales antes de comparar.
3. Comparar con una tolerancia absoluta del orden de 1e-9, sumada o restada
   según el lado inclusivo del corte.
4. Cambiar el pipeline numérico a `Decimal`.

**Decisión**: la opción 3. Cada módulo del motor define su constante
(`TOLERANCIA_PCT`, `TOLERANCIA_CV`, `TOLERANCIA_SCORE`, `TOLERANCIA_AHORRO`,
todas 1e-9) y `evaluador.py` repite el mismo criterio (`TOLERANCIA_RATIO`,
`TOLERANCIA_CV`, `TOLERANCIA_SCORE`, `TOLERANCIA_AHORRO`). La comparación se
escribe `cv <= umbral + tolerancia`, `score >= umbral − tolerancia`,
`ratio < eoq_min_pct/100 − tolerancia`, y así en cada frontera.

**Justificación**: el ruido de punto flotante es del orden de 1e-12, es decir,
diez órdenes de magnitud por debajo de las diferencias que importan (centavos o
centésimas de CV); 1e-9 corrige la frontera sin mover ninguna clasificación
significativa y es el mismo criterio en el motor y en el evaluador. El redondeo
introduce empates artificiales en el dígito de corte y `Decimal` obligaría a
reescribir todas las operaciones, que están vectorizadas con pandas y numpy.

**Consecuencias**:

- Efecto deliberado y documentado: una diferencia real menor que 1e-9 también cae
  del otro lado del corte; hay un test explícito para ese caso en
  `backend/tests/test_ahorro.py`.
- La tolerancia es absoluta, no relativa: sobre magnitudes pequeñas pesa
  proporcionalmente más.
- El criterio 1 (`riesgo_quiebre_stock`) queda fuera de esta decisión: compara
  importes de inventario tal cual los enuncia `MVP.md` §10, sin aritmética de
  porcentajes que introduzca ruido.
- Las constantes están duplicadas por módulo (una por archivo, con el mismo valor
  y el mismo comentario) y hay tests que fijan sus valores; replicar el test
  guardián a los demás módulos del motor está en `PENDIENTES.md`.

**Implementación**: `backend/src/motor/abc.py`, `xyz.py`, `proveedor.py` y
`ahorro.py`; `backend/src/evaluador.py::evaluar_recomendaciones`.

## D-08: Ordenamiento por urgencia con `pd.Categorical`

**Contexto**: la cola de recomendaciones debe salir priorizada por urgencia de
negocio (Crítico, Atención, Sin riesgo), después por ahorro estimado descendente
y con un desempate determinista. Los tres valores son etiquetas de texto, y un
orden alfabético dejaría "Atención" antes que "Crítico" (y "Crítico" al final).

**Alternativas consideradas**:

1. Añadir una columna numérica de prioridad, ordenar por ella y descartarla
   después.
2. Ordenar con una función de clave (`key=`) o mapeando las etiquetas antes de
   ordenar.
3. Convertir la columna a `pd.Categorical` ordenado con las categorías en el
   orden de prioridad y ordenar con `ascending=True`.

**Decisión**: la opción 3, en `recomendador.calcular_recomendaciones`:
`ORDEN_URGENCIA = ["Crítico", "Atención", "Sin riesgo"]`, la columna `urgencia`
se construye como `pd.Categorical(..., categories=ORDEN_URGENCIA, ordered=True)`
y la salida se ordena con
`sort_values(by=["urgencia", "ahorro_neto_estimado", "producto_id"],
ascending=[True, False, True], kind="mergesort")`. El mismo idioma se usa en
`evaluador.py` para el orden lógico de los 6 criterios (`ORDEN_CRITERIOS`).

**Justificación**: la etiqueta de negocio sigue siendo el único valor visible de
la columna (no se añade un campo auxiliar que habría que mantener sincronizado ni
una tabla de mapeo duplicada), el tipo categórico viaja con el DataFrame (de modo
que cualquier orden o agrupación posterior respeta la jerarquía) y
`kind="mergesort"` es estable, lo que hace determinista el desempate final. Como
las categorías ya están en orden de prioridad, "Crítico" es la categoría menor y
el orden pedido se obtiene con `ascending=True`; eso es contraintuitivo, así que
el código lo advierte en los comentarios y en el docstring (con
`ascending=False` saldría el orden inverso).

**Consecuencias**:

- El contrato de la salida vacía construye la misma categórica
  (`pd.Categorical([], categories=ORDEN_URGENCIA, ordered=True)`), de modo que la
  salida vacía y la no vacía tienen el mismo tipo de dato; hay tests que
  verifican tipo, categorías y orden.
- Los consumidores que serializan a Supabase o a JSON ven las etiquetas como
  texto (el `insert` convierte los escalares; ver D-09), no como categorías.
- Cambiar la jerarquía de urgencia es editar una sola lista (`ORDEN_URGENCIA`) en
  un solo archivo.

**Implementación**: `backend/src/recomendador.py::calcular_recomendaciones` (paso
7) y la constante `ORDEN_URGENCIA`; mismo patrón con `ORDEN_CRITERIOS` en
`backend/src/evaluador.py::evaluar_recomendaciones`.

## D-09: Diseño de `guardar_recomendaciones`

**Contexto**: las recomendaciones se persisten en la tabla `recomendaciones`
(RLS de solo lectura para `anon`/`authenticated`; la escritura se hace con
`service_role`) y el evaluador necesita el `recomendacion_id` (uuid) de cada
recomendación ya persistida, porque `evaluaciones_criterios.recomendacion_id` es
una clave foránea. El motor calcula recomendaciones **sin** `id`: el uuid lo
genera Supabase al insertar. La tabla tiene además columnas que el motor no
produce (`id`, `fecha_generacion`, `estado`).

**Alternativas consideradas**:

1. Que la función solo inserte y no devuelva nada (fue su primera versión).
2. Devolver solo los identificadores generados, o un conteo de filas escritas.
3. Devolver las filas insertadas que retorna la API, como DataFrame.
4. Insertar y volver a leer la tabla filtrando por marca de tiempo para recuperar
   los uuid.
5. Que el evaluador resuelva los uuid por su cuenta.

**Decisión**: la opción 3 (adoptada en el commit `06f48e4`, que cambió el
contrato de la opción 1). `guardar_recomendaciones(supabase_client,
recomendaciones)` filtra las 13 columnas de `COLUMNAS_RECOMENDACIONES` (deja
`id`, `fecha_generacion` y `estado` a los valores por defecto de la base:
`gen_random_uuid()`, `now()` y `'pendiente'`), convierte los escalares de numpy a
tipos nativos (el cliente serializa con el módulo `json` estándar, que no
reconoce `np.int64` ni `np.float64`) e inserta. Devuelve
`pd.DataFrame(respuesta.data)`, es decir, las recomendaciones ya persistidas con
sus uuid. Un DataFrame sin filas devuelve un DataFrame vacío sin hacer ninguna
petición; si la API no devuelve filas, se devuelve un DataFrame vacío en lugar de
fallar; los errores de la API (RLS con `anon key`, clave foránea inexistente,
nulo en un `not null`, timeout) se propagan. La función **no** escribe en
`evaluaciones_criterios`.

**Justificación**: el uuid solo lo conoce la respuesta del `insert`, así que
devolverla es la forma más simple y barata de encadenar el evaluador, sin una
segunda consulta ni una transacción adicional (la opción 4 sería frágil: exigiría
discriminar por `fecha_generacion`). Dejar `id`, `fecha_generacion` y `estado` a
la base mantiene una única fuente de verdad del ciclo de vida de la
recomendación. No escribir las evaluaciones respeta la separación de
responsabilidades: la rúbrica es responsabilidad del evaluador (ver D-05).

**Consecuencias**:

- El llamador debe cruzar las filas devueltas con el DataFrame del motor por
  `producto_id` para reconstruir la entrada del evaluador: columnas que el
  evaluador necesita (`stock_actual`, `costo_total_pedido`, `score_proveedor`)
  no se guardan en `recomendaciones`. El cruce 1:1 está implementado en
  `scripts/demo_flujo_completo.py` y cubierto por sus tests.
- De ahí que el demo advierta que la tabla debería estar vacía antes de una
  corrida (el cruce usa solo la respuesta del `insert` de esa ejecución) y que
  "si no se guarda, no hay evaluaciones" (sin `recomendacion_id`, el `insert` del
  evaluador fallaría por clave foránea).
- El DataFrame devuelto trae solo columnas de la tabla: no hay recálculo ni
  reconciliación de importes.
- Las corridas se acumulan: la función solo inserta, no limpia ni reemplaza; el
  ciclo de vida se gestiona con la columna `estado` (`pendiente`, `revisada`,
  `descartada`).
- Si la API no devuelve las filas insertadas, un escritor exitoso se reporta con
  un DataFrame vacío: es un éxito silencioso deliberado.

**Implementación**: `backend/src/recomendador.py::guardar_recomendaciones` y
`COLUMNAS_RECOMENDACIONES`; uso en `scripts/demo_flujo_completo.py` (pasos 2 y 3).

## D-10: Datos sintéticos diseñados para ejercitar la rúbrica

**Contexto**: el MVP no se valida con datos reales, sino contra un dataset
sintético con reglas de negocio conocidas (`MVP.md` §14), porque es la única
forma de comprobar que el motor y la rúbrica producen lo esperado. Con un
dataset arbitrario no se puede afirmar si un resultado es correcto o es un
defecto.

**Alternativas consideradas**:

1. Datos aleatorios (un generador propio o una librería tipo `faker`).
2. Un dataset pequeño diseñado a mano según los resultados que se quieren
   ejercitar: cada criterio de la rúbrica, cada clasificación ABC/XYZ y cada
   estado de proveedor.
3. Generar los datos a partir de las salidas deseadas del motor (ingeniería
   inversa del cálculo).

**Decisión**: la opción 2, en `db/seed_sintetico.sql`:

- 6 productos con un CV objetivo por serie: Widget A ~0.20 (X), Widget B ~0.70
  (Y), Tornillo M3 ~0.25 (X), Cable HDMI ~1.40 (Z), Engrane G7 ~1.30 (Z) y
  Pintura 1L ~0.80 (Y).
- Costos unitarios de 0.80 a 85.00, para que el valor económico acumulado
  reparta clases ABC.
- 4 proveedores que cubren los tres estados del criterio 5 (scores 96.2, 86.0,
  76.0 y 50.0, calculados con la fórmula del criterio y anotados como
  comentario).
- 8 relaciones producto-proveedor, con Widget A con dos proveedores (para poder
  comparar) y Engrane G7 con descuento por volumen (criterio 6).
- 72 registros de demanda (12 periodos mensuales por producto) y stock calibrado
  para intentar cubrir los tres estados del criterio 1.

Todos los nombres llevan el prefijo `SEED_` para poder borrar el dataset de
forma selectiva y el seed no toca `parametros_configuracion`.

**Justificación**: un dataset diseñado hace que los resultados sean predecibles:
12 periodos mensuales dan margen al promedio móvil (ventana 6) y permiten una
desviación estándar muestral (`ddof=1`); las magnitudes de costo dispersan el
acumulado ABC; y los estados de proveedor, de urgencia y de ahorro se pueden
anticipar. Así, cualquier diferencia entre lo esperado y lo obtenido es
evidencia (de un defecto o de una decisión de modelado), no ruido. En
particular, permite sostener que "cada criterio de la rúbrica tiene al menos un
caso que lo ejercita", que es lo que la evaluación del MVP necesita demostrar.

**Consecuencias**:

- Los CV se estimaron a ojo al escribir el seed y el motor calcula los reales,
  que resultan más bajos: las clases ABC/XYZ obtenidas no coinciden del todo con
  las diseñadas (Engrane G7: diseñado A/Z, real A/Y; Widget B: A/Y frente a A/X;
  Cable HDMI: C/Z frente a C/Y; Pintura 1L: C/Y frente a A/X). Está declarado
  como deuda técnica en `PENDIENTES.md`, junto con la opción de reajustar el
  seed.
- Ningún producto cae en "Crítico" pese a que el stock se calibró para eso: el
  stock de seguridad calculado con la demanda estimada queda por debajo del
  `stock_actual`. También está en `PENDIENTES.md` (opcional, para la demo).
- El seed es un fixture, no datos de producción: el sistema funciona con
  cualquier dataset que respete `db/schema.sql`.
- La correspondencia entre "criterio de la rúbrica" y "producto del seed" es
  implícita (vive en los comentarios del SQL); no hay un test que la garantice.

**Implementación**: `db/seed_sintetico.sql` (comentarios de cabecera de cada
bloque); resultados observados en `ESTADO_IMPLEMENTACION.md`.

## D-11: Tools del agente usan `producto_nombre` en lugar de `producto_id`

**Contexto**: El MVP.md §12 define las tools del agente con firma
`detalle_recomendacion(producto_id)` y `explicar_criterio(producto_id,
criterio)`. Sin embargo, el agente es una interfaz conversacional: los
usuarios preguntan por nombre ("¿qué pasa con SEED_Widget A?"), no por
UUIDs.

**Alternativas consideradas**:
- A) Usar `producto_id` (UUID) como el MVP.
- B) Usar `producto_nombre`.
- C) Aceptar ambos.

**Decisión**: **B** (usar `producto_nombre`).

**Justificación**:
1. El LLM no conoce los UUIDs del sistema.
2. El usuario pregunta por nombre.
3. La tool hace el lookup nombre → UUID internamente.

**Consecuencias**:
- Firma de las tools distinta al MVP (documentado aquí).
- Si hay nombres duplicados, la tool lanza `ValueError`.
- Si en el futuro se necesita `producto_id`, se puede añadir como
  parámetro opcional.
  
---

## Otras decisiones menores

Convenciones de implementación aplicadas de forma transversal. No cambian el
comportamiento de negocio, pero conviene dejarlas registradas porque se repiten
en varios módulos o porque explican por qué el código está escrito de una
determinada manera.

- **Año comercial de 360 días.** `eoq_rop.py` y `ahorro.py` usan 12 periodos por
  año y 30 días por periodo por defecto, lo que implica un año de 360 días. Los
  dos módulos comparten la convención para que sus unidades de tiempo sean
  consistentes; un llamador que trabaje con periodos semanales debe pasar sus
  propios valores (`periodos_por_año=52`, `dias_por_periodo=7`).
- **Cálculo de la demanda con promedio móvil.** `MVP.md` admite promedio móvil o
  suavizado exponencial simple; se eligió el promedio móvil de los `ventana`
  periodos más recientes (`demanda_ventana_default`). Un producto con menos
  periodos que la ventana se promedia con lo que tenga, y la salida queda en
  unidades por periodo (no se anualiza).
- **Tres funciones en cada módulo con E/S.** `recomendador.py` y `evaluador.py`
  exponen exactamente tres funciones: la pura, la de escritura y, en
  `evaluador.py`, una de conveniencia que evalúa y guarda en una sola llamada. Es
  la convención que deben seguir los módulos futuros.
- **`TYPE_CHECKING` para no importar `supabase` en `config.py`.** El cliente de
  Supabase se importa únicamente para las anotaciones de tipo, de modo que
  importar `config.py` no depende del paquete en tiempo de ejecución y los tests
  de la función pura no lo necesitan. `evaluador.py` aplica el mismo patrón.
- **`config.py` como único punto de entrada de parámetros.** Ningún módulo del
  motor lee de Supabase: `generar_recomendaciones` carga los parámetros y los
  pasa ya resueltos a cada módulo.
- **`PARAMETROS_DEFAULT` como fuente única de verdad de los valores por
  defecto.** Los defaults de las firmas se leen de ahí; las constantes migradas
  se eliminaron de los módulos y un test guardián en `evaluador.py` impide que
  vuelvan.
- **`cargar_parametros` exige las 10 claves y no filtra las extra.** Si falta un
  parámetro (incluida una tabla vacía) lanza `ValueError`; si la tabla trae claves
  nuevas, también se devuelven, de modo que añadir una fila no rompe el contrato
  de las 10 claves esperadas.
- **Normalización de nombres de columna en la capa de E/S.**
  `generar_recomendaciones` renombra `id` a `producto_id`/`proveedor_id` y
  `nombre` a `proveedor_nombre`, para que la función pura reciba siempre los
  nombres que el motor espera (y sus tests los construyan directamente).
- **Validación estricta de columnas en todo el motor.** Los seis módulos lanzan
  `ValueError` si falta una columna requerida, incluso con el DataFrame vacío
  (`abc.py` se unificó a este criterio).
- **Determinismo en los órdenes y en los empates.** La salida de cada módulo es
  determinista: ABC ordena por valor económico descendente y desempata por
  `producto_id`; el proveedor elegido es el de mayor score y, en caso de empate,
  el de menor precio (y luego el primero en `producto_proveedor`); el recomendador
  ordena con `mergesort` estable.
- **Errores del motor: se propagan, no se capturan.** Un dato que el esquema
  admite pero que el motor no puede calcular (`H = 0`) es un problema del
  llamador; el recomendador no lo esconde.
- **Contrato de salida vacía.** La salida vacía conserva las columnas y los tipos
  de dato de la salida real (incluidas las categóricas ordenadas), para que el
  consumidor no tenga que tratar dos formas distintas.
- **Cortes del score del proveedor que no afectan al recomendador.** Los umbrales
  `score_proveedor_confiable` y `score_proveedor_riesgoso` se propagan al motor,
  pero el recomendador elige proveedor solo por `score`; cambiar esos umbrales no
  cambia las recomendaciones, solo la clasificación del criterio 5 en el
  evaluador (y lo que se muestre en el frontend).
- **Snapshot trazable del proveedor elegido.** `recomendaciones` guarda
  `lead_time_dias` y `precio_unitario` del proveedor elegido en el momento de
  recomendar, además de `cantidad_recomendada` separada de `cantidad_eoq` y un
  `estado` (`pendiente`, `revisada`, `descartada`) para el ciclo de vida.
- **Escritura solo con `service_role`.** RLS está habilitado en las 7 tablas con
  políticas de solo lectura para `anon` y `authenticated`; todo el backend escribe
  con `service_role`, y el frontend y el agente leerán con `anon`.
- **Ingesta manual en el MVP.** El paquete `backend/src/ingesta/` está vacío por
  decisión de alcance: los datos entran aplicando `db/schema.sql` y
  `db/seed_sintetico.sql` en el editor SQL de Supabase (`MVP.md` §8.3).
