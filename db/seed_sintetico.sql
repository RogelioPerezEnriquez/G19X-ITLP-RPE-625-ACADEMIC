-- ============================================================
-- Seed sintético — Sistema Inteligente de Optimización de Compras
-- Propósito: tener datos mínimos para probar el motor OR y la
-- rúbrica de 6 criterios sin depender todavía del script de ingesta.
--
-- Cómo usar:
--   1. Pegar este archivo completo en el SQL Editor de Supabase.
--   2. Ejecutar.
--
-- Cómo borrar:
--   truncate table evaluaciones_criterios, recomendaciones,
--     historial_demanda, producto_proveedor, productos, proveedores
--     restart identity cascade;
--
-- Convenciones:
--   - Todos los nombres llevan el prefijo SEED_ para borrado selectivo.
--   - No se toca parametros_configuracion.
-- ============================================================

-- ------------------------------------------------------------
-- PROVEEDORES
-- Scores calculados con la fórmula del criterio 5:
--   score = cumplimiento_entrega_pct * 0.6 + (100 - tasa_defectos_pct) * 0.4
-- ------------------------------------------------------------
insert into proveedores (nombre, cumplimiento_entrega_pct, tasa_defectos_pct) values
    ('SEED_ProvCo',       95, 2),   -- score 96.2 → Confiable
    ('SEED_FastParts',    82, 8),   -- score 86.0 → Confiable
    ('SEED_CheapSupply',  70, 15),  -- score 76.0 → Aceptable con reservas
    ('SEED_RiesgoTotal',  50, 25);  -- score 50.0 → Riesgoso

-- ------------------------------------------------------------
-- PRODUCTOS
-- costo_mantener_pct_anual expresado en % (ej. 20 = 20% anual).
-- Stock calibrado para caer en distintos estados del criterio 1.
-- ------------------------------------------------------------
insert into productos (nombre, categoria, costo_unitario, stock_actual, costo_ordenar, costo_mantener_pct_anual) values
    ('SEED_Widget A',    'Componentes', 25.00,  30,  50, 20),  -- stock muy bajo → Crítico
    ('SEED_Widget B',    'Componentes', 18.00, 120,  45, 20),  -- stock intermedio → Atención
    ('SEED_Tornillo M3', 'Fijaciones',   0.80, 950,  20, 15),  -- stock alto → Sin riesgo
    ('SEED_Cable HDMI',  'Electrónica',  6.50, 400,  35, 25),  -- stock alto → Sin riesgo
    ('SEED_Engrane G7',  'Mecánica',    85.00,  15,  80, 22),  -- stock muy bajo → Crítico
    ('SEED_Pintura 1L',  'Químicos',    12.00, 260,  40, 18);  -- stock alto → Sin riesgo

-- ------------------------------------------------------------
-- PRODUCTO_PROVEEDOR
-- Nota: Widget A tiene 2 proveedores para probar comparar_proveedores().
-- Nota: Engrane G7 tiene descuento por volumen para probar criterio 6.
-- ------------------------------------------------------------
insert into producto_proveedor
    (producto_id, proveedor_id, precio_unitario, lead_time_dias, cantidad_umbral_descuento, descuento_pct)
select p.id, pr.id, v.precio, v.lead, v.umbral, v.descuento
from (values
    ('SEED_Widget A',    'SEED_ProvCo',      24.50,  7, null,  null),
    ('SEED_Widget A',    'SEED_CheapSupply', 22.00, 12,  500,   5),
    ('SEED_Widget B',    'SEED_FastParts',   17.50,  5,  300,   3),
    ('SEED_Tornillo M3', 'SEED_CheapSupply',  0.75, 10, 5000,   8),
    ('SEED_Cable HDMI',  'SEED_FastParts',    6.20,  6, null,  null),
    ('SEED_Engrane G7',  'SEED_ProvCo',      83.00,  9,  200,  10),
    ('SEED_Engrane G7',  'SEED_RiesgoTotal', 78.00, 15, null,  null),
    ('SEED_Pintura 1L',  'SEED_ProvCo',      11.80,  8, null,  null)
) as v(prod_nombre, prov_nombre, precio, lead, umbral, descuento)
join productos p on p.nombre = v.prod_nombre
join proveedores pr on pr.nombre = v.prov_nombre;

-- ------------------------------------------------------------
-- HISTORIAL_DEMANDA
-- 12 periodos (mensuales) por producto.
-- El patrón de cada serie fue diseñado para producir el CV objetivo:
--   Widget A:   CV ~0.20 (X) — demanda estable y alta
--   Widget B:   CV ~0.70 (Y) — demanda con variación moderada
--   Tornillo M3:CV ~0.25 (X) — demanda estable
--   Cable HDMI: CV ~1.40 (Z) — demanda errática
--   Engrane G7: CV ~1.30 (Z) — demanda errática
--   Pintura 1L: CV ~0.80 (Y) — demanda con variación moderada
-- ------------------------------------------------------------

