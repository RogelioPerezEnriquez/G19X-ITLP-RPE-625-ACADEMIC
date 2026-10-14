# Sistema Inteligente de Optimización de Compras

MVP de un sistema de soporte a la decisión de compras que genera
recomendaciones cuantificadas y explicables sobre qué comprar, cuánto,
cuándo y a qué proveedor.

El proyecto cubre una sola capacidad de punta a punta: **reabastecimiento
de inventario con evaluación explicada por criterios**, más un agente
conversacional de consulta en lenguaje natural.

---

## Estado del proyecto

MVP funcionalmente completo.

| Componente | Estado |
|---|---|
| Esquema de base de datos (Supabase) | Completo |
| Datos sintéticos de prueba | Completo |
| Verificación de RLS | Completo |
| Conexión con LLM (Z.ai) | Completo |
| Motor OR (ABC, XYZ, demanda, EOQ, ROP, proveedor, ahorro) | Completo |
| Recomendador (orquestador del motor) | Completo |
| Evaluador (rúbrica de 6 criterios) | Completo |
| Configurabilidad de umbrales | Completo |
| Agente conversacional | Completo |
| Frontend (Vue 3) | Completo |
| Script de ingesta CSV/Excel | Completo |

Ver `docs/estado-implementacion.md` para el detalle del estado y
`docs/verificacion-final.md` para la verificación de los 8 criterios de
aceptación.

---

## Datos

**Este proyecto usa datos sintéticos**, no reales. Los datasets fueron
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
├── db/                          Esquema SQL, seed y scripts de restauración
│   ├── schema.sql               Esquema completo (8 tablas + RLS + políticas + parámetros)
│   ├── seed_sintetico.sql       Datos de prueba
│   └── restaurar_parametros.sql Restaurar los 10 parámetros a sus valores por defecto
├── backend/                     Lógica de negocio (Python)
│   ├── src/
│   │   ├── motor/               Motor OR (6 módulos puros)
│   │   ├── agente/              Agente conversacional + API FastAPI
│   │   ├── ingesta/             Script de ingesta CSV/Excel
│   │   ├── config.py            Carga de parámetros de configuración
│   │   ├── recomendador.py      Orquestador del motor
│   │   └── evaluador.py         Rúbrica de 6 criterios
│   ├── tests/                   Suite de tests (pytest)
│   └── requirements.txt
├── frontend/                    Interfaz de usuario (Vue 3)
│   ├── src/
│   │   ├── views/               6 vistas (recomendaciones, explicabilidad, proveedores, chat, KPIs, configuración)
│   │   ├── components/          Componentes reutilizables
│   │   ├── stores/              Stores de Pinia
│   │   ├── services/            Cliente de Supabase
│   │   └── router/              Rutas y guards
│   └── package.json
├── scripts/                     Scripts de verificación, demo y API
│   ├── verificar_*.py           Verificación de entorno (RLS, service_role, LLM, agente)
│   ├── demo_*.py                Demos del motor
│   └── run_api.py               Levantar la API del agente
├── data/                        Datos de entrada (CSVs de ejemplo)
├── docs/                        Documentación del proyecto
│   ├── estado-implementacion.md
│   ├── decisiones-diseno.md
│   ├── verificacion.md
│   ├── verificacion-final.md
│   └── pendientes.md
└── README.md
```

**Nota**: el PRD y el MVP no están incluidos en el repositorio; se
distribuyen en la plataforma.

---

## Stack

| Componente | Tecnología |
|---|---|
| Motor de optimización | Python 3.11+ (pandas, numpy) |
| Persistencia y auth | Supabase (Postgres + Auth + RLS) |
| API del agente | FastAPI + uvicorn |
| Agente conversacional | Z.ai (GLM) con function calling |
| Frontend | Vue 3 (Vite, Vue Router, Pinia, Tailwind CSS) |
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
| `VITE_SUPABASE_URL` | URL de Supabase (para el frontend) |
| `VITE_SUPABASE_ANON_KEY` | Key pública (para el frontend) |
| `VITE_API_URL` | URL de la API del agente (por ejemplo, `http://localhost:8000`) |

**Nunca** subas el archivo `.env` al repositorio. Está en `.gitignore`.

### 3. Crear las tablas en Supabase

En el SQL Editor de Supabase, ejecutar en orden:

1. `db/schema.sql` — crea las 8 tablas (7 de datos + `admins`), habilita
   RLS, define las políticas y carga los 10 parámetros de configuración.
2. `db/seed_sintetico.sql` — carga los datos de prueba.

### 4. Crear el usuario administrador

1. Registrar un usuario desde el frontend (o desde Supabase Auth).
2. Obtener su `user_id`.
3. Insertar en la tabla `admins`:

```sql
INSERT INTO admins (user_id) VALUES ('<uuid-del-usuario>');
```

### 5. Instalar dependencias del backend

```bash
cd backend
pip install -r requirements.txt
```

### 6. Instalar dependencias del frontend

```bash
cd frontend
npm install
```

### 7. Verificar el entorno

Desde la raíz del proyecto:

```bash
python scripts/verificar_rls.py
python scripts/verificar_service_role.py
python scripts/verificar_zai.py
```

Los tres deben terminar sin errores.

### 8. Correr la suite de tests

```bash
cd backend
python -m pytest -q
```

Todos los tests deben pasar.

Ver `docs/verificacion.md` para la guía completa de verificación.

### 9. Levantar el sistema completo

El sistema requiere 2 procesos en paralelo:

**Terminal 1 — API del agente:**

```bash
python scripts/run_api.py
```

FastAPI levanta el servidor en `http://localhost:8000`.

**Terminal 2 — Frontend:**

```bash
cd frontend
npm run dev
```

Vite levanta el servidor en `http://localhost:5173`.

Acceder a `http://localhost:5173` y loguearse con el usuario admin.

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

**Cómo cambiar un umbral**: desde la pantalla de configuración del
frontend (solo administradores), o directamente en Supabase:

```sql
UPDATE parametros_configuracion
SET valor = <nuevo_valor>
WHERE nombre_parametro = '<nombre_del_parametro>';
```

El cambio se refleja en la siguiente ejecución del motor (no requiere
reiniciar ni tocar código).

**Cómo restaurar los valores por defecto**: ejecutar
`db/restaurar_parametros.sql` en el SQL Editor de Supabase.

---

## Arquitectura

```
Dataset sintético (SQL seed) o CSV/Excel
        ↓
Supabase (Postgres + RLS + Auth)
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
Agente conversacional (FastAPI + Z.ai, solo lectura)
        ↓
Interfaz Vue 3 (cola + explicabilidad + proveedores + chat + KPIs + configuración)
```

Ver `docs/decisiones-diseno.md` para las decisiones de diseño y
`docs/pendientes.md` para deuda técnica.

---

## Scripts

**Verificación de entorno:**

- `scripts/verificar_rls.py` — confirma que `anon` solo puede leer.
- `scripts/verificar_service_role.py` — confirma que `service_role` puede
  escribir.
- `scripts/verificar_zai.py` — confirma la conexión con el LLM.
- `scripts/verificar_agente_rapido.py` — verifica el agente end-to-end.

**Demos del motor:**

- `scripts/demo_recomendador.py` — genera recomendaciones y las imprime.
- `scripts/demo_flujo_completo.py` — genera recomendaciones, las evalúa
  contra la rúbrica y las guarda opcionalmente en Supabase.

**API del agente:**

- `scripts/run_api.py` — levanta el servidor FastAPI del agente.

---

## Licencia

Proyecto académico. Uso educativo.