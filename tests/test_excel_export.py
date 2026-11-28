"""Pruebas del exportador XLSX sin depender de datos reales."""
import io
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import excel_export


class ExcelExportTest(unittest.TestCase):
    def sample_data(self):
        return {
            "generated": "2026-11-28T12:00:00-05:00",
            "users": [{"id": 1, "nombres": "Paciente", "apellidos": "Demo", "rol": "paciente",
                       "paciente_vinculado": "", "puesto": ""}],
            "medicines": [{"codigo": 1, "nombre": "Producto de prueba", "categoria": "General",
                           "establecimiento": "Demo", "stock": 8, "estado": "Crítico"}],
            "visits": [{"vista": "inicio", "visitas": 4, "usuarios": 1}],
            "monthly_visits": [{"periodo": "2026-11", "visitas": 4}],
            "treatments": [{"id": 1, "paciente": "Paciente Demo", "registrado_por": "Médico Demo",
                            "medico": "Médico Demo", "nombre": "Medicamento de prueba",
                            "forma": "Tableta", "dosis": "1 unidad", "inicio": "2026-11-28",
                            "fin": "2026-11-29", "frecuencia": 1, "programadas": 2,
                            "confirmadas": 1, "pendientes": 1, "seguimiento": "Pendiente",
                            "motivo": "Prueba académica", "indicaciones": "Solo demostración",
                            "fechas_programadas": "2026-11-28T08:00:00 | 2026-11-29T08:00:00",
                            "detalle_confirmaciones": "2026-11-28T08:00:00 -> 2026-11-28T08:10:00Z"}],
            "doctor_activity": [{"nombre": "Médico Demo", "registros": 1, "asignados": 1,
                                 "pacientes": 1, "modificaciones": 0}],
            "assignments": [{"medico": "Médico Demo", "paciente": "Paciente Demo",
                             "registros": 1, "medicamentos": 1}],
            "role_rows": {"paciente": 1},
            "kpis": {"total_users": 1, "patients": 1, "caregivers": 0, "doctors": 0,
                     "total_medicines": 1, "available": 0, "critical": 1, "out_of_stock": 0,
                     "total_treatments": 1, "total_takes": 2, "confirmed_takes": 1,
                     "pending_takes": 1, "page_visits": 4, "accesses": 0, "users_logged": 0,
                     "assignments": 1},
        }

    def test_generates_valid_xlsx_package_and_expected_sheets(self):
        payload = excel_export.build_workbook(self.sample_data())
        self.assertTrue(payload.startswith(b"PK"))
        with ZipFile(io.BytesIO(payload)) as archive:
            self.assertIsNone(archive.testzip())
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            names = [s.attrib["name"] for s in workbook.findall("x:sheets/x:sheet", ns)]
            self.assertEqual(names, ["Dashboard", "Usuarios", "Tratamientos y tomas",
                                     "Medicamentos", "Estadísticas", "Reportes"])
            self.assertEqual(len([n for n in archive.namelist() if n.startswith("xl/charts/chart")]), 5)
            self.assertIn("No se exportan DNI", archive.read("xl/worksheets/sheet2.xml").decode("utf-8"))

    def test_treatment_sheet_has_no_full_identifier_column(self):
        payload = excel_export.build_workbook(self.sample_data())
        with ZipFile(io.BytesIO(payload)) as archive:
            content = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
            self.assertIn("Tratamientos y tomas", content)
            self.assertNotIn("dni", content.lower())
            for name in archive.namelist():
                if name.endswith(".xml") or name.endswith(".rels"):
                    ET.fromstring(archive.read(name))


if __name__ == "__main__":
    unittest.main()
