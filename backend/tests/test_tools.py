"""Tests unitarios de las tools de solo lectura del agente (RF-09, RF-10).

Se prueba cada una de las cinco tools de ``src.agente.tools`` contra un cliente
de Supabase falso **en memoria**: no se toca red, base de datos ni archivos. El
cliente solo implementa ``table(...).select(...).execute()``, que es el único
acceso a datos que usan las tools (todas son de solo lectura).

Los datos de prueba son pequeños y de reglas conocidas: tres productos (uno por
franja de urgencia), tres proveedores (con un empate de score para el desempate
por precio) y recomendaciones/evaluaciones de ejemplo.
"""

import pytest

from src.agente.tools import (
    CRITERIOS_VALIDOS,
    URGENCIA_ATENCION,
    URGENCIA_CRITICO,
    URGENCIA_SIN_RIESGO,
    buscar_recomendaciones,
    comparar_proveedores,
    detalle_recomendacion,
    explicar_criterio,
    resumen_prioridad_ABC_XYZ,
)

# ------------------------------------------------------------- cliente falso


class _RespuestaFalsa:
    """Respuesta mínima de PostgREST: solo el atributo ``data``."""

    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _TablaFalsa:
    """Constructor de consultas mínimo: ``select(...).execute()``."""

    def __init__(self, cliente: "_ClienteFalso", nombre: str) -> None:
        self._cliente = cliente
        self._nombre = nombre

    def select(self, columnas: str) -> "_TablaFalsa":
        """Registra la consulta (tabla + columnas) y devuelve el constructor."""
        self._cliente.consultas.append((self._nombre, columnas))
        return self

    def execute(self) -> _RespuestaFalsa:
        """Lanza el error configurado o devuelve las filas de la tabla."""
        if self._cliente.error is not None:
            raise self._cliente.error
        return _RespuestaFalsa(list(self._cliente.datos.get(self._nombre, [])))


