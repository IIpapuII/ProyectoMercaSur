# Compras/services/icg_pedidos.py
from decimal import Decimal, ROUND_HALF_UP
from math import floor, ceil
from datetime import datetime, timedelta

from django.utils import timezone

from Compras.models import SugeridoLote, SugeridoLinea
from appMercaSur.conect import conectar_sql_server
from Compras.comodin.utils_pedido import (
    _round2, 
    _fmt_dtotexto, 
    _now_naive,
    _date_zero_today,
    _hora_excel_naive,
    _fecha_base_excel,
    _next_numpedido,
    _elegir_cantidad,
    _precio_y_descuento,
    _impuestos_de_linea,
    _obtener_cargos_articulo,
    _get_campo_clasificacion_por_almacen,
    _actualizar_clasificacion_si_activo,
    _actualizar_clasificacion_Almacen,
    _obtener_descuentos_proveedor,
    _obtener_secuencia_cargo,
    _obtener_forma_pago_proveedor,
    )


# ----------------------------- Constantes por defecto -----------------------------

DEFAULT_NUMSERIE = "13CP"
DEFAULT_SUBSERIE_N = "B"
DEFAULT_TIPODOC = 2
DEFAULT_IDESTADO = -1
DEFAULT_CODMONEDA = 1
DEFAULT_FACTORMONEDA = Decimal("1.0")
DEFAULT_IVAINCLUIDO = "F"  # depende del proveedor
DEFAULT_PORTESPAG = "F"
DEFAULT_TODORECIBIDO = "F"
DEFAULT_NORECIBIDO = "T"
DEFAULT_FROMPEDVENTACENTRAL = "F"
DEFAULT_SERIEALBARAN = ""
DEFAULT_NUMEROALBARAN = -1
DEFAULT_NALBARAN = "B"
DEFAULT_TRANSPORTE = 0
DEFAULT_NBULTOS = 0
DEFAULT_REGIMFACT = "3"
DEFAULT_ENVIOPOR = ""
DEFAULT_CONTACTO = -1
DEFAULT_CODEMPLEADO = -1
DEFAULT_NUMIMPRESIONES = 0

# ----------------------------- Flujo principal de creación ------------------------

