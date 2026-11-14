"""Seguimiento de tratamientos ficticios y roles para MediCuida.
Nunca usar para información médica real. Datos de demostración solamente.
"""
from __future__ import annotations
import hashlib
import hmac
import re
import sqlite3
from datetime import date, datetime, time as dt_time, timedelta, timezone
from urllib.parse import urlsplit, parse_qs

DNI_RE = re.compile(r"^[0-9]{8}$")
TREAT_PATH = re.compile(r"^/api/tratamientos/([0-9]{1,12})$")
TAKE_PATH = re.compile(r"^/api/tratamientos/([0-9]{1,12})/confirmar$")
NOTICE_PATH = re.compile(r"^/api/avisos/([0-9]{1,12})/leer$")
BASE_ROLES = ("paciente", "cuidador", "ambos")
ALL_ROLES = BASE_ROLES + ("medico",)


def create_tables(connect):
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS tratamientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titular_dni TEXT NOT NULL,
            autor_dni TEXT NOT NULL,
            nombre TEXT NOT NULL,
            forma TEXT NOT NULL,
            dosis TEXT NOT NULL,
            inicio TEXT NOT NULL,
            fin TEXT NOT NULL,
            frecuencia INTEGER NOT NULL,
            hora TEXT NOT NULL,
            medico_nombre TEXT NOT NULL DEFAULT '',
            motivo TEXT NOT NULL DEFAULT '',
            indicaciones TEXT NOT NULL DEFAULT '',
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_trat_titular ON tratamientos(titular_dni);
        CREATE TABLE IF NOT EXISTS tomas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tratamiento_id INTEGER NOT NULL REFERENCES tratamientos(id) ON DELETE CASCADE,
            fecha TEXT NOT NULL,
            confirmada TEXT DEFAULT NULL,
            confirmada_por TEXT DEFAULT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tomas_trat ON tomas(tratamiento_id);
        CREATE TABLE IF NOT EXISTS avisos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titular_dni TEXT NOT NULL,
            tratamiento_id INTEGER,
            medico_dni TEXT NOT NULL,
            medico_nombre TEXT NOT NULL,
            motivo TEXT NOT NULL,
            detalle TEXT NOT NULL,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            leido INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_avisos_titular ON avisos(titular_dni);
        """)


def string(value, label, minimum=2, maximum=150):
    if not isinstance(value, str):
        raise ValueError("El campo «"+label+"» es obligatorio.")
    val = " ".join(value.split())
    if not (minimum <= len(val) <= maximum) or any(ord(ch) < 32 for ch in val):
        raise ValueError("El campo «"+label+"» no es válido.")
    return val


def verify_dni(val):
    return isinstance(val, str) and DNI_RE.fullmatch(val) is not None


def allowed(user, dni):
    if not verify_dni(dni):
        return False
    if user["dni"] == dni:
        return True
    role = user.get("rol")
    if role == "medico":
        return True  # SOLO DEMO: no existe verificación profesional ni consentimiento externo
    return role in ("cuidador", "ambos") and user.get("dni_paciente") == dni


def target(user, supplied):
    dni = user["dni"] if supplied is None or supplied == "" else str(supplied).strip()
    if not allowed(user, dni):
        raise PermissionError("No tienes permiso para consultar este DNI. Para Cuidador se requiere el paciente vinculado en tu perfil.")
    return dni


def validated_treatment(data, role):
    if not isinstance(data, dict):
        raise ValueError("Envía un objeto JSON.")
    info = {
        "nombre": string(data.get("nombre"), "Nombre del medicamento",2,90),
        "forma": string(data.get("forma"), "Forma farmacéutica",2,60),
        "dosis": string(data.get("dosis"), "Dosis de demostración",2,120),
    }
    start, end = data.get("inicio"), data.get("fin")
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, TypeError):
        raise ValueError("Ingresa fechas de inicio y fin válidas.")
    days = (b - a).days+1
    if not 1 <= days <= 30:
        raise ValueError("El intervalo debe ser de 1 a 30 días.")
    freq = data.get("frecuencia")
    if type(freq) is not int or freq not in (1,2,3):
        raise ValueError("Escoge 1, 2 o 3 tomas diarias de demostración.")
    hour = data.get("hora")
    # Algunos navegadores envían input type=time como HH:MM:SS.
    # Aceptar horas con o sin segundos y guardar con precisión de minuto.
    if not isinstance(hour, str) or not re.fullmatch(
        r"(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9](?:\.[0-9]{1,3})?)?", hour
    ):
        raise ValueError("La hora inicial no es válida.")
    hour = hour[:5]
    info.update(inicio=start,fin=end,frecuencia=freq,hora=hour)
    if role == "medico":
        info["medico_nombre"] = string(data.get("medico_nombre"),"Nombre del médico",4,120)
        info["motivo"] = string(data.get("motivo"),"Motivo del registro",4,400)
        info["indicaciones"] = string(data.get("indicaciones"),"Forma de administración",4,400)
    else:
        info.update(medico_nombre="",motivo="",indicaciones="")
    return info


def schedule(info):
    start = date.fromisoformat(info["inicio"])
    count = (date.fromisoformat(info["fin"])-start).days+1
    hour = dt_time.fromisoformat(info["hora"])
    result = []
    for d in range(count):
        base=datetime.combine(start+timedelta(days=d),hour)
        for n in range(info["frecuencia"]):
            moment=base+timedelta(minutes=n*1440/info["frecuencia"])
            result.append(moment.isoformat(timespec="seconds"))
    return result


def serialize_treatment(db, row):
    result=dict(row)
    result["tomas"]=[dict(t) for t in db.execute(
        "SELECT id, fecha, confirmada, confirmada_por FROM tomas WHERE tratamiento_id=? ORDER BY fecha,id",(row["id"],)
    )]
    return result


def error(handler,status,msg):
    handler.json_out(status,{"error":msg})


def dispatch(handler,method,path,connect):
    """True when route is claimed, sends the response even on error."""
    if not (path.startswith("/api/tratamientos") or path.startswith("/api/historial") or
            path.startswith("/api/avisos") or path == "/api/rol"):
        return False
    session = handler.current_session()
    if not session:
        error(handler,401,"Inicia sesión para consultar los registros.")
        return True
    user=session["usuario"]
    uri=urlsplit(handler.path)
    query=parse_qs(uri.query)
    try:
        if method == "GET" and path=="/api/tratamientos":
            dni=target(user,query.get("dni",[""])[0])
            with connect() as db:
                rows=db.execute("SELECT * FROM tratamientos WHERE titular_dni=? ORDER BY id DESC",(dni,)).fetchall()
                meds=[serialize_treatment(db,row) for row in rows]
            handler.json_out(200,{"dni":dni,"tratamientos":meds})
            return True

        if method == "GET" and path=="/api/historial":
            dni=target(user,query.get("dni",[""])[0])
            with connect() as db:
                rows=db.execute("""
                    SELECT tr.nombre, tm.fecha AS programada, tm.confirmada, tm.confirmada_por
                    FROM tomas tm JOIN tratamientos tr ON tr.id=tm.tratamiento_id
                    WHERE tr.titular_dni=? AND tm.confirmada IS NOT NULL
                    ORDER BY tm.confirmada DESC LIMIT 1500
                """,(dni,)).fetchall()
            handler.json_out(200,{"dni":dni,"historial":[dict(r) for r in rows]})
            return True

        if method == "GET" and path=="/api/avisos":
            with connect() as db:
                rows=db.execute("SELECT id,tratamiento_id,medico_nombre,motivo,detalle,fecha,leido FROM avisos WHERE titular_dni=? ORDER BY id DESC LIMIT 40",(user["dni"],)).fetchall()
            handler.json_out(200,{"avisos":[dict(r) for r in rows]})
            return True

        if method=="POST" and NOTICE_PATH.fullmatch(path):
            aid=int(NOTICE_PATH.fullmatch(path).group(1))
            with connect() as db:
                cursor=db.execute("UPDATE avisos SET leido=1 WHERE id=? AND titular_dni=?",(aid,user["dni"]))
            handler.json_out(200,{"ok":bool(cursor.rowcount)})
            return True

        if method=="POST" and path=="/api/rol":
            data=handler.read_data()
            role=data.get("rol")
            if role not in BASE_ROLES:
                raise ValueError("Puedes elegir Paciente, Cuidador o Paciente y Cuidador.")
            old=user.get("rol","paciente")
            vinculo=data.get("dni_paciente","")
            vinculo=str(vinculo).strip() if vinculo is not None else ""
            if role in ("cuidador","ambos") and vinculo:
                if not verify_dni(vinculo) or vinculo == user["dni"]:
                    raise ValueError("El DNI del paciente vinculado debe tener 8 dígitos y ser diferente al tuyo.")
            else:
                vinculo=""
            with connect() as db:
                row=db.execute("SELECT * FROM usuarios WHERE dni=?",(user["dni"],)).fetchone()
                if not row:
                    error(handler,404,"No se encontró tu cuenta.")
                    return True
                if old=="medico":
                    password=data.get("contrasena","")
                    if not isinstance(password,str):
                        raise ValueError("Confirma tu contraseña para cambiar desde Médico.")
                    computed=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(row["salt"]),200000)
                    if not hmac.compare_digest(row["hash"],computed.hex()):
                        error(handler,403,"La contraseña de confirmación es incorrecta.")
                        return True
                db.execute("UPDATE usuarios SET rol=?,dni_paciente=? WHERE dni=?",(role,vinculo or None,user["dni"]))
                updated=db.execute("SELECT * FROM usuarios WHERE dni=?",(user["dni"],)).fetchone()
            info={key:updated[key] for key in ("nombres","apellidos","dni","correo","rol","dni_paciente","ruc","puesto")}
            session["usuario"]=info
            handler.json_out(200,{"usuario":info,"mensaje":"El rol se actualizó correctamente."})
            return True

        if method=="POST" and path=="/api/tratamientos":
            data=handler.read_data()
            dni=target(user,data.get("dni_paciente"))
            info=validated_treatment(data,user.get("rol"))
            with connect() as db:
                current=db.execute("SELECT count(*) FROM tratamientos WHERE titular_dni=?",(dni,)).fetchone()[0]
                if current >= 60:
                    raise ValueError("Se alcanzó el límite de 60 tratamientos de demostración por usuario.")
                info.update(titular_dni=dni,autor_dni=user["dni"])
                cur=db.execute("""INSERT INTO tratamientos
                    (titular_dni,autor_dni,nombre,forma,dosis,inicio,fin,frecuencia,hora,medico_nombre,motivo,indicaciones)
                    VALUES (:titular_dni,:autor_dni,:nombre,:forma,:dosis,:inicio,:fin,:frecuencia,:hora,:medico_nombre,:motivo,:indicaciones)""",info)
                db.executemany("INSERT INTO tomas(tratamiento_id,fecha) VALUES(?,?)",[(cur.lastrowid,t) for t in schedule(info)])
                row=db.execute("SELECT * FROM tratamientos WHERE id=?",(cur.lastrowid,)).fetchone()
                result=serialize_treatment(db,row)
            handler.json_out(201,{"tratamiento":result,"mensaje":"Tratamiento ficticio registrado."})
            return True

        m=TAKE_PATH.fullmatch(path)
        if method=="POST" and m:
            tid=int(m.group(1))
            with connect() as db:
                record=db.execute("SELECT * FROM tratamientos WHERE id=?",(tid,)).fetchone()
                if not record:
                    error(handler,404,"Tratamiento no encontrado.")
                    return True
                if not allowed(user,record["titular_dni"]):
                    raise PermissionError("No tienes acceso a este tratamiento.")
                row=db.execute("SELECT id FROM tomas WHERE tratamiento_id=? AND confirmada IS NULL ORDER BY fecha,id LIMIT 1",(tid,)).fetchone()
                if not row:
                    raise ValueError("Ya están confirmadas todas las tomas.")
                now=datetime.now(timezone.utc).isoformat(timespec="seconds")
                db.execute("UPDATE tomas SET confirmada=?,confirmada_por=? WHERE id=?",(now,user["dni"],row["id"]))
            handler.json_out(200,{"mensaje":"Toma ficticia confirmada correctamente."})
            return True

        m=TREAT_PATH.fullmatch(path)
        if method=="PUT" and m:
            if user.get("rol") != "medico":
                raise PermissionError("Solo un Médico puede modificar tratamientos registrados.")
            tid=int(m.group(1))
            data=handler.read_data()
            reason=string(data.get("motivo_modificacion"),"Motivo de la modificación",6,500)
            info=validated_treatment(data,"medico")
            with connect() as db:
                old=db.execute("SELECT * FROM tratamientos WHERE id=?",(tid,)).fetchone()
                if not old: error(handler,404,"Tratamiento no encontrado.");return True
                if not allowed(user,old["titular_dni"]):
                    raise PermissionError("No tienes acceso a este paciente.")
                # Las confirmaciones anteriores permanecen en el historial; solo se regeneran tomas pendientes.
                existing={r["fecha"] for r in db.execute("SELECT fecha FROM tomas WHERE tratamiento_id=? AND confirmada IS NOT NULL",(tid,))}
                db.execute("DELETE FROM tomas WHERE tratamiento_id=? AND confirmada IS NULL",(tid,))
                new_dates=[d for d in schedule(info) if d not in existing]
                db.executemany("INSERT INTO tomas(tratamiento_id,fecha) VALUES(?,?)",[(tid,d) for d in new_dates])
                db.execute("""UPDATE tratamientos SET nombre=:nombre,forma=:forma,dosis=:dosis,
                    inicio=:inicio,fin=:fin,frecuencia=:frecuencia,hora=:hora,
                    medico_nombre=:medico_nombre,motivo=:motivo,indicaciones=:indicaciones,
                    actualizado_en=CURRENT_TIMESTAMP WHERE id=:id""",{**info,"id":tid})
                if old["titular_dni"] != user["dni"]:
                    who=info["medico_nombre"]
                    db.execute("""INSERT INTO avisos
                        (titular_dni,tratamiento_id,medico_dni,medico_nombre,motivo,detalle)
                        VALUES(?,?,?,?,?,?)""",
                        (old["titular_dni"],tid,user["dni"],who,reason,
                        "El médico actualizó el registro del medicamento "+info["nombre"]+". Motivo: "+reason))
                updated=db.execute("SELECT * FROM tratamientos WHERE id=?",(tid,)).fetchone()
                result=serialize_treatment(db,updated)
            handler.json_out(200,{"tratamiento":result,"mensaje":"Tratamiento modificado. Se dejó aviso para el paciente."})
            return True

        m=TREAT_PATH.fullmatch(path)
        if method=="DELETE" and m:
            tid=int(m.group(1))
            with connect() as db:
                old=db.execute("SELECT * FROM tratamientos WHERE id=?",(tid,)).fetchone()
                if not old: error(handler,404,"Tratamiento no encontrado.");return True
                # El médico no puede borrar silenciosamente registros ajenos.
                if not allowed(user,old["titular_dni"]) or (user["dni"] != old["titular_dni"] and old["autor_dni"] != user["dni"]):
                    raise PermissionError("Solo el titular o quien creó el registro puede eliminarlo.")
                db.execute("DELETE FROM tomas WHERE tratamiento_id=?",(tid,))
                db.execute("DELETE FROM tratamientos WHERE id=?",(tid,))
            handler.json_out(200,{"mensaje":"Tratamiento de demostración eliminado."})
            return True

        error(handler,404,"Ruta no encontrada.")
        return True
    except PermissionError as exc:
        error(handler,403,str(exc))
    except ValueError as exc:
        error(handler,400,str(exc))
    except (sqlite3.IntegrityError,sqlite3.OperationalError):
        error(handler,500,"No fue posible guardar los cambios en SQLite.")
    return True
