// Tests de filtros de disponibilidad con Node.js (sin paquetes externos).
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const js = fs.readFileSync(path.join(root, "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
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
const snippets = between("  function determinarEstado(stock)", "  function llenarSelect") + "\n" +
  between("  // El mismo criterio se usa", "  function badgeEstado") +
  "\nmodule.exports={determinarEstado,cumpleFiltroStock,registrosFiltrados};";
vm.runInNewContext(snippets, context, {timeout:1000});
const {determinarEstado,cumpleFiltroStock,registrosFiltrados} = context.module.exports;
assert.equal(determinarEstado(0),"agotado");
assert.equal(determinarEstado(1),"critico");
assert.equal(determinarEstado(10),"critico");
assert.equal(determinarEstado(11),"disponible");
assert.equal(registrosFiltrados("","","","").length,4);
assert.equal(registrosFiltrados("","","","con-stock").length,3);
assert.equal(registrosFiltrados("","","","disponible").length,2);
assert.equal(registrosFiltrados("","","","critico").length,1);
assert.equal(registrosFiltrados("","","","agotado").length,1);
assert.equal(registrosFiltrados("Analgésicos","","","con-stock")[0].id,"MED-002");
assert.equal(registrosFiltrados("","Centro Norte","","agotado")[0].id,"MED-001");
assert.equal(registrosFiltrados("","","paracetamol","agotado")[0].id,"MED-001");
assert.equal(registrosFiltrados("Suplementos","Centro Sur","cal","con-stock")[0].id,"MED-004");
assert.equal(registrosFiltrados("Analgésicos","Centro Sur","","agotado").length,0);
assert.equal(cumpleFiltroStock(records[0],"con-stock"),false);
for (const id of ["estado-consulta","estado-dashboard","estado-inventario","limpiar-inventario","total-filtrado-dashboard"]) {
  assert.ok(html.includes('id="'+id+'"'),"Falta el control "+id);
}
for (const value of ["con-stock","disponible","critico","agotado"]) {
  assert.equal((html.match(new RegExp('value="'+value+'"', "g"))||[]).length,3);
  assert.ok(html.includes('data-stock-quick="'+value+'"'),"Falta acceso desde Inicio: "+value);
}
console.log("✓ Filtros de stock y combinaciones verificados");
