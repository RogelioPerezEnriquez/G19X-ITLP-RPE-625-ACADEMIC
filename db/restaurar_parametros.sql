-- Restaura los 10 parámetros a sus valores por defecto.
-- Uso: ejecutar en el SQL Editor de Supabase cuando se quiera resetear.

UPDATE parametros_configuracion SET valor = 80 WHERE nombre_parametro = 'abc_clase_a_pct';
UPDATE parametros_configuracion SET valor = 95 WHERE nombre_parametro = 'abc_clase_b_pct';
UPDATE parametros_configuracion SET valor = 3 WHERE nombre_parametro = 'ahorro_neto_min_pct';
UPDATE parametros_configuracion SET valor = 0.5 WHERE nombre_parametro = 'cv_confianza_alta';
UPDATE parametros_configuracion SET valor = 1.0 WHERE nombre_parametro = 'cv_confianza_media';
UPDATE parametros_configuracion SET valor = 6 WHERE nombre_parametro = 'demanda_ventana_default';
UPDATE parametros_configuracion SET valor = 110 WHERE nombre_parametro = 'eoq_max_pct';
UPDATE parametros_configuracion SET valor = 90 WHERE nombre_parametro = 'eoq_min_pct';
UPDATE parametros_configuracion SET valor = 80 WHERE nombre_parametro = 'score_proveedor_confiable';
UPDATE parametros_configuracion SET valor = 60 WHERE nombre_parametro = 'score_proveedor_riesgoso';