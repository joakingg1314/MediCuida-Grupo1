"""Comprobación de datos ficticios iniciales, sin usar información médica real."""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class CatalogoTest(unittest.TestCase):
    def test_catalogo_de_150(self):
        records=json.loads((ROOT/"backend"/"medicamentos_iniciales.json").read_text(encoding="utf-8"))
        self.assertEqual(len(records),150)
        self.assertEqual([r["codigo"] for r in records],list(range(1,151)))
        self.assertEqual(len(set(r["nombre"].casefold() for r in records)),150)
        self.assertGreaterEqual(len(set(r["categoria"] for r in records)),12)
        self.assertGreaterEqual(len(set(r["establecimiento"] for r in records)),8)
        self.assertTrue(any(r["stock"]==0 for r in records))
        self.assertTrue(any(0<r["stock"]<=10 for r in records))
        self.assertTrue(any(r["stock"]>10 for r in records))
        self.assertTrue(all(type(r["stock"]) is int and r["stock"]>=0 for r in records))


if __name__=="__main__":
    unittest.main()
