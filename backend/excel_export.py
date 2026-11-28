"""Generación de informes XLSX de MediCuida usando solo la biblioteca estándar.

Los datos se leen de SQLite (fuente operativa actual). No se modifican tablas,
no se exportan credenciales ni DNI completos y el archivo representa una
instantánea tomada al pulsar el botón del Dashboard.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def _s(value):
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32)
    return text[:32767]


def _role(value):
    return {"paciente": "Paciente", "cuidador": "Cuidador",
            "ambos": "Paciente y Cuidador", "medico": "Médico"}.get(value, _s(value))


def _view(value):
    return {
        "inicio": "Inicio", "consulta": "Disponibilidad", "dashboard": "Dashboard",
        "inventario": "Administrar stock", "tratamientos": "Mis medicamentos",
        "historial": "Historial", "ayuda": "Ayuda", "blog": "Blog",
        "perfil": "Accesibilidad", "acceso": "Inicio de sesión",
    }.get(value, _s(value))


def collect_report_data(db):
    """Lee los datos actuales de MediCuida sin escribir ni alterar registros."""
    users = [dict(r) for r in db.execute("""
        SELECT u.id, u.nombres, u.apellidos, u.rol,
               CASE WHEN p.id IS NULL THEN ''
                    ELSE TRIM(COALESCE(p.nombres,'') || ' ' || COALESCE(p.apellidos,''))
               END AS paciente_vinculado,
               u.puesto
        FROM usuarios u
        LEFT JOIN usuarios p ON p.dni=u.dni_paciente
        ORDER BY u.id
    """).fetchall()]

    medicines = []
    for row in db.execute("""
        SELECT codigo,nombre,categoria,establecimiento,stock
        FROM medicamentos ORDER BY nombre,establecimiento
    """).fetchall():
        item = dict(row)
        stock = int(item.get("stock") or 0)
        item["estado"] = "Sin stock" if stock == 0 else ("Crítico" if stock <= 10 else "Disponible")
        medicines.append(item)

    visits = [dict(r) for r in db.execute("""
        SELECT vista,COUNT(*) AS visitas,COUNT(DISTINCT dni) AS usuarios
        FROM visitas_pestanas WHERE vista <> 'acceso'
        GROUP BY vista ORDER BY visitas DESC,vista
    """).fetchall()]

    monthly_visits = [dict(r) for r in db.execute("""
        SELECT substr(visitado_en,1,7) AS periodo,COUNT(*) AS visitas
        FROM visitas_pestanas WHERE vista <> 'acceso'
        GROUP BY substr(visitado_en,1,7) ORDER BY periodo
    """).fetchall()]

    role_rows = {r["rol"]: int(r["cantidad"]) for r in db.execute(
        "SELECT rol,COUNT(*) AS cantidad FROM usuarios GROUP BY rol"
    ).fetchall()}
    total_users = int(db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0])
    total_accesses = int(db.execute(
        "SELECT COUNT(*) FROM visitas_pestanas WHERE vista='acceso'"
    ).fetchone()[0])
    users_logged = int(db.execute(
        "SELECT COUNT(DISTINCT dni) FROM visitas_pestanas WHERE vista='acceso'"
    ).fetchone()[0])
    total_page_visits = int(db.execute(
        "SELECT COUNT(*) FROM visitas_pestanas WHERE vista <> 'acceso'"
    ).fetchone()[0])
    total_treatments = int(db.execute("SELECT COUNT(*) FROM tratamientos").fetchone()[0])
    total_takes = int(db.execute("SELECT COUNT(*) FROM tomas").fetchone()[0])
    confirmed_takes = int(db.execute(
        "SELECT COUNT(*) FROM tomas WHERE confirmada IS NOT NULL"
    ).fetchone()[0])

    treatments = [dict(r) for r in db.execute("""
        SELECT t.id,
               COALESCE(NULLIF(TRIM(COALESCE(p.nombres,'') || ' ' || COALESCE(p.apellidos,'')),''),'Usuario de demostración') AS paciente,
               COALESCE(NULLIF(TRIM(COALESCE(a.nombres,'') || ' ' || COALESCE(a.apellidos,'')),''),'Usuario de demostración') AS registrado_por,
               COALESCE(t.medico_nombre,'') AS medico,
               t.nombre,t.forma,t.dosis,t.inicio,t.fin,t.frecuencia,t.hora,
               t.motivo,t.indicaciones,
               COUNT(tm.id) AS programadas,
               SUM(CASE WHEN tm.confirmada IS NOT NULL THEN 1 ELSE 0 END) AS confirmadas,
               GROUP_CONCAT(tm.fecha, ' | ') AS fechas_programadas,
               GROUP_CONCAT(CASE WHEN tm.confirmada IS NOT NULL THEN tm.fecha || ' -> ' || tm.confirmada ELSE NULL END, ' | ') AS detalle_confirmaciones
        FROM tratamientos t
        LEFT JOIN usuarios p ON p.dni=t.titular_dni
        LEFT JOIN usuarios a ON a.dni=t.autor_dni
        LEFT JOIN tomas tm ON tm.tratamiento_id=t.id
        GROUP BY t.id
        ORDER BY t.id DESC
    """).fetchall()]
    for treatment in treatments:
        treatment["programadas"] = int(treatment.get("programadas") or 0)
        treatment["confirmadas"] = int(treatment.get("confirmadas") or 0)
        treatment["pendientes"] = max(0, treatment["programadas"] - treatment["confirmadas"])
        treatment["seguimiento"] = "Completado" if treatment["pendientes"] == 0 else "Pendiente"

    doctor_activity = [dict(r) for r in db.execute("""
        SELECT u.dni,
            COALESCE(
                (SELECT MAX(t.medico_nombre) FROM tratamientos t
                 WHERE t.autor_dni=u.dni AND t.medico_nombre <> ''
                   AND (t.medico_dni=u.dni OR (t.medico_dni='' AND u.rol='medico'))),
                TRIM(COALESCE(u.nombres,'') || ' ' || COALESCE(u.apellidos,'')),
                'Médico'
            ) AS nombre,
            (SELECT COUNT(*) FROM tratamientos t
             WHERE t.autor_dni=u.dni AND t.medico_nombre <> ''
               AND (t.medico_dni=u.dni OR (t.medico_dni='' AND u.rol='medico'))) AS registros,
            (SELECT COUNT(*) FROM tratamientos t
             WHERE t.autor_dni=u.dni AND t.medico_nombre <> ''
               AND (t.medico_dni=u.dni OR (t.medico_dni='' AND u.rol='medico'))
               AND t.titular_dni <> t.autor_dni) AS asignados,
            (SELECT COUNT(DISTINCT t.titular_dni) FROM tratamientos t
             WHERE t.autor_dni=u.dni AND t.medico_nombre <> ''
               AND (t.medico_dni=u.dni OR (t.medico_dni='' AND u.rol='medico'))
               AND t.titular_dni <> t.autor_dni) AS pacientes,
            (SELECT COUNT(*) FROM avisos a WHERE a.medico_dni=u.dni) AS modificaciones
        FROM usuarios u
        WHERE u.rol='medico'
           OR EXISTS (SELECT 1 FROM tratamientos t WHERE t.autor_dni=u.dni AND t.medico_nombre <> ''
                      AND (t.medico_dni=u.dni OR (t.medico_dni='' AND u.rol='medico')))
           OR EXISTS (SELECT 1 FROM avisos a WHERE a.medico_dni=u.dni)
        ORDER BY registros DESC,nombre
    """).fetchall()]

    assignments = [dict(r) for r in db.execute("""
        SELECT
            COALESCE(NULLIF(MAX(t.medico_nombre),''),'Médico') AS medico,
            COALESCE(NULLIF(TRIM(COALESCE(p.nombres,'') || ' ' || COALESCE(p.apellidos,'')),''),'Paciente de demostración') AS paciente,
            COUNT(*) AS registros,
            COUNT(DISTINCT t.nombre) AS medicamentos
        FROM tratamientos t
        LEFT JOIN usuarios p ON p.dni=t.titular_dni
        WHERE t.medico_nombre <> '' AND t.titular_dni <> t.autor_dni
        GROUP BY t.autor_dni,t.titular_dni
        ORDER BY registros DESC,medico,paciente
    """).fetchall()]

    available = sum(1 for x in medicines if x["estado"] == "Disponible")
    critical = sum(1 for x in medicines if x["estado"] == "Crítico")
    out_of_stock = sum(1 for x in medicines if x["estado"] == "Sin stock")
    assignment_total = sum(int(x.get("asignados") or 0) for x in doctor_activity)

    return {
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "users": users, "medicines": medicines, "visits": visits,
        "monthly_visits": monthly_visits, "treatments": treatments,
        "doctor_activity": doctor_activity, "assignments": assignments,
        "role_rows": role_rows,
        "kpis": {
            "total_users": total_users,
            "patients": role_rows.get("paciente", 0) + role_rows.get("ambos", 0),
            "caregivers": role_rows.get("cuidador", 0) + role_rows.get("ambos", 0),
            "doctors": role_rows.get("medico", 0),
            "total_medicines": len(medicines),
            "available": available, "critical": critical, "out_of_stock": out_of_stock,
            "total_treatments": total_treatments, "total_takes": total_takes,
            "confirmed_takes": confirmed_takes,
            "pending_takes": max(0, total_takes - confirmed_takes),
            "page_visits": total_page_visits, "accesses": total_accesses,
            "users_logged": users_logged, "assignments": assignment_total,
        },
    }


def _col(n):
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def _cell_xml(row_index, col_index, item):
    if item is None:
        return ""
    formula = None
    cached = None
    style = 0
    value = item
    if isinstance(item, tuple) and len(item) == 2:
        value, style = item
    elif isinstance(item, dict) and "__formula__" in item:
        formula, cached, style = item["__formula__"], item.get("value", 0), item.get("style", 6)
    ref = f"{_col(col_index)}{row_index}"
    style_attr = f' s="{int(style)}"' if style else ""
    if formula is not None:
        v = str(cached) if isinstance(cached, (int, float)) and not isinstance(cached, bool) else "0"
        return f'<c r="{ref}"{style_attr}><f>{escape(_s(formula))}</f><v>{v}</v></c>'
    if value is None:
        return ""
    if isinstance(value, bool):
        return f'<c r="{ref}"{style_attr} t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    text = escape(_s(value))
    return f'<c r="{ref}"{style_attr} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet_xml(rows, widths, freeze_rows=0, auto_filter=None, merges=None, drawing=False):
    max_cols = max([len(r) for r in rows] + [len(widths), 1])
    max_rows = max(len(rows), 1)
    cols_xml = "".join(
        f'<col min="{i}" max="{i}" width="{widths[i-1]}" customWidth="1"/>'
        for i in range(1, len(widths) + 1)
    )
    row_xml = []
    for r_idx, row in enumerate(rows, 1):
        cells = "".join(_cell_xml(r_idx, c_idx, item) for c_idx, item in enumerate(row, 1) if item is not None)
        row_xml.append(f'<row r="{r_idx}" spans="1:{max_cols}">{cells}</row>')
    pane = ""
    if freeze_rows:
        pane = f'<pane ySplit="{freeze_rows}" topLeftCell="A{freeze_rows+1}" activePane="bottomLeft" state="frozen"/>'
    merges_xml = ""
    if merges:
        merge_items = "".join(f'<mergeCell ref="{x}"/>' for x in merges)
        merges_xml = f'<mergeCells count="{len(merges)}">{merge_items}</mergeCells>'
    filter_xml = f'<autoFilter ref="{auto_filter}"/>' if auto_filter else ""
    drawing_xml = '<drawing r:id="rId1"/>' if drawing else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="A1:{_col(max_cols)}{max_rows}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        f'{pane}</sheetView></sheetViews><sheetFormatPr defaultRowHeight="19"/>'
        f'<cols>{cols_xml}</cols><sheetData>{"".join(row_xml)}</sheetData>'
        f'{filter_xml}{merges_xml}'
        '<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
        f'{drawing_xml}'
        '</worksheet>'
    )


def _empty_matrix(rows, cols):
    return [[None for _ in range(cols)] for _ in range(rows)]


def _put(matrix, row, col, value, style=0):
    matrix[row - 1][col - 1] = (value, style) if style else value


def _title_rows(title, note, cols):
    first = [None] * cols
    first[0] = (title, 1)
    second = [None] * cols
    second[0] = (note, 2)
    return [first, second, [None] * cols]


def _data_sheet(title, note, headers, records, widths, state_col=None):
    cols = len(headers)
    rows = _title_rows(title, note, cols)
    rows.append([(h, 3) for h in headers])
    for record in records:
        row = []
        for idx, value in enumerate(record):
            style = 8 if isinstance(value, (int, float)) and not isinstance(value, bool) else 7
            if state_col is not None and idx == state_col:
                label = _s(value)
                style = 9 if label == "Disponible" else (10 if label == "Crítico" else 11)
            row.append((value, style))
        rows.append(row)
    last_row = max(4, len(rows))
    return _sheet_xml(rows, widths, freeze_rows=4, auto_filter=f"A4:{_col(cols)}{last_row}")


def _block(matrix, start_row, start_col, title, headers, data):
    _put(matrix, start_row, start_col, title, 4)
    for offset, header in enumerate(headers):
        _put(matrix, start_row + 1, start_col + offset, header, 3)
    if not data:
        data = [["Sin datos", 0]]
    for r_offset, record in enumerate(data, 2):
        for c_offset, value in enumerate(record):
            style = 8 if isinstance(value, (int, float)) and not isinstance(value, bool) else 7
            _put(matrix, start_row + r_offset, start_col + c_offset, value, style)


def _chart_cache_categories(values):
    points = "".join(f'<c:pt idx="{i}"><c:v>{escape(_s(v))}</c:v></c:pt>' for i, v in enumerate(values))
    return f'<c:strCache><c:ptCount val="{len(values)}"/>{points}</c:strCache>'


def _chart_cache_numbers(values):
    points = "".join(f'<c:pt idx="{i}"><c:v>{float(v or 0):g}</c:v></c:pt>' for i, v in enumerate(values))
    return f'<c:numCache><c:formatCode>0</c:formatCode><c:ptCount val="{len(values)}"/>{points}</c:numCache>'


def _chart_xml(kind, title, category_formula, value_formula, categories, values, bar_direction="col"):
    cns = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    ans = "http://schemas.openxmlformats.org/drawingml/2006/main"
    chart_title = (
        '<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p>'
        '<a:pPr><a:defRPr lang="es-PE" sz="1400" b="1"/></a:pPr>'
        f'<a:r><a:rPr lang="es-PE" sz="1400" b="1"/><a:t>{escape(_s(title))}</a:t></a:r>'
        '<a:endParaRPr lang="es-PE"/></a:p></c:rich></c:tx><c:overlay val="0"/></c:title>'
    )
    series = (
        '<c:ser><c:idx val="0"/><c:order val="0"/><c:tx><c:v>Cantidad</c:v></c:tx>'
        f'<c:cat><c:strRef><c:f>{escape(category_formula)}</c:f>{_chart_cache_categories(categories)}</c:strRef></c:cat>'
        f'<c:val><c:numRef><c:f>{escape(value_formula)}</c:f>{_chart_cache_numbers(values)}</c:numRef></c:val>'
        '</c:ser>'
    )
    if kind == "pie":
        plot = '<c:pieChart><c:varyColors val="1"/>' + series + (
            '<c:dLbls><c:showLegendKey val="0"/><c:showPercent val="1"/><c:showLeaderLines val="1"/></c:dLbls>'
            '<c:firstSliceAng val="0"/></c:pieChart>'
        )
    elif kind == "line":
        series_line = series.replace('</c:val>', '</c:val><c:marker><c:symbol val="circle"/><c:size val="5"/></c:marker>')
        plot = (
            '<c:lineChart><c:grouping val="standard"/>' + series_line +
            '<c:smooth val="0"/><c:axId val="1000001"/><c:axId val="1000002"/></c:lineChart>'
            '<c:catAx><c:axId val="1000001"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            '<c:delete val="0"/><c:axPos val="b"/><c:tickLblPos val="nextTo"/><c:crossAx val="1000002"/>'
            '<c:crosses val="autoZero"/></c:catAx>'
            '<c:valAx><c:axId val="1000002"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            '<c:delete val="0"/><c:axPos val="l"/><c:majorGridlines/><c:numFmt formatCode="0" sourceLinked="0"/>'
            '<c:tickLblPos val="nextTo"/><c:crossAx val="1000001"/><c:crosses val="autoZero"/>'
            '<c:crossesAt val="0"/></c:valAx>'
        )
    else:
        plot = (
            f'<c:barChart><c:barDir val="{bar_direction}"/><c:grouping val="clustered"/><c:varyColors val="0"/>'
            + series +
            '<c:gapWidth val="110"/><c:overlap val="0"/><c:axId val="1000001"/><c:axId val="1000002"/></c:barChart>'
            '<c:catAx><c:axId val="1000001"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            '<c:delete val="0"/><c:axPos val="b"/><c:tickLblPos val="nextTo"/><c:crossAx val="1000002"/>'
            '<c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/><c:lblOffset val="100"/></c:catAx>'
            '<c:valAx><c:axId val="1000002"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            '<c:delete val="0"/><c:axPos val="l"/><c:majorGridlines/><c:numFmt formatCode="0" sourceLinked="0"/>'
            '<c:tickLblPos val="nextTo"/><c:crossAx val="1000001"/><c:crosses val="autoZero"/>'
            '<c:crossesAt val="0"/></c:valAx>'
        )
    legend = "" if kind == "pie" else '<c:legend><c:legendPos val="b"/><c:layout/><c:overlay val="0"/></c:legend>'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<c:chartSpace xmlns:c="{cns}" xmlns:a="{ans}">'
        '<c:date1904 val="0"/><c:lang val="es-PE"/><c:roundedCorners val="1"/>'
        f'<c:chart>{chart_title}<c:plotArea><c:layout/>{plot}</c:plotArea>{legend}'
        '<c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/></c:chart>'
        '<c:printSettings><c:headerFooter/><c:pageMargins b="0.75" l="0.7" r="0.7" t="0.75" header="0.3" footer="0.3"/>'
        '<c:pageSetup/></c:printSettings></c:chartSpace>'
    )


def _drawing_xml(anchors):
    xdr = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    c = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    parts = []
    for index, (from_col, from_row, to_col, to_row) in enumerate(anchors, 1):
        parts.append(
            '<xdr:twoCellAnchor editAs="oneCell">'
            f'<xdr:from><xdr:col>{from_col}</xdr:col><xdr:colOff>50000</xdr:colOff><xdr:row>{from_row}</xdr:row><xdr:rowOff>50000</xdr:rowOff></xdr:from>'
            f'<xdr:to><xdr:col>{to_col}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{to_row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>'
            '<xdr:graphicFrame macro=""><xdr:nvGraphicFramePr>'
            f'<xdr:cNvPr id="{index+1}" name="Gráfico {index}"/><xdr:cNvGraphicFramePr/>'
            '</xdr:nvGraphicFramePr><xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm>'
            f'<a:graphic><a:graphicData uri="{c}"><c:chart xmlns:c="{c}" xmlns:r="{rel}" r:id="rId{index}"/></a:graphicData></a:graphic>'
            '</xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<xdr:wsDr xmlns:xdr="{xdr}" xmlns:a="{a}">' + "".join(parts) + '</xdr:wsDr>'
    )


def _styles_xml():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0"/></numFmts>
<fonts count="4">
<font><sz val="10"/><name val="Aptos"/><family val="2"/><color rgb="FF243746"/></font>
<font><b/><sz val="16"/><name val="Aptos Display"/><color rgb="FFFFFFFF"/></font>
<font><b/><sz val="10"/><name val="Aptos"/><color rgb="FFFFFFFF"/></font>
<font><i/><sz val="9"/><name val="Aptos"/><color rgb="FF607586"/></font>
</fonts>
<fills count="9">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF123B55"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEAF2F7"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF087E8B"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE5F5EC"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2D9"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFCE8E8"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF8E8"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFD9E4EC"/></left><right style="thin"><color rgb="FFD9E4EC"/></right><top style="thin"><color rgb="FFD9E4EC"/></top><bottom style="thin"><color rgb="FFD9E4EC"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="12">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"><alignment horizontal="left" vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="3" borderId="0" xfId="0"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="4" borderId="0" xfId="0"><alignment horizontal="left" vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="4" borderId="1" xfId="0"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="3" borderId="1" xfId="0"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0"><alignment horizontal="right" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="6" borderId="1" xfId="0"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="7" borderId="1" xfId="0"><alignment horizontal="center" vertical="center"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def build_workbook(data):
    """Devuelve bytes de un XLSX válido con hojas, filtros, KPI y gráficos."""
    users = data["users"]
    medicines = data["medicines"]
    treatments = data["treatments"]
    visits = data["visits"]
    doctors = data["doctor_activity"]
    assignments = data["assignments"]
    kpi = data["kpis"]

    user_records = [[x["id"], x["nombres"], x["apellidos"], _role(x["rol"]),
                     x["paciente_vinculado"], x["puesto"]] for x in users]
    medicine_records = [[x["codigo"], x["nombre"], x["categoria"], x["establecimiento"],
                         x["stock"], x["estado"]] for x in medicines]
    treatment_records = [
        [x["id"], x["paciente"], x["registrado_por"], x["medico"], x["nombre"], x["forma"],
         x["dosis"], x["inicio"], x["fin"], x["frecuencia"], x["programadas"], x["confirmadas"],
         x["pendientes"], x["seguimiento"], x["motivo"], x["indicaciones"],
         x["fechas_programadas"], x["detalle_confirmaciones"]]
        for x in treatments
    ]

    report_records = []
    for x in visits:
        report_records.append(["Visitas por pestaña", _view(x["vista"]), "", "",
                               int(x["visitas"] or 0), int(x["usuarios"] or 0), 0, 0])
    if kpi["accesses"] or kpi["users_logged"]:
        report_records.append(["Accesos", "Inicios de sesión", "", "",
                               kpi["accesses"], kpi["users_logged"], 0, 0])
    for x in doctors:
        report_records.append(["Actividad médica", "Registros realizados", x["nombre"], "",
                               int(x["registros"] or 0), int(x["pacientes"] or 0),
                               int(x["asignados"] or 0), int(x["modificaciones"] or 0)])
    for x in assignments:
        report_records.append(["Asignación por paciente", "Medicamentos asignados", x["medico"], x["paciente"],
                               int(x["registros"] or 0), 1, int(x["registros"] or 0), 0])
    for x in data["monthly_visits"]:
        report_records.append(["Visitas por mes", x["periodo"], "", "", int(x["visitas"] or 0), 0, 0, 0])

    users_sheet = _data_sheet(
        "Usuarios registrados",
        "Cuentas existentes al momento de generar el archivo. No se exportan DNI, correos, teléfonos ni credenciales. La tabla de usuarios no conserva fecha de alta.",
        ["ID", "Nombres", "Apellidos", "Rol", "Paciente vinculado", "Puesto declarado"],
        user_records, [9, 22, 25, 24, 28, 24]
    )
    medicines_sheet = _data_sheet(
        "Inventario de medicamentos",
        "Inventario actual del prototipo. Disponible: stock > 10; Crítico: stock entre 1 y 10; Sin stock: stock = 0. No representa existencias oficiales del MINSA.",
        ["Código", "Medicamento", "Categoría", "Establecimiento", "Stock", "Estado"],
        medicine_records, [12, 30, 22, 34, 12, 16], state_col=5
    )
    treatments_sheet = _data_sheet(
        "Tratamientos y tomas",
        "Registros de demostración almacenados en MediCuida. Se incluyen datos necesarios para el seguimiento; el prototipo no debe utilizarse con información clínica real.",
        ["ID", "Paciente", "Registrado por", "Médico", "Medicamento", "Forma", "Dosis",
         "Inicio", "Fin", "Tomas/día", "Programadas", "Confirmadas", "Pendientes",
         "Seguimiento", "Motivo", "Indicaciones", "Fechas programadas", "Confirmaciones (fecha / hora)"],
        treatment_records, [9, 25, 25, 24, 26, 18, 22, 14, 14, 12, 13, 13, 12, 16, 36, 38, 38, 42]
    )
    reports_sheet = _data_sheet(
        "Reportes consolidados",
        "Resumen filtrable de visitas, accesos, actividad médica, asignaciones y visitas mensuales. Los conteos se calculan con los registros existentes.",
        ["Tipo", "Indicador o periodo", "Médico", "Paciente", "Cantidad",
         "Usuarios únicos", "Asignaciones", "Modificaciones"],
        report_records, [24, 27, 25, 28, 14, 16, 15, 16]
    )

    stats = _empty_matrix(max(15, 4 + max(4, 3, len(visits), len(data['monthly_visits']), len(doctors))), 14)
    stats[0][0] = ("Estadísticas de MediCuida", 1)
    stats[1][0] = ("Agregados calculados desde los registros existentes al momento de la exportación.", 2)
    _block(stats, 3, 1, "Usuarios por rol", ["Rol", "Cuentas"], [
        ["Paciente", data["role_rows"].get("paciente", 0)],
        ["Cuidador", data["role_rows"].get("cuidador", 0)],
        ["Paciente y Cuidador", data["role_rows"].get("ambos", 0)],
        ["Médico", data["role_rows"].get("medico", 0)],
    ])
    _block(stats, 3, 4, "Estado del inventario", ["Estado", "Medicamentos"], [
        ["Disponible", kpi["available"]], ["Crítico", kpi["critical"]], ["Sin stock", kpi["out_of_stock"]],
    ])
    visit_chart_rows = [[_view(x["vista"]), int(x["visitas"] or 0)] for x in visits] or [["Sin visitas", 0]]
    _block(stats, 3, 7, "Visitas por pestaña", ["Pestaña", "Visitas"], visit_chart_rows)
    month_chart_rows = [[x["periodo"], int(x["visitas"] or 0)] for x in data["monthly_visits"]] or [["Sin datos", 0]]
    _block(stats, 3, 10, "Tendencia mensual de visitas", ["Periodo", "Visitas"], month_chart_rows)
    doctor_chart_rows = [[_s(x["nombre"]), int(x["registros"] or 0)] for x in doctors] or [["Sin registros médicos", 0]]
    _block(stats, 3, 13, "Registros por médico", ["Médico", "Registros"], doctor_chart_rows)
    stats[11][0] = ("Notas sobre la disponibilidad de datos", 4)
    stats[12][0] = ("La tabla usuarios no guarda fecha de creación: no se calcula una tendencia de altas.", 2)
    stats[13][0] = ("No existe historial de movimientos de stock: solo se informa el inventario actual.", 2)
    stats[14][0] = ("No existe una tabla de citas médicas; el módulo equivalente de este informe es Tratamientos y tomas.", 2)
    stats_sheet = _sheet_xml(stats, [23, 14, 3, 25, 14, 3, 25, 14, 3, 24, 14, 3, 28, 14], freeze_rows=4)

    dash = _empty_matrix(62, 16)
    dash[0][0] = ("MediCuida | Dashboard ejecutivo", 1)
    dash[1][0] = (f"Informe generado: {data['generated']} · Instantánea de solo lectura", 2)
    card_specs = [
        (4, 1, "Usuarios registrados", {"__formula__": f"COUNTA(Usuarios!A5:A{max(5,4+len(users))})", "value": kpi["total_users"], "style": 6}),
        (4, 4, "Medicamentos", {"__formula__": f"COUNTA(Medicamentos!A5:A{max(5,4+len(medicines))})", "value": kpi["total_medicines"], "style": 6}),
        (4, 7, "Tratamientos", {"__formula__": f"COUNTA('Tratamientos y tomas'!A5:A{max(5,4+len(treatments))})", "value": kpi["total_treatments"], "style": 6}),
        (4, 10, "Tomas confirmadas", {"__formula__": f"SUM('Tratamientos y tomas'!L5:L{max(5,4+len(treatments))})", "value": kpi["confirmed_takes"], "style": 6}),
        (4, 13, "Visitas a pestañas", kpi["page_visits"]),
        (7, 1, "Pacientes (incluye rol combinado)", kpi["patients"]),
        (7, 4, "Cuidadores (incluye rol combinado)", kpi["caregivers"]),
        (7, 7, "Médicos", kpi["doctors"]),
        (7, 10, "Asignaciones médicas", kpi["assignments"]),
        (7, 13, "Stock crítico o agotado", kpi["critical"] + kpi["out_of_stock"]),
    ]
    merges = ["A1:P1", "A2:P2", "A4:C4", "A5:C6", "D4:F4", "D5:F6",
              "G4:I4", "G5:I6", "J4:L4", "J5:L6", "M4:P4", "M5:P6",
              "A7:C7", "A8:C9", "D7:F7", "D8:F9", "G7:I7", "G8:I9",
              "J7:L7", "J8:L9", "M7:P7", "M8:P9", "A10:P10"]
    for row, col, label, value in card_specs:
        _put(dash, row, col, label, 5)
        if isinstance(value, dict) and "__formula__" in value:
            dash[row][col - 1] = value
        else:
            _put(dash, row + 1, col, value, 6)
    _put(dash, 10, 1,
         "Datos de demostración. No utilizar con información personal o clínica real. Cada descarga contiene una instantánea actual; no se actualiza automáticamente después de abrir el archivo.",
         2)
    _put(dash, 11, 1, "Gráficos y tendencias", 4)
    dashboard_sheet = _sheet_xml(
        dash, [13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13],
        merges=merges, drawing=True
    )

    role_categories = ["Paciente", "Cuidador", "Paciente y Cuidador", "Médico"]
    role_values = [data["role_rows"].get("paciente", 0), data["role_rows"].get("cuidador", 0),
                   data["role_rows"].get("ambos", 0), data["role_rows"].get("medico", 0)]
    stock_categories = ["Disponible", "Crítico", "Sin stock"]
    stock_values = [kpi["available"], kpi["critical"], kpi["out_of_stock"]]
    visit_categories = [_view(x["vista"]) for x in visits] or ["Sin visitas"]
    visit_values = [int(x["visitas"] or 0) for x in visits] or [0]
    doctor_categories = [_s(x["nombre"]) for x in doctors] or ["Sin registros médicos"]
    doctor_values = [int(x["registros"] or 0) for x in doctors] or [0]
    month_categories = [x["periodo"] for x in data["monthly_visits"]] or ["Sin datos"]
    month_values = [int(x["visitas"] or 0) for x in data["monthly_visits"]] or [0]

    charts = [
        _chart_xml("bar", "Usuarios por rol", "'Estadísticas'!A5:A8", "'Estadisticas'!B5:B8", role_categories, role_values),
        _chart_xml("pie", "Disponibilidad del inventario", "'Estadisticas'!D5:D7", "'Estadisticas'!E5:E7", stock_categories, stock_values),
        _chart_xml("bar", "Visitas por pestaña", f"'Estadisticas'!G5:G{4+len(visit_categories)}",
                   f"'Estadisticas'!H5:H{4+len(visit_categories)}", visit_categories, visit_values),
        _chart_xml("bar", "Registros por médico", f"'Estadisticas'!M5:M{4+len(doctor_categories)}",
                   f"'Estadisticas'!N5:N{4+len(doctor_categories)}", doctor_categories, doctor_values, "bar"),
        _chart_xml("line", "Tendencia mensual de visitas", f"'Estadisticas'!J5:J{4+len(month_categories)}",
                   f"'Estadisticas'!K5:K{4+len(month_categories)}", month_categories, month_values),
    ]
    drawing = _drawing_xml([(0, 11, 7, 26), (8, 11, 15, 26), (0, 27, 7, 42),
                            (8, 27, 15, 42), (0, 43, 7, 58)])

    sheet_files = [dashboard_sheet, users_sheet, treatments_sheet, medicines_sheet, stats_sheet, reports_sheet]
    sheet_names = ["Dashboard", "Usuarios", "Tratamientos y tomas", "Medicamentos", "Estadísticas", "Reportes"]
    overrides = [
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    for i in range(1, 7):
        overrides.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    overrides += [
        '<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>',
        *[f'<Override PartName="/xl/charts/chart{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>' for i in range(1, 6)],
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    ]
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        + "".join(overrides) + '</Types>'
    )
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="18000" windowHeight="10000"/></bookViews>'
        '<sheets>'
        + "".join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(sheet_names, 1))
        + '</sheets><calcPr calcId="191029" fullCalcOnLoad="1" forceFullCalc="1"/></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, 7))
        + '<Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        + '</Relationships>'
    )
    sheet1_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>
</Relationships>"""
    drawing_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart{i}.xml"/>' for i in range(1, 6))
        + '</Relationships>'
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>Informe de MediCuida</dc:title><dc:creator>MediCuida</dc:creator>'
        '<dc:subject>Dashboard y reportes de demostración</dc:subject></cp:coreProperties>'
    )
    app_props = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>MediCuida</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>'
        '<TitlesOfParts><vt:vector size="6" baseType="lpstr">'
        + "".join(f'<vt:lpstr>{escape(n)}</vt:lpstr>' for n in sheet_names)
        + '</vt:vector></TitlesOfParts></Properties>'
    )

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/styles.xml", _styles_xml())
        for index, sheet in enumerate(sheet_files, 1):
            zf.writestr(f"xl/worksheets/sheet{index}.xml", sheet)
        zf.writestr("xl/worksheets/_rels/sheet1.xml.rels", sheet1_rels)
        zf.writestr("xl/drawings/drawing1.xml", drawing)
        zf.writestr("xl/drawings/_rels/drawing1.xml.rels", drawing_rels)
        for index, chart in enumerate(charts, 1):
            zf.writestr(f"xl/charts/chart{index}.xml", chart)
        zf.writestr("docProps/core.xml", core)
        zf.writestr("docProps/app.xml", app_props)
    return output.getvalue()
