# Sistema Inteligente de Optimización de Compras

MVP de un sistema de soporte a la decisión de compras que genera
recomendaciones cuantificadas y explicables sobre qué comprar, cuánto,
cuándo y a qué proveedor.

El proyecto cubre una sola capacidad de punta a punta: **reabastecimiento
de inventario con evaluación explicada por criterios**, más un agente
conversacional de consulta en lenguaje natural.

---

## Estado del proyecto

🚧 En desarrollo.

| Componente | Estado |
|---|---|
| Esquema de base de datos (Supabase) | ✅ |
| Datos sintéticos de prueba | ✅ |
| Verificación de RLS | ✅ |
| Conexión con LLM (Z.ai) | ✅ |
| Motor OR (ABC, XYZ, demanda, EOQ, ROP, proveedor, ahorro) | ✅ |
| Recomendador (orquestador del motor) | ✅ |
| Evaluador (rúbrica de 6 criterios) | ✅ |
| Configurabilidad de umbrales | ✅ |
| Agente conversacional | ⏳ |
| Frontend (Vue 3) | ⏳ |
| Script de ingesta CSV/Excel | ⏳ |

---

## Datos

⚠️ **Este proyecto usa datos sintéticos**, no reales. Los datasets fueron
diseñados específicamente para ejercitar los 6 criterios de la rúbrica de
evaluación y permitir validar el motor contra resultados esperados.

El seed en `db/seed_sintetico.sql` carga:

- 6 productos con perfiles ABC×XYZ distintos.
- 4 proveedores con scores de confiabilidad distintos.
- 8 relaciones producto-proveedor (incluye casos con descuento por volumen).
- 72 registros de demanda (12 periodos × 6 productos).

Los datos no deben confundirse con datos de producción. El sistema
funciona con cualquier dataset que respete el esquema de `db/schema.sql`.

---

## Estructura del repositorio

```
.
├── db/                    Esquema SQL y seed de datos
│   ├── schema.sql         Esquema de las 7 tablas + RLS + parámetros
│   └── seed_sintetico.sql Datos de prueba
├── backend/               Lógica de negocio (Python)
│   ├── src/
│   │   ├── motor/         Motor OR (6 módulos puros)
│   │   ├── config.py      Carga de parámetros de configuración
│   │   ├── recomendador.py Orquestador del motor
│   │   └── evaluador.py   Rúbrica de 6 criterios
│   ├── tests/             Suite de tests (pytest)
│   └── requirements.txt
├── scripts/               Scripts de verificación y demo
│   ├── verificar_*.py     Verificación de entorno (RLS, service_role, LLM)
│   ├── demo_recomendador.py
│   └── demo_flujo_completo.py
├── frontend/              Interfaz de usuario (Vue 3) [pendiente]
├── MVP.md                 Definición del producto mínimo viable
├── PRD_*.md               Documento de requisitos
├── ESTADO_IMPLEMENTACION.md  Estado actual de la implementación
├── DECISIONES_DISENO.md      Decisiones de diseño del proyecto
└── PENDIENTES.md          Deuda técnica
```

---

## Stack

| Componente | Tecnología |
|---|---|
| Motor de optimización | Python 3.11+ (pandas, numpy) |
| Persistencia y auth | Supabase (Postgres) |
| Agente conversacional | Z.ai (GLM) con function calling |
| Frontend | Vue 3 (Vite, Vue Router, Pinia) |
| Visualización | Librería de gráficos embebida |
| Testing | pytest |

---

## Setup

### 1. Clonar el repositorio

```bash
git clone <url-del-repo>
cd OptimizaCompras
```

### 2. Configurar variables de entorno

Copia `.env.example` a `.env` y rellena con tus valores reales.

En Linux / macOS:

```bash
cp .env.example .env
```

En Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Variables requeridas:

| Variable | Descripción |
|---|---|
| `SUPABASE_URL` | URL del proyecto Supabase |
| `SUPABASE_ANON_KEY` | Key pública (solo lectura, para frontend y agente) |
| `SUPABASE_SERVICE_ROLE_KEY` | Key secreta (escritura, solo backend) |
| `LLM_PROVIDER` | Proveedor de LLM (`zai`) |
| `LLM_BASE_URL` | Endpoint del LLM |
| `LLM_API_KEY` | API key del LLM |
| `LLM_MODEL` | Identificador del modelo |

