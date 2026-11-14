"""MediCuida Grupo 1: prototipo académico, no usar con datos personales reales."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import webbrowser
from pathlib import Path
from threading import Lock
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import seguimiento
import persistencia

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "datos"
DATA_DIR.mkdir(exist_ok=True)
DB = DATA_DIR / "medicuida.sqlite3"
PORT = int(os.environ.get("PORT") or os.environ.get("MEDICUIDA_PORT", "8765"))
HOST = os.environ.get("MEDICUIDA_HOST", "127.0.0.1")
SESSIONS = {}
LOCK = Lock()
SESSION_AGE = 8 * 3600
COOKIE = "medicuida_session"
STATIC = {"/": "index.html", "/index.html": "index.html", "/styles.css": "styles.css", "/app.js": "app.js"}
MIMES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}
MED_PATH = re.compile(r"^/api/medicamentos/MED-(\d{1,9})$")
DNI = re.compile(r"^[0-9]{8}$")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

def connect():
    return persistencia.open_connection(DB)

def init_db():
    with connect() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS usuarios(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombres TEXT NOT NULL, apellidos TEXT NOT NULL, dni TEXT NOT NULL UNIQUE,
                correo TEXT NOT NULL UNIQUE, salt TEXT NOT NULL, hash TEXT NOT NULL,
                rol TEXT NOT NULL DEFAULT 'paciente',
                dni_paciente TEXT,
                ruc TEXT,
                puesto TEXT
            );
            CREATE TABLE IF NOT EXISTS medicamentos(
                codigo INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL, categoria TEXT NOT NULL, establecimiento TEXT NOT NULL,
                stock INTEGER NOT NULL CHECK(stock>=0)
            );
            CREATE TABLE IF NOT EXISTS configuracion(clave TEXT PRIMARY KEY, valor TEXT);
        """)
        # Migración compatible con usuarios registrados en versiones anteriores.
        existing = {row["name"] for row in c.execute("PRAGMA table_info(usuarios)")}
        for name, ddl in (
            ("rol", "TEXT NOT NULL DEFAULT 'paciente'"),
            ("dni_paciente", "TEXT"),
            ("ruc", "TEXT"),
            ("puesto", "TEXT"),
        ):
            if name not in existing:
                c.execute(f"ALTER TABLE usuarios ADD COLUMN {name} {ddl}")
        # Si la base ya contiene datos, conserva cambios anteriores.
        # La ampliación a 150 registros se ejecuta una sola vez por base.
        catalogo = json.loads((ROOT / "backend" / "medicamentos_iniciales.json").read_text(encoding="utf-8"))
        if not c.execute("SELECT 1 FROM configuracion WHERE clave='seeded'").fetchone():
            c.executemany("INSERT INTO medicamentos(codigo,nombre,categoria,establecimiento,stock) VALUES (:codigo,:nombre,:categoria,:establecimiento,:stock)",catalogo)
            c.execute("INSERT INTO configuracion(clave,valor) VALUES('seeded','1')")
        if not c.execute("SELECT 1 FROM configuracion WHERE clave='catalogo150_v2'").fetchone():
            c.executemany("INSERT OR IGNORE INTO medicamentos(codigo,nombre,categoria,establecimiento,stock) VALUES (:codigo,:nombre,:categoria,:establecimiento,:stock)",catalogo)
            c.execute("INSERT INTO configuracion(clave,valor) VALUES('catalogo150_v2','1')")


def med(row):
    return {"id": f"MED-{row['codigo']:03d}", "nombre": row["nombre"],
            "categoria": row["categoria"], "establecimiento": row["establecimiento"],
            "stock": row["stock"]}

def user(row):
    return {k: row[k] for k in ("nombres", "apellidos", "dni", "correo", "rol", "dni_paciente", "ruc", "puesto")}