class _ClienteFalso:
    """Cliente de Supabase mínimo, en memoria: sirve cada tabla por nombre.

    Registra en ``consultas`` cada ``select`` recibido, para poder afirmar qué
    tablas se leyeron (y que solo se leyeron).
    """

    def __init__(
        self,
        datos: dict[str, list[dict]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.datos = {} if datos is None else datos
        self.error = error
        self.consultas: list[tuple[str, str]] = []

    def table(self, nombre: str) -> _TablaFalsa:
        """Devuelve el constructor de consultas de la tabla pedida."""
        return _TablaFalsa(self, nombre)


# --------------------------------------------------------------- datos base


def _producto(id_: str, nombre: str, stock_actual: float) -> dict:
    """Fila de ``productos`` con las columnas de la base."""
    return {
        "id": id_,
        "nombre": nombre,
        "categoria": "Cat",
        "costo_unitario": 10.0,
        "stock_actual": stock_actual,
        "costo_ordenar": 50.0,
        "costo_mantener_pct_anual": 0.2,
    }


def _productos() -> list[dict]:
    """Tres productos, uno por franja de urgencia (SS=10 y ROP=100)."""
    return [
        _producto("p1", "Producto A", stock_actual=5.0),  # Crítico
        _producto("p2", "Producto B", stock_actual=50.0),  # Atención
        _producto("p3", "Producto C", stock_actual=500.0),  # Sin riesgo
    ]


def _proveedores() -> list[dict]:
    """Tres proveedores; pr1 y pr3 empatan en score (92) con precios distintos."""
    return [
        {
            "id": "pr1",
            "nombre": "Proveedor Uno",
            "cumplimiento_entrega_pct": 90.0,
            "tasa_defectos_pct": 5.0,  # score 92
        },
        {
            "id": "pr2",
            "nombre": "Proveedor Dos",
            "cumplimiento_entrega_pct": 80.0,
            "tasa_defectos_pct": 10.0,  # score 84
        },
        {
            "id": "pr3",
            "nombre": "Proveedor Tres",
            "cumplimiento_entrega_pct": 90.0,
            "tasa_defectos_pct": 5.0,  # score 92
        },
    ]


def _producto_proveedor() -> list[dict]:
    """p1 tiene 2 proveedores (pr1 score 92; pr2 score 84); p2 tiene 1 (pr2)."""
    return [
        {
            "producto_id": "p1",
            "proveedor_id": "pr1",
            "precio_unitario": 10.0,
            "lead_time_dias": 5,
            "cantidad_umbral_descuento": 100.0,
            "descuento_pct": 5.0,
        },
        {
            "producto_id": "p1",
            "proveedor_id": "pr2",
            "precio_unitario": 8.0,
            "lead_time_dias": 9,
            "cantidad_umbral_descuento": None,
            "descuento_pct": None,
        },
        {
            "producto_id": "p2",
            "proveedor_id": "pr2",
            "precio_unitario": 18.0,
            "lead_time_dias": 6,
            "cantidad_umbral_descuento": None,
            "descuento_pct": None,
        },
    ]


def _recomendacion(
    id_: str,
    producto_id: str,
    *,
    clase_abc: str,
    clase_xyz: str,
    ahorro: float,
    proveedor_id: str = "pr1",
    fecha: str = "2026-01-03T10:00:00+00:00",
    stock_seguridad: float = 10.0,
    punto_reorden: float = 100.0,
) -> dict:
    """Fila de ``recomendaciones`` con las columnas de la base."""
    return {
        "id": id_,
        "producto_id": producto_id,
        "proveedor_id": proveedor_id,
        "fecha_generacion": fecha,
        "demanda_estimada": 300.0,
        "cv_demanda": 0.3,
        "punto_reorden": punto_reorden,
        "stock_seguridad": stock_seguridad,
        "cantidad_eoq": 200.0,
        "cantidad_recomendada": 200.0,
        "clase_abc": clase_abc,
        "clase_xyz": clase_xyz,
        "lead_time_dias": 5,
        "precio_unitario": 10.0,
        "ahorro_neto_estimado": ahorro,
        "estado": "pendiente",
    }


def _recomendaciones() -> list[dict]:
    """Una recomendación por producto, con la urgencia repartida en las 3 franjas."""
    return [
        _recomendacion(
            "r1", "p1", clase_abc="A", clase_xyz="X", ahorro=300.0, proveedor_id="pr1"
        ),
        _recomendacion(
            "r2", "p2", clase_abc="B", clase_xyz="Y", ahorro=200.0, proveedor_id="pr2"
        ),
        _recomendacion(
            "r3", "p3", clase_abc="C", clase_xyz="Z", ahorro=100.0, proveedor_id="pr2"
        ),
    ]


def _recomendaciones_orden() -> list[dict]:
    """Tres recomendaciones Críticas (SS alto), para probar el orden del listado."""
    criticas = {"stock_seguridad": 1000.0, "punto_reorden": 2000.0}
    return [
        _recomendacion("r1", "p1", clase_abc="A", clase_xyz="X", ahorro=100.0, **criticas),
        _recomendacion("r2", "p2", clase_abc="A", clase_xyz="Y", ahorro=300.0, **criticas),
        _recomendacion("r3", "p3", clase_abc="B", clase_xyz="Z", ahorro=200.0, **criticas),
    ]


def _evaluaciones() -> list[dict]:
    """Evaluaciones de ejemplo: r1 tiene riesgo y confiabilidad; r2, solo riesgo."""
    return [
        {
            "id": "e1",
            "recomendacion_id": "r1",
            "criterio": "riesgo_quiebre_stock",
            "estado": URGENCIA_CRITICO,
            "valor_numerico": 5.0,
        },
        {
            "id": "e2",
            "recomendacion_id": "r1",
            "criterio": "confiabilidad_proveedor",
            "estado": "Confiable",
            "valor_numerico": 92.0,
        },
        {
            "id": "e3",
            "recomendacion_id": "r2",
            "criterio": "riesgo_quiebre_stock",
            "estado": URGENCIA_ATENCION,
            "valor_numerico": 50.0,
        },
    ]


def _datos(**overrides: list[dict]) -> dict[str, list[dict]]:
    """Las cinco tablas con los datos base, salvo las que se sobrescriban."""
    datos: dict[str, list[dict]] = {
        "productos": _productos(),
        "proveedores": _proveedores(),
        "producto_proveedor": _producto_proveedor(),
        "recomendaciones": _recomendaciones(),
        "evaluaciones_criterios": _evaluaciones(),
    }
    datos.update(overrides)
    return datos


def _cliente(**overrides: list[dict]) -> _ClienteFalso:
    """Cliente falso con las tablas base (o las sobrescritas)."""
    return _ClienteFalso(_datos(**overrides))


# ================================================ buscar_recomendaciones


def test_buscar_sin_filtro_devuelve_todas_ordenadas_por_urgencia():
    resultado = buscar_recomendaciones(_cliente())

    assert [r["producto_nombre"] for r in resultado] == [
        "Producto A",
        "Producto B",
        "Producto C",
    ]
    assert [r["urgencia"] for r in resultado] == [
        URGENCIA_CRITICO,
        URGENCIA_ATENCION,
        URGENCIA_SIN_RIESGO,
    ]
    assert set(resultado[0]) == {
        "producto_nombre",
        "urgencia",
        "clase_abc",
        "clase_xyz",
        "cantidad_recomendada",
        "ahorro_neto_estimado",
    }
    assert resultado[0]["clase_abc"] == "A"
    assert resultado[0]["clase_xyz"] == "X"
    assert resultado[0]["cantidad_recomendada"] == pytest.approx(200.0)
    assert resultado[0]["ahorro_neto_estimado"] == pytest.approx(300.0)


def test_buscar_filtra_por_urgencia():
    casos = {
        URGENCIA_CRITICO: ["Producto A"],
        URGENCIA_ATENCION: ["Producto B"],
        URGENCIA_SIN_RIESGO: ["Producto C"],
    }

    for urgencia, esperados in casos.items():
        resultado = buscar_recomendaciones(_cliente(), urgencia=urgencia)
        assert [r["producto_nombre"] for r in resultado] == esperados
        assert all(r["urgencia"] == urgencia for r in resultado)


def test_buscar_respeta_el_limite():
    resultado = buscar_recomendaciones(_cliente(), limite=2)

    assert [r["producto_nombre"] for r in resultado] == ["Producto A", "Producto B"]
    assert buscar_recomendaciones(_cliente(), limite=1)[0]["producto_nombre"] == (
        "Producto A"
    )
    assert buscar_recomendaciones(_cliente(), limite=99) == buscar_recomendaciones(
        _cliente()
    )


def test_buscar_con_la_base_vacia_devuelve_lista_vacia():
    assert buscar_recomendaciones(_cliente(recomendaciones=[])) == []
    # Sin productos no se puede calcular la urgencia: no hay filas que devolver.
    assert buscar_recomendaciones(_cliente(productos=[])) == []


def test_buscar_ordena_por_ahorro_descendente_dentro_de_la_urgencia():
    resultado = buscar_recomendaciones(_cliente(recomendaciones=_recomendaciones_orden()))

    assert [r["producto_nombre"] for r in resultado] == [
        "Producto B",
        "Producto C",
        "Producto A",
    ]
    assert [r["ahorro_neto_estimado"] for r in resultado] == [300.0, 200.0, 100.0]


def test_buscar_desempata_por_producto_id_ascendente():
    recomendaciones = _recomendaciones_orden()
    for fila in recomendaciones:
        fila["ahorro_neto_estimado"] = 100.0

    resultado = buscar_recomendaciones(_cliente(recomendaciones=recomendaciones))

    assert [r["producto_nombre"] for r in resultado] == [
        "Producto A",
        "Producto B",
        "Producto C",
    ]


def test_buscar_urgencia_invalida_lanza_value_error():
    for invalida in ["critico", "Crítico ", "CRÍTICO", "", 1, True]:
        with pytest.raises(ValueError):
            buscar_recomendaciones(_cliente(), urgencia=invalida)


def test_buscar_limite_invalido_lanza_value_error():
    for limite in [0, -1, 2.5, "5", True, None]:
        with pytest.raises(ValueError):
            buscar_recomendaciones(_cliente(), limite=limite)


# ================================================ detalle_recomendacion


def test_detalle_normal_incluye_campos_y_nombres():
    detalle = detalle_recomendacion(_cliente(), "Producto A")

    assert detalle is not None
    assert detalle["producto_nombre"] == "Producto A"
    assert detalle["proveedor_nombre"] == "Proveedor Uno"
    assert detalle["clase_abc"] == "A"
    assert detalle["clase_xyz"] == "X"
    assert detalle["cantidad_recomendada"] == pytest.approx(200.0)
    assert detalle["ahorro_neto_estimado"] == pytest.approx(300.0)
    # Todos los campos de la recomendación siguen presentes.
    for campo in (
        "id",
        "producto_id",
        "proveedor_id",
        "fecha_generacion",
        "demanda_estimada",
        "cv_demanda",
        "punto_reorden",
        "stock_seguridad",
        "cantidad_eoq",
        "lead_time_dias",
        "precio_unitario",
        "estado",
    ):
        assert campo in detalle


def test_detalle_producto_inexistente_devuelve_none():
    assert detalle_recomendacion(_cliente(), "No Existe") is None


def test_detalle_nombre_duplicado_lanza_value_error():
    productos = _productos()
    productos.append(dict(productos[0], id="p9"))

    with pytest.raises(ValueError):
        detalle_recomendacion(_cliente(productos=productos), "Producto A")


def test_detalle_producto_sin_recomendacion_devuelve_none():
    assert detalle_recomendacion(_cliente(recomendaciones=[]), "Producto A") is None


# ===================================================== explicar_criterio


def test_explicar_criterio_normal():
    resultado = explicar_criterio(_cliente(), "Producto A", "riesgo_quiebre_stock")

    assert resultado == {
        "producto_nombre": "Producto A",
        "criterio": "riesgo_quiebre_stock",
        "estado": URGENCIA_CRITICO,
        "valor_numerico": 5.0,
    }


def test_explicar_criterio_invalido_lanza_value_error():
    assert len(CRITERIOS_VALIDOS) == 6
    for invalido in ["riesgo", "", "RIESGO_QUIEBRE_STOCK", "oportunidad", 1]:
        with pytest.raises(ValueError):
            explicar_criterio(_cliente(), "Producto A", invalido)


def test_explicar_criterio_sin_evaluacion_devuelve_none():
    # Producto A no tiene evaluación de eficiencia_cantidad_eoq.
    assert (
        explicar_criterio(_cliente(), "Producto A", "eficiencia_cantidad_eoq") is None
    )


def test_explicar_criterio_producto_inexistente_devuelve_none():
    assert (
        explicar_criterio(_cliente(), "No Existe", "riesgo_quiebre_stock") is None
    )


# ================================================== comparar_proveedores


def test_comparar_dos_proveedores_ordenados_por_score():
    resultado = comparar_proveedores(_cliente(), "Producto A")

    assert [r["proveedor_nombre"] for r in resultado] == [
        "Proveedor Uno",
        "Proveedor Dos",
    ]
    assert resultado[0]["score_proveedor"] == pytest.approx(92.0)
    assert resultado[1]["score_proveedor"] == pytest.approx(84.0)
    assert set(resultado[0]) == {
        "proveedor_nombre",
        "precio_unitario",
        "lead_time_dias",
        "cumplimiento_entrega_pct",
        "tasa_defectos_pct",
        "score_proveedor",
    }
    assert resultado[0]["precio_unitario"] == pytest.approx(10.0)
    assert resultado[0]["cumplimiento_entrega_pct"] == pytest.approx(90.0)
    assert resultado[0]["tasa_defectos_pct"] == pytest.approx(5.0)
    assert resultado[0]["lead_time_dias"] == 5


def test_comparar_desempata_por_precio_ascendente():
    # pr1 y pr3 empatan en score (92); desempata el precio (pr3 más barato).
    relaciones = [
        {
            "producto_id": "p1",
            "proveedor_id": "pr1",
            "precio_unitario": 10.0,
            "lead_time_dias": 5,
        },
        {
            "producto_id": "p1",
            "proveedor_id": "pr3",
            "precio_unitario": 7.0,
            "lead_time_dias": 4,
        },
    ]

    resultado = comparar_proveedores(
        _cliente(producto_proveedor=relaciones), "Producto A"
    )

    assert [r["proveedor_nombre"] for r in resultado] == [
        "Proveedor Tres",
        "Proveedor Uno",
    ]
    assert resultado[0]["score_proveedor"] == pytest.approx(
        resultado[1]["score_proveedor"]
    )
    assert resultado[0]["precio_unitario"] == pytest.approx(7.0)


def test_comparar_producto_inexistente_devuelve_lista_vacia():
    assert comparar_proveedores(_cliente(), "No Existe") == []


def test_comparar_un_solo_proveedor():
    resultado = comparar_proveedores(_cliente(), "Producto B")

    assert len(resultado) == 1
    assert resultado[0]["proveedor_nombre"] == "Proveedor Dos"
    assert resultado[0]["score_proveedor"] == pytest.approx(84.0)


# ============================================ resumen_prioridad_ABC_XYZ


def test_resumen_normal_cuenta_por_clase_y_urgencia():
    resumen = resumen_prioridad_ABC_XYZ(_cliente())

    assert resumen["total_recomendaciones"] == 3
    assert resumen["por_clase_abc"] == {"A": 1, "B": 1, "C": 1}
    assert resumen["por_clase_xyz"] == {"X": 1, "Y": 1, "Z": 1}
    assert resumen["por_urgencia"] == {
        URGENCIA_CRITICO: 1,
        URGENCIA_ATENCION: 1,
        URGENCIA_SIN_RIESGO: 1,
    }
    assert len(resumen["por_combinacion"]) == 9
    assert resumen["por_combinacion"]["AX"] == 1
    assert resumen["por_combinacion"]["BY"] == 1
    assert resumen["por_combinacion"]["CZ"] == 1
    assert resumen["por_combinacion"]["AZ"] == 0
    assert resumen["suma_ahorro_neto"] == pytest.approx(600.0)


def test_resumen_con_la_base_vacia_todo_en_cero():
    resumen = resumen_prioridad_ABC_XYZ(_cliente(recomendaciones=[]))

    assert resumen["total_recomendaciones"] == 0
    assert resumen["por_clase_abc"] == {"A": 0, "B": 0, "C": 0}
    assert resumen["por_clase_xyz"] == {"X": 0, "Y": 0, "Z": 0}
    assert resumen["por_urgencia"] == {
        URGENCIA_CRITICO: 0,
        URGENCIA_ATENCION: 0,
        URGENCIA_SIN_RIESGO: 0,
    }
    assert len(resumen["por_combinacion"]) == 9
    assert all(valor == 0 for valor in resumen["por_combinacion"].values())
    assert resumen["suma_ahorro_neto"] == 0.0
    assert type(resumen["suma_ahorro_neto"]) is float


# ==================================== serialización, solo lectura y errores


def test_serializa_los_valores_a_tipos_nativos_y_solo_lee():
    cliente = _cliente()
    buscar_recomendaciones(cliente)
    detalle_recomendacion(cliente, "Producto A")
    explicar_criterio(cliente, "Producto A", "riesgo_quiebre_stock")
    comparar_proveedores(cliente, "Producto A")
    resumen_prioridad_ABC_XYZ(cliente)

    # Todas las consultas son SELECT (columnas "*"): nunca una escritura.
    assert cliente.consultas
    assert all(columnas == "*" for _, columnas in cliente.consultas)

    for fila in buscar_recomendaciones(_cliente()):
        assert type(fila["producto_nombre"]) is str
        assert type(fila["urgencia"]) is str
        assert type(fila["clase_abc"]) is str
        assert type(fila["cantidad_recomendada"]) is float
        assert type(fila["ahorro_neto_estimado"]) is float

    for fila in comparar_proveedores(_cliente(), "Producto A"):
        assert type(fila["lead_time_dias"]) is int
        assert type(fila["precio_unitario"]) is float
        assert type(fila["score_proveedor"]) is float


def test_propaga_la_excepcion_del_cliente():
    error = RuntimeError("401 Unauthorized")
    cliente = _ClienteFalso(_datos(), error=error)

    with pytest.raises(RuntimeError) as capturado:
        buscar_recomendaciones(cliente)

    assert capturado.value is error
