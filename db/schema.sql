-- ============================================================
-- Esquema de base de datos — Sistema Inteligente de Optimización de Compras
-- Basado en: PRD_Sistema_Optimizacion_Compras.md, sección 12
-- Versión: 2 (corregida antes de cargar datos)
--
-- Cambios respecto a v1:
--   1. recomendaciones.cantidad_recomendada (separada de cantidad_eoq)
--   2. recomendaciones.proveedor_id NOT NULL
--   3. recomendaciones.lead_time_dias y precio_unitario (snapshot trazable)
--   4. recomendaciones.estado (pendiente/revisada/descartada)
--   5. evaluaciones_criterios.creado_en
--   6. proveedor_id ON DELETE RESTRICT (no dejar huérfanas)
--   7. RLS habilitado + políticas de solo lectura para anon/authenticated
--   8. Índices adicionales de apoyo
-- ============================================================

-- Supabase ya trae disponible la función gen_random_uuid() (extensión pgcrypto).

-- ------------------------------------------------------------
-- productos
-- ------------------------------------------------------------
create table productos (
    id uuid primary key default gen_random_uuid(),
    nombre text not null,
    categoria text,
    costo_unitario numeric not null check (costo_unitario >= 0),
    stock_actual numeric not null default 0 check (stock_actual >= 0),
    costo_ordenar numeric not null check (costo_ordenar >= 0),
    costo_mantener_pct_anual numeric not null check (costo_mantener_pct_anual >= 0),
    creado_en timestamptz not null default now()
);

-- ------------------------------------------------------------
-- proveedores
-- ------------------------------------------------------------
create table proveedores (
    id uuid primary key default gen_random_uuid(),
    nombre text not null,
    cumplimiento_entrega_pct numeric not null check (cumplimiento_entrega_pct between 0 and 100),
    tasa_defectos_pct numeric not null check (tasa_defectos_pct between 0 and 100),
    creado_en timestamptz not null default now()
);

-- ------------------------------------------------------------
-- producto_proveedor (relación muchos a muchos)
-- ------------------------------------------------------------
create table producto_proveedor (
    producto_id uuid not null references productos (id) on delete cascade,
    proveedor_id uuid not null references proveedores (id) on delete cascade,
    precio_unitario numeric not null check (precio_unitario >= 0),
    lead_time_dias integer not null check (lead_time_dias >= 0),
    cantidad_umbral_descuento numeric check (cantidad_umbral_descuento >= 0),
    descuento_pct numeric check (descuento_pct between 0 and 100),
    primary key (producto_id, proveedor_id)
);

-- ------------------------------------------------------------
-- historial_demanda
-- ------------------------------------------------------------
create table historial_demanda (
    id uuid primary key default gen_random_uuid(),
    producto_id uuid not null references productos (id) on delete cascade,
    periodo date not null,
    cantidad_demandada numeric not null check (cantidad_demandada >= 0),
    unique (producto_id, periodo)
);

-- ------------------------------------------------------------
-- recomendaciones (salida del motor OR)
-- Cambios v2: proveedor NOT NULL, snapshot de lead_time y precio,
-- cantidad_recomendada separada del EOQ teórico, estado.
-- ------------------------------------------------------------
create table recomendaciones (
    id uuid primary key default gen_random_uuid(),
    producto_id uuid not null references productos (id) on delete cascade,
    proveedor_id uuid not null references proveedores (id) on delete restrict,
    fecha_generacion timestamptz not null default now(),

    -- parámetros calculados por el motor
    demanda_estimada numeric not null,
    cv_demanda numeric not null,
    punto_reorden numeric not null,
    stock_seguridad numeric not null,
    cantidad_eoq numeric not null,
    cantidad_recomendada numeric not null,  -- puede diferir del EOQ por descuento/urgencia

    -- clasificación
    clase_abc text not null check (clase_abc in ('A', 'B', 'C')),
    clase_xyz text not null check (clase_xyz in ('X', 'Y', 'Z')),

    -- snapshot trazable del proveedor elegido al momento de recomendar
    lead_time_dias integer not null,
    precio_unitario numeric not null,

    -- resultado económico
    ahorro_neto_estimado numeric not null default 0,

    -- ciclo de vida de la recomendación
    estado text not null default 'pendiente'
        check (estado in ('pendiente', 'revisada', 'descartada'))
);