def clean(value, field, minimum=2, maximum=90):
    if not isinstance(value, str):
        raise ValueError(f"El campo {field} es obligatorio.")
    value = " ".join(value.split())
    if not minimum <= len(value) <= maximum or any(ord(c)<32 for c in value):
        raise ValueError(f"El campo {field} no es válido.")
    return value

def validate_med(data):
    result = {k: clean(data.get(k), k, 2, size) for k,size in
              (("nombre",90),("categoria",65),("establecimiento",110))}
    stock = data.get("stock")
    if type(stock) is not int or not 0 <= stock <= 1000000:
        raise ValueError("El stock debe ser un número entero no negativo.")
    result["stock"] = stock
    return result

def validate_user(data):
    if not isinstance(data, dict):
        raise ValueError("Los datos de registro deben enviarse como un objeto JSON.")
    rol = data.get("rol")
    if rol not in ("paciente", "cuidador", "medico"):
        raise ValueError("Selecciona un rol válido: Paciente, Cuidador o Médico.")
    result = {"rol": rol,
              "nombres": clean(data.get("nombres"),"nombres",2,80),
              "apellidos": clean(data.get("apellidos"),"apellidos",2,100)}
    dni = data.get("dni")
    if not isinstance(dni,str) or not DNI.fullmatch(dni):
        raise ValueError("El DNI debe contener exactamente ocho números.")
    correo = data.get("correo")
    if not isinstance(correo,str) or len(correo)>120 or not EMAIL.fullmatch(correo.strip()):
        raise ValueError("El correo electrónico no es válido.")
    password = data.get("contrasena")
    if not isinstance(password,str) or not 8 <= len(password) <= 72 or password != password.strip():
        raise ValueError("La contraseña debe tener entre 8 y 72 caracteres, sin espacios al inicio o final.")
    datos_rol = {"dni_paciente": None, "ruc": None, "puesto": None}
    if rol == "cuidador":
        dni_paciente = data.get("dni_paciente")
        if not isinstance(dni_paciente, str) or not DNI.fullmatch(dni_paciente):
            raise ValueError("Ingresa el DNI de ocho dígitos del paciente.")
        if dni_paciente == dni:
            raise ValueError("El DNI del paciente debe ser diferente de tu DNI.")
        datos_rol["dni_paciente"] = dni_paciente
    if rol == "medico":
        ruc = data.get("ruc")
        if not isinstance(ruc, str) or not re.fullmatch(r"[0-9]{11}", ruc):
            raise ValueError("El RUC del establecimiento debe tener exactamente 11 dígitos.")
        datos_rol["ruc"] = ruc
        datos_rol["puesto"] = clean(data.get("puesto"), "puesto", 2, 100)
    return {**result, **datos_rol, "dni": dni, "correo": correo.strip().lower(), "contrasena":password}

