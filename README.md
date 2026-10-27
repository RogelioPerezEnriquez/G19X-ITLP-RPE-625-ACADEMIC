**Alumno:** Rogelio Pérez Enríquez
**Matrícula:** G19X-ITLP-RPE-625
**Institución:** Instituto Tecnológico de La Piedad

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
│   │   ├── evaluador.py         Rúbrica de 6 criterios
│   │   └── pipeline.py          Flujo completo de recálculo sin interacción (API)
│   ├── tests/                   Suite de tests (pytest, 12 archivos)
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

### Requisitos previos

Antes de comenzar, asegúrate de tener instalado:

- **Python 3.11 o superior**: descárgalo de
  [python.org](https://www.python.org/downloads/).
  *⚠️ En Windows, es **muy importante** marcar la casilla "Add python.exe
  to PATH" durante la instalación.*
- **Node.js 20.19+ o 22.12+**: descárgalo de
  [nodejs.org](https://nodejs.org/).
  *⚠️ Vite requiere esta versión mínima. Si usas una versión anterior
  (como Node 18 o 20.10), verás un error al correr `npm run dev`.*
- **Git**: descárgalo de [git-scm.com](https://git-scm.com/).

Para verificar que están instalados correctamente, abre una terminal y
ejecuta:

```bash
python --version
node --version
git --version
```

Si alguno de estos comandos da un error de "término no reconocido",
significa que no está instalado o no se agregó al PATH del sistema.

### 1. Clonar el repositorio

```bash
git clone https://github.com/RogelioPerezEnriquez/G19X-ITLP-RPE-625-ACADEMIC.git
cd G19X-ITLP-RPE-625-ACADEMIC
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

**Si eres el evaluador**, no necesitas crear ningún usuario: la cuenta de
administrador ya está creada en Supabase y las credenciales se entregan
por el canal indicado en la plataforma (ver la sección «Usuario de
prueba» más abajo). Puedes saltar al paso 5.

**Si instalas el proyecto desde cero**, como el registro público está
cerrado (RF-12), el primer usuario administrador se crea manualmente:

1. En el dashboard de Supabase, ve a **Authentication → Users**.
2. Pulsa **Add user** → **Create new user**.
3. Introduce el correo y la contraseña del administrador.
4. Copia el `User UID` del usuario recién creado.
5. En el **SQL Editor** de Supabase, ejecuta:
   ```sql
   INSERT INTO admins (user_id) VALUES ('<uuid-del-usuario>');
   ```

### 5. Instalar dependencias del backend

```bash
cd backend
python -m pip install -r requirements.txt
```

**Nota**: usar `python -m pip` garantiza que las dependencias se instalen
en el Python correcto si tienes varias versiones instaladas.

### 6. Instalar dependencias del frontend

```bash
cd ../frontend
npm install
cd ..
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

Esperado: 457 tests pasando.

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

### 10. Generar las recomendaciones iniciales

Al arrancar por primera vez, la cola de recomendaciones estará vacía.
Para generarla:

1. Inicia sesión con una cuenta de administrador.
2. Ve a la vista de **Configuración**.
3. Pulsa el botón **Recalcular recomendaciones**.

El sistema ejecutará el motor completo, guardará las recomendaciones y
las evaluaciones de los 6 criterios. Verás un mensaje de confirmación.

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

## Usuario de prueba

Para probar el sistema como administrador, utiliza las credenciales
asignadas al evaluador. Por seguridad, las credenciales (correo y
contraseña) **no se publican en el repositorio**; se entregan en
"Documentos del SGPA" (sección Técnicos → Accesos de prueba) o por el
canal indicado en la plataforma.

**Nota**: la cuenta entregada tiene rol de administrador para probar la
pantalla de configuración de parámetros (criterio 8).

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

## Lo que todavía no funciona

El MVP está funcionalmente completo (los 8 criterios de aceptación se
cumplen). Quedan pendientes algunas mejoras opcionales, documentadas en
`docs/pendientes.md`:

- **Configurabilidad total**: algunos parámetros (periodos por año,
  margen de seguridad, pesos del score) siguen hardcodeados.
- **Seed**: las clases ABC/XYZ calculadas no coinciden exactamente con
  las diseñadas (por estimaciones a ojo de la varianza).

Ver `docs/pendientes.md` para la lista completa.

---

## Si algo no funciona

Los problemas más comunes al instalar el proyecto desde cero y cómo
resolverlos:

**Error: `No module named 'dotenv'` o similar al correr el backend**

Significa que las dependencias no se instalaron en el Python correcto.
Ejecuta `python -m pip install -r requirements.txt` dentro de la carpeta
`backend/` para asegurarte de usar el mismo Python que ejecutará los
scripts.

**Error en Windows: `npm : No se puede cargar el archivo ... npm.ps1
porque la ejecución de scripts está deshabilitada`**

Es una restricción de seguridad de PowerShell. Tienes dos opciones:

1. Cambiar la terminal de VS Code a "Command Prompt" (CMD).
2. O ejecutar en PowerShell:
   `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
   (y confirmar con "S").

**Error: `Cannot find native binding` al correr `npm run dev`**

Es un bug conocido de `npm` con las dependencias opcionales de
`rolldown` (la herramienta de compilación de Vite). La solución es
forzar una reinstalación limpia:

1. Dentro de `frontend/`, borra la carpeta `node_modules` y el archivo
   `package-lock.json`.
2. Ejecuta `npm install` de nuevo.
3. Prueba `npm run dev`.

Si persiste, actualiza `npm` con `npm install -g npm@latest` y repite
los pasos.

**El frontend no conecta con la API**

Verifica que el archivo `.env` tenga la variable
`VITE_API_URL=http://localhost:8000` y que el servidor de FastAPI esté
corriendo en la terminal 1.

---

## Licencia

Proyecto académico. Uso educativo.