def crear_pedido_compra_desde_lote(
    lote_id: int,
    numserie: str = DEFAULT_NUMSERIE,
    subserie_n: str = DEFAULT_SUBSERIE_N,
    politica_cantidades: str = "prefer_interno",
    ajuste_multiplo: str = "up",
):
    """
    Crea pedidos en ICG agrupando líneas del lote por almacén.
    - Inserta CAB, LIN, DTOSLIN, TOT y DTOS (cargos consolidados).
    - Actualiza STOCKS.PEDIDO.
    - Inserta TESORERIA por cada pedido creado.
    """
    lote = SugeridoLote.objects.select_related("proveedor").get(pk=lote_id)
    if not lote.proveedor:
        raise ValueError("El lote no tiene proveedor asignado.")

    codprove = getattr(lote.proveedor, "cod_icg", None) or getattr(lote.proveedor, "codigo", None)
    if codprove in (None, "", 0):
        raise ValueError("El proveedor no tiene código ICG (campo 'cod_icg' o 'codigo').")

    lineas = list(
        lote.lineas.select_related("proveedor", "marca")
        .filter(sugerido_interno__gt=0)
        .all()
    )
    if not lineas:
        raise ValueError("El lote no tiene líneas con sugerido interno > 0.")

    print(f"DEBUG: Encontradas {len(lineas)} líneas con sugerido_interno > 0")
    for i, lin in enumerate(lineas[:3]):
        print(
            f"DEBUG línea {i+1}: "
            f"codigo={lin.codigo_articulo}, sugerido_interno={lin.sugerido_interno}, embalaje={lin.embalaje}"
        )

    # Agrupar por almacén
    grupos: dict[str, list[SugeridoLinea]] = {}
    for lin in lineas:
        grupos.setdefault(lin.cod_almacen, []).append(lin)
    print(f"DEBUG: Grupos por almacén: {list(grupos.keys())}")

    pedidos_creados = []
    lineas_ordenadas_ids: list[int] = []

    # ------------------- Conexión segura -------------------
    conexion = conectar_sql_server()
    if not conexion:
        raise RuntimeError(
            "No se pudo obtener una conexión a SQL Server (conectar_sql_server() devolvió None). "
            "Verifica credenciales/DSN/red."
        )
    try:
        cursor = conexion.cursor()
    except AttributeError:
        raise RuntimeError(
            "La conexión a SQL Server no es válida (no expone .cursor()). "
            "Revisa la implementación de conectar_sql_server()."
        )

    # Control de autocommit (pyodbc usa .autocommit)
    try:
        conexion.autocommit = False
    except Exception:
        pass  # si el driver no soporta, continuamos con manejo manual

    try:
        dt_now = _now_naive()
        date_zero = _date_zero_today()
        hora_excel = _hora_excel_naive()

        for cod_almacen, lista in grupos.items():
            print(f"DEBUG: Procesando almacén {cod_almacen} con {len(lista)} líneas")

            # Filtrar/ajustar cantidades
            lista_validas: list[SugeridoLinea] = []
            for lin in lista:
                cantidad = _elegir_cantidad(lin, politica_cantidades, ajuste_multiplo)
                if cantidad > 0:
                    lista_validas.append(lin)
            if not lista_validas:
                continue

            # Obtener REGIMFACT del proveedor
            try:
                cursor.execute(
                    """
                    SELECT REGIMFACT
                    FROM PROVEEDORES
                    WHERE CODPROVEEDOR = ?
                    """,
                    (int(codprove),),
                )
                row_prov = cursor.fetchone()
                regimfact = str(row_prov[0]) if (row_prov and row_prov[0]) else DEFAULT_REGIMFACT
            except Exception as e:
                print(f"Error al obtener REGIMFACT del proveedor {codprove}: {e}")
                regimfact = DEFAULT_REGIMFACT

            # CABECERA
            numpedido = _next_numpedido(cursor, numserie)
            supedido = f"-{numserie}-{numpedido}"

            tot_bruto = Decimal("0")
            tot_impuestos = Decimal("0")
            tot_neto = Decimal("0")

            cursor.execute(
                """
                INSERT INTO PEDCOMPRACAB (
                    NUMSERIE, NUMPEDIDO, N, CODPROVEEDOR, SERIEALBARAN, NUMEROALBARAN, NALBARAN,
                    FECHAPEDIDO, FECHAENTREGA, ENVIOPOR, TOTBRUTO, DTOPP, TOTDTOPP, DTOCOMERCIAL, TOTDTOCOMERCIAL,
                    TOTIMPUESTOS, TOTNETO, CODMONEDA, FACTORMONEDA, PORTESPAG, SUPEDIDO, IVAINCLUIDO, TODORECIBIDO,
                    TIPODOC, IDESTADO, FECHAMODIFICADO, HORA, TRANSPORTE, NBULTOS, TOTALCARGOSDTOS, NORECIBIDO,
                    CODEMPLEADO, CONTACTO, FROMPEDVENTACENTRAL, FECHACREACION, NUMIMPRESIONES, REGIMFACT
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    numserie, numpedido, subserie_n, int(codprove),
                    DEFAULT_SERIEALBARAN, DEFAULT_NUMEROALBARAN, DEFAULT_NALBARAN,
                    date_zero, date_zero, DEFAULT_ENVIOPOR,
                    0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0,
                    DEFAULT_CODMONEDA, float(DEFAULT_FACTORMONEDA),
                    DEFAULT_PORTESPAG, supedido, DEFAULT_IVAINCLUIDO, DEFAULT_TODORECIBIDO,
                    DEFAULT_TIPODOC, DEFAULT_IDESTADO, dt_now, hora_excel, DEFAULT_TRANSPORTE, DEFAULT_NBULTOS, 0.0, DEFAULT_NORECIBIDO,
                    DEFAULT_CODEMPLEADO, DEFAULT_CONTACTO, DEFAULT_FROMPEDVENTACENTRAL, dt_now, DEFAULT_NUMIMPRESIONES, regimfact
                ),
            )

            # TOTALES POR IMPUESTO
            totales_por_impuesto: dict[tuple[int, Decimal], dict] = {}
            numlinea = 0
            contador_dtoslin = 0
            numlin_global = 0
            # Acumulador de base por cargo: suma de TOTALLINEA de las líneas que llevan ese cargo
            bases_por_cargo = {f"CARGO{i}": Decimal("0") for i in range(1, 7)}
            # LINEAS
            for lin in lista_validas:
                q = _elegir_cantidad(lin, politica_cantidades, ajuste_multiplo)
                if q <= 0:
                    continue

                precio_base, dto_pct = _precio_y_descuento(lin)
                tipoimp, iva_pct = _impuestos_de_linea(cursor, lin)

                codart = int(lin.codigo_articulo) if str(lin.codigo_articulo).isdigit() else lin.codigo_articulo
                cargos_pct = _obtener_cargos_articulo(cursor, str(codart))

                total_linea_sin_iva = _round2(precio_base * (Decimal("1") - (dto_pct / Decimal("100"))) * q)
                iva_linea = _round2(total_linea_sin_iva * (iva_pct / Decimal("100"))) if iva_pct else Decimal("0")
                total_linea = total_linea_sin_iva + iva_linea

                # Acumular totales del pedido
                tot_bruto += total_linea_sin_iva
                tot_impuestos += iva_linea
                tot_neto += total_linea

                # Agrupar por (tipoimp, iva_pct)
                key_impuesto = (tipoimp, iva_pct)
                if key_impuesto not in totales_por_impuesto:
                    totales_por_impuesto[key_impuesto] = {
                        "baseimponible": Decimal("0"),
                        "totiva": Decimal("0"),
                        "total": Decimal("0"),
                        "tipoiva": tipoimp,
                        "cargos": {f"CARGO{i}": Decimal("0") for i in range(1, 7)},
                    }

                totales_por_impuesto[key_impuesto]["baseimponible"] += total_linea_sin_iva
                totales_por_impuesto[key_impuesto]["totiva"] += iva_linea
                totales_por_impuesto[key_impuesto]["total"] += total_linea

                # Sumar cargos por grupo de impuesto (consolidados) como UNID1 * cargo_unitario
                for cargo_name, cargo_unit in cargos_pct.items():
                    totales_por_impuesto[key_impuesto]["cargos"][cargo_name] += _round2(cargo_unit * q)
                # Acumular base del cargo: suma del TOTALLINEA de las líneas que tengan ese cargo
                for cargo_name, cargo_unit in cargos_pct.items():
                    if cargo_unit > 0:
                        bases_por_cargo[cargo_name] += total_linea
                # Insert de línea
                numlinea += 1
                cursor.execute(
                    """
                    INSERT INTO PEDCOMPRALIN (
                        NUMSERIE, NUMPEDIDO, N, NUMLINEA, CODARTICULO, REFERENCIA, TALLA, COLOR, DESCRIPCION,
                        UNID1, UNID2, UNID3, UNID4, UNIDADESTOTAL, UNIDADESREC, UNIDADESPEN,
                        PRECIO, DTO, TIPOIMPUESTO, IVA, REQ, TOTALLINEA, CODALMACEN, DEPOSITO, PRECIOVENTA,
                        NUMKG, SUPEDIDO, CODCLIENTE, CARGO1, CARGO2, DTOTEXTO, ESOFERTA, FECHAENTREGA,
                        CODENVIO, UDMEDIDA2, LINEAOCULTA, CODFORMATO, CARGO3, CARGO4, CARGO5, CARGO6,
                        IMPORTEMASCARGOS, IMPORTEIVAMASCARGOS
                    )
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        numserie, numpedido, subserie_n, numlinea,
                        codart, (lin.referencia or ""), ".", ".", (lin.descripcion or "")[:250],
                        float(q), 1.0, 1.0, 1.0, float(q), 0.0, float(q),
                        float(precio_base), float(dto_pct), int(tipoimp), float(iva_pct), 0.0, float(total_linea),
                        lin.cod_almacen, "F", 0.0,
                        0.0, f"-{numserie}-{numpedido}", -1,
                        float(cargos_pct.get("CARGO1", Decimal("0"))),
                        float(cargos_pct.get("CARGO2", Decimal("0"))),
                        _fmt_dtotexto(dto_pct), "F", date_zero,
                        -1, 0.0, "F", 0,
                        float(cargos_pct.get("CARGO3", Decimal("0"))),
                        float(cargos_pct.get("CARGO4", Decimal("0"))),
                        float(cargos_pct.get("CARGO5", Decimal("0"))),
                        float(cargos_pct.get("CARGO6", Decimal("0"))),
                        0.0, 0.0,
                    ),
                )

                # DTOS/IMPUESTOS por línea (PEDCOMPRADTOSLIN) - 6 cargos obligatorios
                cargo_code_map = {"CARGO1": 3, "CARGO2": 34, "CARGO3": 39, "CARGO4": 40, "CARGO5": 41, "CARGO6": 42}
                
                for cargo_name in ["CARGO1", "CARGO2", "CARGO3", "CARGO4", "CARGO5", "CARGO6"]:
                    contador_dtoslin += 1
                    numlin_global += 1
                    codigo_cargo = cargo_code_map[cargo_name]
                    
                    # Valor del cargo (solo si es visible)
                    cargo_unit = cargos_pct.get(cargo_name, Decimal("0"))
                    importe_cargo = _round2(cargo_unit * q) if cargo_unit > 0 else Decimal("0")
                    
                    # CARGO2 lleva el IVA de la línea principal
                    if cargo_name == "CARGO2":
                        tipo_imp_cargo = int(tipoimp)
                        iva_cargo_pct = iva_pct
                        # IVA se calcula sobre el importe del cargo si existe, sino es 0
                        iva_cargo_importe = _round2(importe_cargo * (iva_cargo_pct / Decimal("100"))) if importe_cargo > 0 else Decimal("0")
                    else:
                        # Los demás cargos tienen su propio IVA (si existe en CARGOSDTOS)
                        if importe_cargo > 0:
                            try:
                                cursor.execute(
                                    """
                                    SELECT I.IVA, I.TIPOIVA
                                    FROM CARGOSDTOS C
                                    LEFT JOIN IMPUESTOS I ON I.TIPOIVA = C.TIPOIMPUESTO
                                    WHERE C.CODIGO = ?
                                    """,
                                    (codigo_cargo,),
                                )
                                row_cargo_iva = cursor.fetchone()
                                if row_cargo_iva and row_cargo_iva[0]:
                                    iva_cargo_pct = Decimal(str(row_cargo_iva[0]))
                                    tipo_imp_cargo = int(row_cargo_iva[1] or 0)
                                    iva_cargo_importe = _round2(importe_cargo * (iva_cargo_pct / Decimal("100")))
                                else:
                                    iva_cargo_pct = Decimal("0")
                                    tipo_imp_cargo = 0
                                    iva_cargo_importe = Decimal("0")
                            except Exception:
                                iva_cargo_pct = Decimal("0")
                                tipo_imp_cargo = 0
                                iva_cargo_importe = Decimal("0")
                        else:
                            iva_cargo_pct = Decimal("0")
                            tipo_imp_cargo = 0
                            iva_cargo_importe = Decimal("0")
                    
                    # INSERT siempre, incluso si el importe es 0
                    cursor.execute(
                        """
                        INSERT INTO PEDCOMPRADTOSLIN (
                            NUMSERIE, NUMERO, N, NUMLINDOC, IMPORTE, IMPORTEIVA, NUMLIN, CODIMPUESTO, PORC1, PORC2
                        )
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            numserie, numpedido, subserie_n, numlinea,
                            float(importe_cargo), float(iva_cargo_importe),
                            numlin_global, tipo_imp_cargo, float(iva_cargo_pct), 0.0,
                        ),
                    )

                _actualizar_clasificacion_si_activo(cursor, lin)
                _actualizar_clasificacion_Almacen(cursor, lin)
                lineas_ordenadas_ids.append(lin.id)

            # TOTALES (PEDCOMPRATOT)
            numlinea_tot = 0
            for (tipoimp, iva_pct), totales in totales_por_impuesto.items():
                # 1) Base + IVA
                numlinea_tot += 1
                cursor.execute(
                    """
                    INSERT INTO PEDCOMPRATOT (
                        SERIE, NUMERO, N, NUMLINEA, BRUTO, DTOCOMERC, TOTDTOCOMERC, DTOPP, TOTDTOPP,
                        BASEIMPONIBLE, IVA, TOTIVA, REQ, TOTREQ, TOTAL, ESGASTO, CODDTO, DESCRIPCION, TIPOIVA
                    )
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        numserie, numpedido, subserie_n, numlinea_tot,
                        float(_round2(totales["baseimponible"])), 0.0, 0.0, 0.0, 0.0,
                        float(_round2(totales["baseimponible"])), float(iva_pct), float(_round2(totales["totiva"])),
                        0.0, 0.0, float(_round2(totales["baseimponible"] + totales["totiva"])),
                        "F", -1, "", int(tipoimp),
                    ),
                )

                # 2) Cargos individuales por código específico
                cargo_code_map = {"CARGO1": 3, "CARGO2": 34, "CARGO3": 39, "CARGO4": 40, "CARGO5": 41, "CARGO6": 42}
                for cargo_name, cargo_total in totales["cargos"].items():
                    if cargo_total > 0:
                        numlinea_tot += 1
                        codigo_cargo = cargo_code_map.get(cargo_name, 3)
                        cursor.execute(
                            """
                            INSERT INTO PEDCOMPRATOT (
                                SERIE, NUMERO, N, NUMLINEA, BRUTO, DTOCOMERC, TOTDTOCOMERC, DTOPP, TOTDTOPP,
                                BASEIMPONIBLE, IVA, TOTIVA, REQ, TOTREQ, TOTAL, ESGASTO, CODDTO, DESCRIPCION, TIPOIVA
                            )
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                numserie, numpedido, subserie_n, numlinea_tot,
                                float(_round2(cargo_total)), 0.0, 0.0, 0.0, 0.0,
                                float(_round2(cargo_total)), 0.0, 0.0,
                                0.0, 0.0, float(_round2(cargo_total)),
                                "F", codigo_cargo, "", 0,
                            ),
                        )

            # Añadir descuentos de proveedor a PEDCOMPRATOT (como cargos negativos)
            # Base para el porcentaje: suma de base imponible de todos los grupos de impuesto
            base_tot_tots = sum(t["baseimponible"] for t in totales_por_impuesto.values())
            descuentos_proveedor = _obtener_descuentos_proveedor(cursor, int(codprove))
            for codigo_desc, valor_pct in descuentos_proveedor:
                if base_tot_tots > 0 and valor_pct > 0:
                    importe_desc = _round2(base_tot_tots * (valor_pct / Decimal("100")))
                    if importe_desc > 0:
                        numlinea_tot += 1
                        cursor.execute(
                            """
                            INSERT INTO PEDCOMPRATOT (
                                SERIE, NUMERO, N, NUMLINEA, BRUTO, DTOCOMERC, TOTDTOCOMERC, DTOPP, TOTDTOPP,
                                BASEIMPONIBLE, IVA, TOTIVA, REQ, TOTREQ, TOTAL, ESGASTO, CODDTO, DESCRIPCION, TIPOIVA
                            )
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                numserie, numpedido, subserie_n, numlinea_tot,
                                float(_round2(-importe_desc)), 0.0, 0.0, 0.0, 0.0,
                                float(_round2(-importe_desc)), 0.0, 0.0,
                                0.0, 0.0, float(_round2(-importe_desc)),
                                "F", int(codigo_desc), "", 0,
                            ),
                        )

            # DTOS/CARGOS Consolidados (PEDCOMPRADTOS)
            total_base_imponible = sum(t["baseimponible"] for t in totales_por_impuesto.values())
            cargos_consolidados = {f"CARGO{i}": Decimal("0") for i in range(1, 7)}
            for totales in totales_por_impuesto.values():
                for cargo_name, cargo_total in totales["cargos"].items():
                    cargos_consolidados[cargo_name] += cargo_total

            cargo_code_map = {"CARGO1": 3, "CARGO2": 34, "CARGO3": 39, "CARGO4": 40, "CARGO5": 41, "CARGO6": 42}

            cursor.execute(
                """
                SELECT LINEA FROM PEDCOMPRADTOS
                WHERE NUMSERIE = ? AND NUMERO = ? AND N = ?
                """,
                (numserie, numpedido, subserie_n),
            )
            lineas_existentes = {row[0] for row in cursor.fetchall()}

            linea_consolidado = 0
            for cargo_name, cargo_total in cargos_consolidados.items():
                if cargo_total > 0:
                    linea_consolidado += 1
                    if linea_consolidado not in lineas_existentes:
                        codigo_cargo = cargo_code_map.get(cargo_name, 3)
                        secuencia = _obtener_secuencia_cargo(cursor, codigo_cargo)
                        # BASE debe ser la suma de TOTALLINEA de las líneas que tienen ese cargo
                        base_para_cargo = _round2(bases_por_cargo.get(cargo_name, Decimal("0")))
                        cursor.execute(
                            """
                            INSERT INTO PEDCOMPRADTOS (
                                NUMSERIE, NUMERO, N, LINEA, NUMLINDOC, CODDTO, TIPO, SECUENCIA,
                                BASE, DTOCARGO, IMPORTE, UDSDTO, IMPORTEUNITARIODESC,
                                TIPOIMPUESTO, IVA, REQ, TIPODTO
                            )
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                numserie, numpedido, subserie_n, linea_consolidado, None, codigo_cargo, "C", secuencia,
                                float(base_para_cargo), 0.0, float(_round2(cargo_total)),
                                0.0, 0.0, 0, 0.0, 0.0, 0,
                            ),
                        )

            # Descuentos de proveedor en PEDCOMPRADTOS (se mantienen basados en la base total imponible)
            for codigo_desc, valor_pct in descuentos_proveedor:
                if total_base_imponible > 0 and valor_pct > 0:
                    importe_desc = _round2(total_base_imponible * (valor_pct / Decimal("100")))
                    if importe_desc > 0:
                        linea_consolidado += 1
                        secuencia_desc = _obtener_secuencia_cargo(cursor, int(codigo_desc))
                        cursor.execute(
                            """
                            INSERT INTO PEDCOMPRADTOS (
                                NUMSERIE, NUMERO, N, LINEA, NUMLINDOC, CODDTO, TIPO, SECUENCIA,
                                BASE, DTOCARGO, IMPORTE, UDSDTO, IMPORTEUNITARIODESC,
                                TIPOIMPUESTO, IVA, REQ, TIPODTO
                            )
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                numserie, numpedido, subserie_n, linea_consolidado, None, int(codigo_desc), "D", secuencia_desc,
                                float(_round2(total_base_imponible)), float(valor_pct), float(_round2(-importe_desc)),
                                0.0, 0.0, 0, 0.0, 0.0, 1,
                            ),
                        )

            # STOCKS: incrementar PEDIDO
            for lin in lista_validas:
                q = _elegir_cantidad(lin, politica_cantidades, ajuste_multiplo)
                if q <= 0:
                    continue
                codart = int(lin.codigo_articulo) if str(lin.codigo_articulo).isdigit() else lin.codigo_articulo
                cursor.execute(
                    """
                    UPDATE STOCKS
                    SET PEDIDO = PEDIDO + ?, FECHAMODIFICADO = ?
                    WHERE CODARTICULO = ? AND TALLA = ? AND COLOR = ? AND CODALMACEN = ?
                    """,
                    (float(q), dt_now, codart, ".", ".", lin.cod_almacen),
                )

            # Actualizar totales de CAB
            total_cargos_pedido = Decimal("0")
            for totales in totales_por_impuesto.values():
                total_cargos_pedido += sum(totales["cargos"].values())

            # Incluir descuentos de proveedor (negativos) en TOTALCARGOSDTOS
            total_descuentos_proveedor = Decimal("0")
            if total_base_imponible > 0 and descuentos_proveedor:
                for _, valor_pct in descuentos_proveedor:
                    if valor_pct > 0:
                        total_descuentos_proveedor += _round2(total_base_imponible * (valor_pct / Decimal("100")))
            total_cargos_pedido = total_cargos_pedido - total_descuentos_proveedor  # restar descuentos

            # Ajustar tot_neto para incluir cargos y descuentos
            tot_neto_final = tot_neto + total_cargos_pedido

            cursor.execute(
                """
                UPDATE PEDCOMPRACAB
                SET TOTBRUTO = ?, TOTIMPUESTOS = ?, TOTNETO = ?, TOTALCARGOSDTOS = ?
                WHERE NUMSERIE = ? AND NUMPEDIDO = ? AND N = ?
                """,
                (
                    float(_round2(tot_bruto)),
                    float(_round2(tot_impuestos)),
                    float(_round2(tot_neto_final)),
                    float(_round2(total_cargos_pedido)),
                    numserie, numpedido, subserie_n
                ),
            )

            # ---------------- TESORERIA por pedido ----------------
            # Obtener forma de pago (por proveedor) con DIAS, CODFORMAPAGO y CODTIPOPAGO
            datos_fpago = _obtener_forma_pago_proveedor(cursor, int(codprove))
            codformapago = datos_fpago["codformapago"]
            dias_vencimiento = datos_fpago["dias_vencimiento"]
            codtipopago = datos_fpago["codtipopago"]

            # Calcular FECHAVENCIMIENTO sumando días a FECHADOCUMENTO
            fecha_vencimiento = date_zero + timedelta(days=dias_vencimiento)
            
            # FECHACARTERA siempre es la fecha base de Excel
            fecha_cartera = _fecha_base_excel()

            importe_tes = _round2(tot_neto_final)
            values_tesoreria = (
                # 1-8
                "P", "P", numserie, numpedido, subserie_n, 1, date_zero, fecha_vencimiento,
                # 9-16
                "F", "22050501", int(codprove), float(importe_tes), "22050501", "F", codformapago, codtipopago,
                # 17-24
                "P", "", -1, "F", "F", None, fecha_cartera, None,
                # 25-32
                fecha_vencimiento, None, 0.0, None, 0, 3, "", 0,
                # 33-40
                0, "F", "VENCIMIENTO", 1.0, 1, "", "F", "",
                # 41-48
                "", 0.0, 0, dt_now, "", 0.0, "F", 0,
                # 49-56
                "", 0, "", -1, 0.0, -1, 0.0, 0.0,
                # 57-64
                0.0, 0.0, "", "", 1.0, "", "",
                # 65-69
                "", "", 0, 0, "", ""
            )

            assert len(values_tesoreria) == 69, f"TESORERIA espera 69 valores (sin VERSION), llegaron {len(values_tesoreria)}"
            placeholders = ", ".join(["?"] * len(values_tesoreria))
            cursor.execute(
                f"""
                INSERT INTO TESORERIA (
                    ORIGEN, TIPODOCUMENTO, SERIE, NUMERO, N, POSICION, FECHADOCUMENTO, FECHAVENCIMIENTO,
                    REPOSICION, CUENTA, CODIGOINTERNO, IMPORTE, CONTRAPARTIDA, MARCABORRADO, CODFORMAPAGO,
                    CODTIPOPAGO, ESTADO, COMENTARIO, NUMEROREMESA, IMPRESO, TRASPASADO, FECHATRASPASO,
                    FECHACARTERA, FECHADESCONTADO, FECHASALDADO, FECHADEVUELTO, IMPORTEGASTOS, CUENTAGASTOS,
                    ENLACE_EJERCICIO, ENLACE_EMPRESA, ENLACE_USUARIO, ENLACE_ASIENTO, ENLACE_APUNTE,
                    FECHADIRECTA, GENAPUNTE, FACTORMONEDA, CODMONEDA, SUDOCUMENTO, MULTIPLE, NUMEFECTO,
                    CUENTAPUENTE, MORA, ZSALDADO, FECHAMODIFICADO, CAJASALDADO, DESCUADRE, BLOQUEADO,
                    COMPENSACION, COMENTARIOVISIBLE, RETENCION, SERIERECIBO, NUMRECIBO, BASE,
                    CODIMPUESTO, PORCIVA, CUOTAIVA, PORCREQ, CUOTAREQ, CUENTAIVA, CUENTAREQ,
                    FACTORMONEDAREAL, NUMTXNTEF, NUMRTSTEF, BINTARJETA, CAJACARTERA, ZCARTERA,
                    ECPARTIDA, COMENTARIOLARGO, ASIENTOCARTERA
                )
                VALUES ({placeholders})
                """,
                values_tesoreria,
            )

            pedidos_creados.append(
                {
                    "cod_almacen": str(cod_almacen),
                    "numserie": numserie,
                    "numpedido": int(numpedido),
                    "subserie": subserie_n,
                    "supedido": supedido,
                    "totbruto": float(_round2(tot_bruto)),
                    "totimpuestos": float(_round2(tot_impuestos)),
                    "totneto": float(_round2(tot_neto)),
                }
            )

        if not pedidos_creados:
            # Debug ampliado si nada se generó
            debug_info = []
            for cod_almacen, lista in grupos.items():
                for lin in lista:
                    cantidad = _elegir_cantidad(lin, politica_cantidades, ajuste_multiplo)
                    debug_info.append(
                        f"Almacén {cod_almacen}, Artículo {lin.codigo_articulo}: "
                        f"sugerido_interno={lin.sugerido_interno}, embalaje={lin.embalaje}, cantidad_elegida={cantidad}"
                    )
            raise ValueError("No se generaron pedidos (sin líneas válidas).\n" + "\n".join(debug_info))

        # Commit final (todos los pedidos)
        try:
            conexion.commit()
        except Exception:
            try:
                conexion.rollback()
            except Exception:
                pass
            raise

    except Exception:
        try:
            conexion.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conexion.close()
        except Exception:
            pass

    # Marcar líneas como ordenadas y cerrar lote en Django
    if lineas_ordenadas_ids:
        SugeridoLinea.objects.filter(id__in=lineas_ordenadas_ids).update(
            estado_linea=SugeridoLinea.EstadoLinea.ORDENADA
        )

    SugeridoLote.objects.filter(pk=lote_id).update(
        estado=SugeridoLote.Estado.COMPLETADO,
        pedidos_icg=pedidos_creados,
    )

    return pedidos_creados
