// Tests de filtros de disponibilidad e inventario con Node.js (sin paquetes externos).
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const js = fs.readFileSync(path.join(root, "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "styles.css"), "utf8");

// Evita que un error de sintaxis desactive silenciosamente todos los eventos del frontend.
new vm.Script(js, {filename: "app.js"});
assert.ok(html.includes('<form id="form-login" method="post"'), "El login no debe enviar credenciales por GET");
assert.ok(html.includes('<form id="form-registro" method="post"'), "El registro no debe enviar credenciales por GET");

function between(start, end) {
  const a = js.indexOf(start), b = js.indexOf(end, a);
  assert.ok(a >= 0 && b > a, "No se encontró el código: " + start);
  return js.slice(a, b);
}
const records = [
  {id:"MED-001", nombre:"Paracetamol", categoria:"Analgésicos", establecimiento:"Centro Norte", stock:0},
  {id:"MED-002", nombre:"Ibuprofeno", categoria:"Analgésicos", establecimiento:"Centro Sur", stock:2},
  {id:"MED-003", nombre:"Vitamina C", categoria:"Suplementos", establecimiento:"Centro Norte", stock:11},
  {id:"MED-004", nombre:"Calcio", categoria:"Suplementos", establecimiento:"Centro Sur", stock:45}
];
const context = {inventario:records, module:{exports:{}}};
const snippets =
  between("  function determinarEstado(stock)", "  function llenarSelect") + "\n" +
  between("  function registrosFiltrados(", "  function badgeEstado") +
  "\nmodule.exports={determinarEstado,cumpleFiltroStock,registrosFiltrados};";
vm.runInNewContext(snippets, context, {timeout:1000});
const {determinarEstado,cumpleFiltroStock,registrosFiltrados} = context.module.exports;

assert.equal(determinarEstado(0),"agotado");
assert.equal(determinarEstado(1),"critico");
assert.equal(determinarEstado(10),"critico");
assert.equal(determinarEstado(11),"disponible");
assert.equal(registrosFiltrados("","","","").length,4);
assert.equal(registrosFiltrados("","","","disponible").length,2);
assert.equal(registrosFiltrados("","","","critico").length,1);
assert.equal(registrosFiltrados("","","","agotado").length,1);
assert.equal(registrosFiltrados("Analgésicos","","","critico")[0].id,"MED-002");
assert.equal(registrosFiltrados("","Centro Norte","","agotado")[0].id,"MED-001");
assert.equal(registrosFiltrados("","","paracetamol","agotado")[0].id,"MED-001");
assert.equal(registrosFiltrados("Suplementos","Centro Sur","cal","disponible")[0].id,"MED-004");
assert.equal(registrosFiltrados("Analgésicos","Centro Sur","","agotado").length,0);
assert.equal(cumpleFiltroStock(records[0],""),true);
assert.equal(cumpleFiltroStock(records[0],"agotado"),true);
assert.equal(cumpleFiltroStock(records[0],"disponible"),false);

for (const id of ["estado-consulta","estado-inventario","buscar-inventario","limpiar-inventario","opcion-daltonismo"]) {
  assert.ok(html.includes('id="'+id+'"'),"Falta el control "+id);
}
for (const value of ["disponible","critico","agotado"]) {
  assert.equal((html.match(new RegExp('value="'+value+'"',"g"))||[]).length,2,"El estado debe estar en los dos filtros: "+value);
}
assert.ok(js.includes("hablar(texto)"),"Las notificaciones deben activar las confirmaciones habladas");
assert.ok(js.includes("colorblind-safe"),"Falta activar la paleta apta para daltonismo");
assert.ok(css.includes("body.high-contrast"),"Faltan estilos de alto contraste");
assert.ok(css.includes("body.colorblind-safe"),"Faltan estilos para daltonismo");

console.log("✓ Filtros de stock, accesibilidad visual y confirmaciones habladas verificados");
