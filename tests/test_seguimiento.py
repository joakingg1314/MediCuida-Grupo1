"""Pruebas del módulo de seguimiento con datos 100% ficticios."""
import hashlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import seguimiento


class FakeHandler:
    def __init__(self, usuario, path, payload=None):
        self.usuario = usuario
        self.path = path
        self.payload = payload
        self.status = None
        self.result = None
    def current_session(self):
        return {"usuario": self.usuario} if self.usuario else None
    def read_data(self):
        return self.payload
    def json_out(self, status, result):
        self.status = int(status)
        self.result = result


class SeguimientoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        seguimiento.create_tables(self.connect)
        self.paciente = self.user("10000001", "paciente")
        self.cuidador = self.user("20000002", "cuidador", "10000001")
        self.medico = self.user("30000003", "medico")
        self.password = "test123456"
        salt = b"0"*16
        digest = hashlib.pbkdf2_hmac("sha256",self.password.encode(),salt,200000).hex()
        with self.connect() as db:
            db.execute("""CREATE TABLE usuarios (
                id INTEGER PRIMARY KEY,
                nombres TEXT, apellidos TEXT, dni TEXT,
                correo TEXT, salt TEXT, hash TEXT,
                rol TEXT, dni_paciente TEXT, ruc TEXT, puesto TEXT)""")
            db.execute("INSERT INTO usuarios(id,nombres,apellidos,dni,correo,salt,hash,rol) VALUES(1,'María','Ejemplo','30000003','fake@example.test',?,?,?)",
                (salt.hex(),digest,"medico"))
    def tearDown(self):
        self.temp.cleanup()
    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db
    @staticmethod
    def user(dni,role,linked=None):
        return {"dni":dni,"nombres":"Usuario","apellidos":"Ejemplo","rol":role,"dni_paciente":linked,
                "correo":"fake@example.test","ruc":None,"puesto":None}
    def call(self, user, method, path, data=None):
        handler = FakeHandler(user,path,data)
        self.assertTrue(seguimiento.dispatch(handler,method,path,self.connect))
        return handler
    def example(self,linked=""):
        return {"nombre":"Medicina Ficticia", "forma":"Tableta", "dosis":"1 unidad de prueba",
                "inicio":"2026-12-01","fin":"2026-12-03","frecuencia":1,"hora":"08:00",
                "dni_paciente":linked,"medico_nombre":"Doctor Ficticio",
                "motivo":"Evaluación académica ficticia","indicaciones":"Solo un ejemplo de administración"}
    def test_permissions_and_shared_treatments(self):
        created=self.call(self.cuidador,"POST","/api/tratamientos",self.example("10000001"))
        self.assertEqual(created.status,201)
        tid=created.result["tratamiento"]["id"]
        own=self.call(self.cuidador,"GET","/api/tratamientos")
        self.assertEqual(own.result["tratamientos"],[])
        patient=self.call(self.paciente,"GET","/api/tratamientos")
        self.assertEqual(patient.status,200)
        self.assertEqual(patient.result["tratamientos"][0]["id"],tid)
        external=self.call(self.cuidador,"GET","/api/tratamientos?dni=99999999")
        self.assertEqual(external.status,403)
        confirmed=self.call(self.paciente,"POST",f"/api/tratamientos/{tid}/confirmar")
        self.assertEqual(confirmed.status,200)
        history=self.call(self.cuidador,"GET","/api/historial?dni=10000001")
        self.assertEqual(len(history.result["historial"]),1)
        doctor_updated=self.example()
        doctor_updated["motivo_modificacion"]="Ajustar información ficticia"
        edited=self.call(self.medico,"PUT",f"/api/tratamientos/{tid}",doctor_updated)
        self.assertEqual(edited.status,200)
        notices=self.call(self.paciente,"GET","/api/avisos")
        self.assertEqual(len(notices.result["avisos"]),1)
        self.assertIn("Ajustar información",notices.result["avisos"][0]["detalle"])
        unauthorized=self.call(self.paciente,"PUT",f"/api/tratamientos/{tid}",doctor_updated)
        self.assertEqual(unauthorized.status,403)
    def test_horas_de_navegador_con_segundos(self):
        # En algunos navegadores type=time envía HH:MM:SS en vez de HH:MM.
        for hora in ("12:00", "12:00:00", "12:00:00.000"):
            datos = self.example()
            datos["hora"] = hora
            result = self.call(self.paciente, "POST", "/api/tratamientos", datos)
            self.assertEqual(result.status, 201, f"No se guardó {hora}: {result.result}")
            self.assertEqual(result.result["tratamiento"]["hora"], "12:00")
            self.assertTrue(result.result["tratamiento"]["tomas"])
        # Cualquier hora realmente inválida sigue rechazándose.
        datos = self.example()
        datos["hora"] = "25:80:00"
        bad = self.call(self.paciente, "POST", "/api/tratamientos", datos)
        self.assertEqual(bad.status, 400)

    def test_medico_modifica_hora_con_segundos(self):
        original = self.call(self.medico, "POST", "/api/tratamientos", self.example())
        self.assertEqual(original.status, 201)
        tid = original.result["tratamiento"]["id"]
        datos = self.example()
        datos["hora"] = "12:00:00"
        datos["motivo_modificacion"] = "Ajuste ficticio del horario"
        actualizado = self.call(self.medico, "PUT", f"/api/tratamientos/{tid}", datos)
        self.assertEqual(actualizado.status, 200, actualizado.result)
        self.assertEqual(actualizado.result["tratamiento"]["hora"], "12:00")

    def test_role_change_limits(self):
        attempt=self.call(self.paciente,"POST","/api/rol",{"rol":"medico","contrasena":"x"})
        self.assertEqual(attempt.status,400)
        weak=self.call(self.medico,"POST","/api/rol",{"rol":"ambos","contrasena":"incorrecta"})
        self.assertEqual(weak.status,403)
        okay=self.call(self.medico,"POST","/api/rol",{"rol":"ambos","contrasena":self.password,"dni_paciente":"10000001"})
        self.assertEqual(okay.status,200)
        self.assertEqual(okay.result["usuario"]["rol"],"ambos")
        self.assertEqual(okay.result["usuario"]["dni_paciente"],"10000001")
        again=self.call(self.medico,"POST","/api/rol",{"rol":"medico"})
        self.assertEqual(again.status,400)


if __name__=="__main__":
    unittest.main()
