# Sistema Inteligente de Optimización de Compras

MVP de un sistema de soporte a la decisión de compras que genera
recomendaciones cuantificadas y explicables sobre qué comprar, cuánto,
cuándo y a qué proveedor.

El proyecto cubre una sola capacidad de punta a punta: **reabastecimiento
de inventario con evaluación explicada por criterios**, más un agente
conversacional de consulta en lenguaje natural.

---

## Estado del proyecto

🚧 En desarrollo — fase de motor de optimización.

| Componente | Estado |
|---|---|
| Esquema de base de datos (Supabase) | ✅ |
| Datos sintéticos de prueba | ✅ |
| Verificación de RLS | ✅ |
| Conexión con LLM (Z.ai) | ✅ |
| Motor OR (ABC, XYZ, EOQ, ROP) | ⏳ |
| Rúbrica de 6 criterios | ⏳ |
| Agente conversacional | ⏳ |
| Frontend (Vue 3) | ⏳ |

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

---

## Estructura del repositorio

```
.
├── db/                    Esquema SQL y seed de datos
├── backend/               Motor OR, agente y script de ingesta (Python)
├── frontend/              Interfaz de usuario (Vue 3) [pendiente]
├── scripts/               Scripts de verificación de entorno
├── MVP.md                 Definición del producto mínimo viable
└── PRD_*.md               Documento de requisitos
```

---

## Stack

| Componente | Tecnología |
|---|---|
| Motor de optimización | Python (pandas, numpy) |
| Persistencia y auth | Supabase (Postgres) |
| Agente conversacional | Z.ai (GLM) con function calling |
| Frontend | Vue 3 (Vite, Vue Router, Pinia) |
| Visualización | Librería de gráficos embebida |

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

### 3. Crear las tablas en Supabase

En el SQL Editor de Supabase, ejecutar en orden:

1. `db/schema.sql` — crea las 7 tablas y habilita RLS.
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

---

## Arquitectura

```
Dataset sintético (SQL seed)
        ↓
Supabase (Postgres + RLS)
        ↓
Motor OR (ABC · XYZ · EOQ · ROP)
        ↓
Evaluación por criterios (rúbrica de 6)
        ↓
Agente conversacional (solo lectura)
        ↓
Interfaz (cola + explicabilidad + chat + KPIs)
```

Ver `MVP.md` para detalle de cada componente.

---

## Licencia

Proyecto académico. Uso educativo.