class Handler(BaseHTTPRequestHandler):
    server_version = "MediCuidaDemo/3"
    def headers_common(self):
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Referrer-Policy","no-referrer")
    def json_out(self, status, obj, cookie=None):
        raw = json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status); self.headers_common()
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw)))
        if cookie: self.send_header("Set-Cookie",cookie)
        self.end_headers(); self.wfile.write(raw)
    def new_cookie(self, value, age):
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto","").lower()=="https" else ""
        return f"{COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}{secure}"
    def read_data(self):
        if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json":
            raise ValueError("Se requiere application/json.")
        try: length = int(self.headers.get("Content-Length","-1"))
        except ValueError: raise ValueError("Solicitud inválida.") from None
        if not 1 <= length <= 16384: raise ValueError("Solicitud demasiado grande o vacía.")
        try: data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError,ValueError): raise ValueError("JSON inválido.") from None
        if not isinstance(data,dict): raise ValueError("Se esperaba un objeto JSON.")
        return data
    def valid_origin(self):
        origin = self.headers.get("Origin")
        if not origin: return True
        p = urlsplit(origin)
        scheme = self.headers.get("X-Forwarded-Proto") or "http"
        return p.scheme.lower()==scheme.lower() and p.netloc.lower()==self.headers.get("Host","").lower()
    def current_session(self):
        try:
            cookies=SimpleCookie(); cookies.load(self.headers.get("Cookie",""))
            token=cookies.get(COOKIE)
            if token is None: return None
            with LOCK:
                session=SESSIONS.get(token.value)
                if not session: return None
                if session["expiry"]<time.time():
                    SESSIONS.pop(token.value,None)
                    return None
                return session
        except Exception: return None
    def auth(self):
        if self.current_session(): return True
        self.json_out(HTTPStatus.UNAUTHORIZED,{"error":"Debes iniciar sesión."})
        return False
    def auth_medico(self):
        session = self.current_session()
        if not session:
            self.json_out(HTTPStatus.UNAUTHORIZED, {"error":"Debes iniciar sesión."})
            return False
        if session["usuario"].get("rol") != "medico":
            self.json_out(HTTPStatus.FORBIDDEN, {"error":"Solo los médicos tienen permiso para administrar el stock."})
            return False
        return True
    def do_GET(self):
        path=urlsplit(self.path).path
        if seguimiento.dispatch(self,"GET",path,connect): return
        if path=="/api/sesion":
            session=self.current_session()
            return self.json_out(200,{"autenticado":bool(session),"usuario":session["usuario"] if session else None})
        if path=="/api/medicamentos":
            if not self.auth(): return
            with connect() as c: rows=c.execute("SELECT * FROM medicamentos ORDER BY codigo").fetchall()
            return self.json_out(200,{"medicamentos":[med(r) for r in rows]})
        if path in STATIC:
            file=ROOT/STATIC[path]
            raw=file.read_bytes()
            self.send_response(200);self.headers_common()
            self.send_header("Content-Type",MIMES[file.suffix])
            self.send_header("Content-Length",str(len(raw)))
            self.end_headers();self.wfile.write(raw)
            return
        self.json_out(404,{"error":"Ruta no encontrada."})
    def do_POST(self):
        if not self.valid_origin(): return self.json_out(403,{"error":"Origen no autorizado."})
        path=urlsplit(self.path).path
        if seguimiento.dispatch(self,"POST",path,connect): return
        if path=="/api/logout":
            try:
                cookies=SimpleCookie();cookies.load(self.headers.get("Cookie",""))
                item=cookies.get(COOKIE)
                if item:
                    with LOCK: SESSIONS.pop(item.value,None)
            except Exception: pass
            return self.json_out(200,{"ok":True},self.new_cookie("",0))
        if path=="/api/register":
            try:
                data=validate_user(self.read_data())
            except ValueError as e: return self.json_out(400,{"error":str(e)})
            salt=secrets.token_bytes(16)
            digest=hashlib.pbkdf2_hmac("sha256",data["contrasena"].encode(),salt,200000).hex()
            try:
                with connect() as c:
                    c.execute("""INSERT INTO usuarios(nombres,apellidos,dni,correo,salt,hash,rol,dni_paciente,ruc,puesto)
                                 VALUES(?,?,?,?,?,?,?,?,?,?)""",
                              (data["nombres"],data["apellidos"],data["dni"],data["correo"],
                               salt.hex(),digest,data["rol"],data["dni_paciente"],data["ruc"],data["puesto"]))
            except sqlite3.IntegrityError as e:
                error=str(e)
                msg="Ese DNI ya está registrado." if "usuarios.dni" in error else "Ese correo ya está registrado." if "usuarios.correo" in error else "Error al registrar el usuario."
                return self.json_out(409,{"error":msg})
            return self.json_out(201,{"ok":True,"mensaje":"Cuenta creada. Inicia sesión con DNI y contraseña."})
        if path=="/api/login":
            try: data=self.read_data()
            except ValueError as e: return self.json_out(400,{"error":str(e)})
            dni=data.get("dni"); pw=data.get("contrasena")
            if not isinstance(dni,str) or not DNI.fullmatch(dni) or not isinstance(pw,str):
                return self.json_out(400,{"error":"Ingresa DNI y contraseña válidos."})
            with connect() as c: row=c.execute("SELECT * FROM usuarios WHERE dni=?",(dni,)).fetchone()
            if row is None: return self.json_out(401,{"error":"DNI o contraseña incorrectos."})
            digest=hashlib.pbkdf2_hmac("sha256",pw.encode(),bytes.fromhex(row["salt"]),200000).hex()
            if not hmac.compare_digest(row["hash"],digest):
                return self.json_out(401,{"error":"DNI o contraseña incorrectos."})
            account=user(row); token=secrets.token_urlsafe(32)
            with LOCK: SESSIONS[token]={"expiry":time.time()+SESSION_AGE,"usuario":account}
            return self.json_out(200,{"ok":True,"usuario":account},self.new_cookie(token,SESSION_AGE))
        if path=="/api/medicamentos":
            if not self.auth_medico(): return
            try: data=validate_med(self.read_data())
            except ValueError as e: return self.json_out(400,{"error":str(e)})
            with connect() as c:
                cur=c.execute("INSERT INTO medicamentos(nombre,categoria,establecimiento,stock) VALUES (:nombre,:categoria,:establecimiento,:stock)",data)
                row=c.execute("SELECT * FROM medicamentos WHERE codigo=?",(cur.lastrowid,)).fetchone()
            return self.json_out(201,{"medicamento":med(row),"mensaje":"Medicamento agregado."})
        return self.json_out(404,{"error":"Ruta no encontrada."})
    def do_PUT(self):
        if not self.valid_origin(): return self.json_out(403,{"error":"Origen no autorizado."})
        path=urlsplit(self.path).path
        if seguimiento.dispatch(self,"PUT",path,connect): return
        m=MED_PATH.fullmatch(path)
        if not m: return self.json_out(404,{"error":"Ruta no encontrada."})
        if not self.auth_medico(): return
        try: data=validate_med(self.read_data())
        except ValueError as e: return self.json_out(400,{"error":str(e)})
        with connect() as c:
            cur=c.execute("UPDATE medicamentos SET nombre=:nombre,categoria=:categoria,establecimiento=:establecimiento,stock=:stock WHERE codigo=:codigo",{**data,"codigo":int(m.group(1))})
            row=c.execute("SELECT * FROM medicamentos WHERE codigo=?",(int(m.group(1)),)).fetchone() if cur.rowcount else None
        if not row: return self.json_out(404,{"error":"Medicamento no encontrado."})
        return self.json_out(200,{"medicamento":med(row),"mensaje":"Medicamento actualizado."})
    def do_DELETE(self):
        if not self.valid_origin(): return self.json_out(403,{"error":"Origen no autorizado."})
        path=urlsplit(self.path).path
        if seguimiento.dispatch(self,"DELETE",path,connect): return
        m=MED_PATH.fullmatch(path)
        if not m: return self.json_out(404,{"error":"Ruta no encontrada."})
        if not self.auth_medico(): return
        with connect() as c: cur=c.execute("DELETE FROM medicamentos WHERE codigo=?",(int(m.group(1)),))
        if not cur.rowcount: return self.json_out(404,{"error":"Medicamento no encontrado."})
        return self.json_out(200,{"ok":True,"mensaje":"Medicamento eliminado."})

def main():
    # En Render, restaura primero la última copia desde el Postgres externo.
    # Si DATABASE_URL está configurada y Postgres falla, NO iniciar con datos vacíos.
    persistencia.restore_database(DB)
    init_db()
    seguimiento.create_tables(connect)
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    url=f"http://127.0.0.1:{PORT}"
    print("MediCuida Grupo 1",url,flush=True)
    if os.environ.get("MEDICUIDA_NO_BROWSER")!="1": webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=="__main__": main()