-- ------------------------------------------------------------
-- evaluaciones_criterios (rúbrica aplicada a cada recomendación)
-- Cambio v2: creado_en para auditoría.
-- ------------------------------------------------------------
create table evaluaciones_criterios (
    id uuid primary key default gen_random_uuid(),
    recomendacion_id uuid not null references recomendaciones (id) on delete cascade,
    criterio text not null check (criterio in (
        'riesgo_quiebre_stock',
        'eficiencia_cantidad_eoq',
        'confianza_demanda',
        'importancia_producto',
        'confiabilidad_proveedor',
        'oportunidad_ahorro'
    )),
    estado text not null,
    valor_numerico numeric,
    creado_en timestamptz not null default now()
);

-- ------------------------------------------------------------
-- parametros_configuracion (umbrales ajustables de la rúbrica)
-- ------------------------------------------------------------
create table parametros_configuracion (
    nombre_parametro text primary key,
    valor numeric not null,
    descripcion text
);

insert into parametros_configuracion (nombre_parametro, valor, descripcion) values
    ('eoq_min_pct',               90,  'Límite inferior (%) de cantidad vs. EOQ para considerarse "óptima"'),
    ('eoq_max_pct',              110,  'Límite superior (%) de cantidad vs. EOQ para considerarse "óptima"'),
    ('cv_confianza_alta',        0.5,  'CV máximo para clasificar la demanda como "alta confianza" / clase X'),
    ('cv_confianza_media',       1.0,  'CV máximo para clasificar la demanda como "confianza moderada" / clase Y'),
    ('score_proveedor_confiable', 80,  'Score mínimo para considerar a un proveedor "confiable"'),
    ('score_proveedor_riesgoso',  60,  'Score por debajo del cual un proveedor se considera "riesgoso"'),
    ('ahorro_neto_min_pct',        3,  'Porcentaje mínimo de ahorro neto para considerarse una "oportunidad detectada"'),
    ('abc_clase_a_pct',           80,  'Porcentaje acumulado máximo para clasificar un producto como clase A'),
    ('abc_clase_b_pct',           95,  'Porcentaje acumulado máximo para clasificar un producto como clase B (por encima de este valor es clase C)'),
    ('demanda_ventana_default',    6,  'Número de periodos más recientes a promediar en la estimación de demanda (promedio móvil)');

-- ------------------------------------------------------------
-- Índices de apoyo para las consultas más frecuentes
-- ------------------------------------------------------------
create index idx_historial_demanda_producto    on historial_demanda (producto_id);
create index idx_historial_demanda_producto_periodo on historial_demanda (producto_id, periodo desc);
create index idx_producto_proveedor_producto   on producto_proveedor (producto_id);
create index idx_producto_proveedor_proveedor  on producto_proveedor (proveedor_id);
create index idx_recomendaciones_producto      on recomendaciones (producto_id);
create index idx_recomendaciones_estado        on recomendaciones (estado);
create index idx_recomendaciones_fecha         on recomendaciones (fecha_generacion desc);
create index idx_evaluaciones_recomendacion    on evaluaciones_criterios (recomendacion_id);

-- ============================================================
-- ROW LEVEL SECURITY
-- Objetivo: el frontend y el agente conversacional usan la anon key
-- y SOLO pueden leer. Toda escritura pasa por service_role (script de
-- ingesta y motor), que ignora RLS.
-- ============================================================

alter table productos               enable row level security;
alter table proveedores             enable row level security;
alter table producto_proveedor      enable row level security;
alter table historial_demanda       enable row level security;
alter table recomendaciones         enable row level security;
alter table evaluaciones_criterios  enable row level security;
alter table parametros_configuracion enable row level security;

-- Políticas de solo lectura para anon y authenticated.
-- No se crean políticas de insert/update/delete para estos roles:
-- eso garantiza que no puedan escribir aunque lo intenten.

create policy "lectura_anon_authenticated" on productos
    for select to anon, authenticated using (true);

create policy "lectura_anon_authenticated" on proveedores
    for select to anon, authenticated using (true);

create policy "lectura_anon_authenticated" on producto_proveedor
    for select to anon, authenticated using (true);

create policy "lectura_anon_authenticated" on historial_demanda
    for select to anon, authenticated using (true);

create policy "lectura_anon_authenticated" on recomendaciones
    for select to anon, authenticated using (true);

create policy "lectura_anon_authenticated" on evaluaciones_criterios
    for select to anon, authenticated using (true);

create policy "lectura_anon_authenticated" on parametros_configuracion
    for select to anon, authenticated using (true);