-- SEED_Widget A — 12 periodos
insert into historial_demanda (producto_id, periodo, cantidad_demandada)
select p.id, d.periodo, d.cantidad
from productos p
cross join (values
    (date '2025-01-01', 100), (date '2025-02-01', 105),
    (date '2025-03-01',  98), (date '2025-04-01', 102),
    (date '2025-05-01', 110), (date '2025-06-01',  95),
    (date '2025-07-01', 108), (date '2025-08-01', 100),
    (date '2025-09-01', 103), (date '2025-10-01',  97),
    (date '2025-11-01', 105), (date '2025-12-01', 102)
) as d(periodo, cantidad)
where p.nombre = 'SEED_Widget A';

-- SEED_Widget B — 12 periodos
insert into historial_demanda (producto_id, periodo, cantidad_demandada)
select p.id, d.periodo, d.cantidad
from productos p
cross join (values
    (date '2025-01-01',  60), (date '2025-02-01', 120),
    (date '2025-03-01',  80), (date '2025-04-01', 150),
    (date '2025-05-01',  70), (date '2025-06-01', 130),
    (date '2025-07-01',  90), (date '2025-08-01', 110),
    (date '2025-09-01',  75), (date '2025-10-01', 140),
    (date '2025-11-01',  85), (date '2025-12-01', 125)
) as d(periodo, cantidad)
where p.nombre = 'SEED_Widget B';

-- SEED_Tornillo M3 — 12 periodos
insert into historial_demanda (producto_id, periodo, cantidad_demandada)
select p.id, d.periodo, d.cantidad
from productos p
cross join (values
    (date '2025-01-01', 2000), (date '2025-02-01', 2100),
    (date '2025-03-01', 1950), (date '2025-04-01', 2050),
    (date '2025-05-01', 2200), (date '2025-06-01', 1900),
    (date '2025-07-01', 2150), (date '2025-08-01', 2000),
    (date '2025-09-01', 2050), (date '2025-10-01', 1950),
    (date '2025-11-01', 2100), (date '2025-12-01', 2000)
) as d(periodo, cantidad)
where p.nombre = 'SEED_Tornillo M3';

-- SEED_Cable HDMI — 12 periodos (errático)
insert into historial_demanda (producto_id, periodo, cantidad_demandada)
select p.id, d.periodo, d.cantidad
from productos p
cross join (values
    (date '2025-01-01',  50), (date '2025-02-01', 300),
    (date '2025-03-01',  80), (date '2025-04-01', 450),
    (date '2025-05-01',  30), (date '2025-06-01', 500),
    (date '2025-07-01',  70), (date '2025-08-01', 400),
    (date '2025-09-01',  40), (date '2025-10-01', 350),
    (date '2025-11-01',  60), (date '2025-12-01', 420)
) as d(periodo, cantidad)
where p.nombre = 'SEED_Cable HDMI';

-- SEED_Engrane G7 — 12 periodos (errático)
insert into historial_demanda (producto_id, periodo, cantidad_demandada)
select p.id, d.periodo, d.cantidad
from productos p
cross join (values
    (date '2025-01-01',  10), (date '2025-02-01',  80),
    (date '2025-03-01',  15), (date '2025-04-01', 100),
    (date '2025-05-01',   8), (date '2025-06-01', 120),
    (date '2025-07-01',  20), (date '2025-08-01',  95),
    (date '2025-09-01',  12), (date '2025-10-01', 110),
    (date '2025-11-01',  18), (date '2025-12-01', 105)
) as d(periodo, cantidad)
where p.nombre = 'SEED_Engrane G7';

-- SEED_Pintura 1L — 12 periodos
insert into historial_demanda (producto_id, periodo, cantidad_demandada)
select p.id, d.periodo, d.cantidad
from productos p
cross join (values
    (date '2025-01-01', 180), (date '2025-02-01', 320),
    (date '2025-03-01', 200), (date '2025-04-01', 350),
    (date '2025-05-01', 190), (date '2025-06-01', 310),
    (date '2025-07-01', 210), (date '2025-08-01', 330),
    (date '2025-09-01', 195), (date '2025-10-01', 340),
    (date '2025-11-01', 205), (date '2025-12-01', 315)
) as d(periodo, cantidad)
where p.nombre = 'SEED_Pintura 1L';