⚠️ **Nunca** subas el archivo `.env` al repositorio. Está en `.gitignore`.

### 3. Crear las tablas en Supabase

En el SQL Editor de Supabase, ejecutar en orden:

1. `db/schema.sql` — crea las 7 tablas, habilita RLS y carga los 10
   parámetros de configuración.
2. `db/seed_sintetico.sql` — carga los datos de prueba.

### 4. Instalar dependencias de Python

```bash
cd backend
pip install -r requirements.txt
```

### 5. Verificar el entorno

Desde la raíz del proyecto:

```bash
python scripts/verificar_rls.py
python scripts/verificar_service_role.py
python scripts/verificar_zai.py
```

Los tres deben terminar sin errores.

### 6. Correr la suite de tests

```bash
cd backend
python -m pytest -q
```

Todos los tests deben pasar.

---

## Configurabilidad

El sistema es **configurable sin tocar código**. Los umbrales de decisión
viven en la tabla `parametros_configuracion` de Supabase, y los módulos
del motor los reciben como parámetros.

**Los 10 parámetros configurables**:

| Parámetro | Valor por defecto | Descripción |
|---|---|---|
| `abc_clase_a_pct` | 80 | Porcentaje acumulado máximo para clase A |
| `abc_clase_b_pct` | 95 | Porcentaje acumulado máximo para clase B |
| `ahorro_neto_min_pct` | 3 | Porcentaje mínimo de ahorro neto para "Ahorro detectado" |
| `cv_confianza_alta` | 0.5 | CV máximo para "alta confianza" / clase X |
| `cv_confianza_media` | 1.0 | CV máximo para "confianza moderada" / clase Y |
| `demanda_ventana_default` | 6 | Periodos a promediar en la estimación de demanda |
| `eoq_max_pct` | 110 | Límite superior (%) de cantidad vs. EOQ |
| `eoq_min_pct` | 90 | Límite inferior (%) de cantidad vs. EOQ |
| `score_proveedor_confiable` | 80 | Score mínimo para proveedor "confiable" |
| `score_proveedor_riesgoso` | 60 | Score por debajo del cual es "riesgoso" |

**Cómo cambiar un umbral**:

```sql
UPDATE parametros_configuracion
SET valor = <nuevo_valor>
WHERE nombre_parametro = '<nombre_del_parametro>';
```

El cambio se refleja en la siguiente ejecución del motor (no requiere
reiniciar ni tocar código).

---

## Arquitectura

```
Dataset sintético (SQL seed)
        ↓
Supabase (Postgres + RLS)
        ↓
config.py (carga de parámetros)
        ↓
Motor OR (6 módulos puros)
  ├── abc.py        Clasificación ABC
  ├── xyz.py        Clasificación XYZ
  ├── demanda.py    Estimación de demanda
  ├── eoq_rop.py    EOQ, stock de seguridad, ROP
  ├── proveedor.py  Score de proveedores
  └── ahorro.py     Oportunidad de ahorro por volumen
        ↓
recomendador.py (orquesta el motor)
        ↓
evaluador.py (aplica la rúbrica de 6 criterios)
        ↓
Agente conversacional (solo lectura) [pendiente]
        ↓
Interfaz (cola + explicabilidad + chat + KPIs) [pendiente]
```

Ver `MVP.md` para detalle de cada componente, `PENDIENTES.md` para deuda
técnica y `DECISIONES_DISENO.md` para decisiones de diseño.

---

## Scripts de demo

**`demo_recomendador.py`**: genera recomendaciones con datos reales del
seed y las imprime en terminal.

```bash
python scripts/demo_recomendador.py
```

**`demo_flujo_completo.py`**: genera recomendaciones, las evalúa contra la
rúbrica y las guarda opcionalmente en Supabase.

```bash
python scripts/demo_flujo_completo.py
```

---

## Licencia

Proyecto académico. Uso educativo.