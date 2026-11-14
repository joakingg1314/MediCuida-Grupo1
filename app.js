/* MediCuida · Grupo 1 · Frontend conectado a API Python con SQLite y copia de respaldo en PostgreSQL.
   Inventario FICTICIO. NO es un sistema clínico ni oficial del MINSA. */
'use strict';

(() => {
  const TREAT_KEY = 'medicuida_tratamientos_demo_v1';
  const PREF_KEY = 'medicuida_preferencias_demo_v1';
  const VISTAS = ['inicio','consulta','dashboard','inventario','tratamientos','historial','ayuda','perfil'];
  const VISTAS_NO_MEDICO = ['inicio','consulta','tratamientos','historial','ayuda','perfil'];
  let rolActual = null;
  const puedeAbrirVista = nombre => VISTAS.includes(nombre) && (rolActual === 'medico' || VISTAS_NO_MEDICO.includes(nombre));
  function actualizarNavegacionPorRol() {
    const medico = rolActual === 'medico';
    $$('[data-medico-only]').forEach(control => {
      control.hidden = !medico;
      control.disabled = !medico;
      if (!medico) control.setAttribute('aria-hidden', 'true');
      else control.removeAttribute('aria-hidden');
    });
    $$('[data-paciente-cuidador]').forEach(control => {
      control.hidden = medico;
      control.disabled = medico;
    });
    if (!$('#aplicacion').hidden) {
      const visible = $$('.view').find(view => !view.hidden);
      const nombre = visible?.id.replace('vista-', '');
      if (nombre && !puedeAbrirVista(nombre)) mostrarVista('inicio');
    }
  }
  const ESTADOS = {
    disponible: { texto: 'Disponible', clase: 'available', color: '#199769' },
    critico: { texto: 'Stock crítico', clase: 'critical', color: '#e0a12f' },
    agotado: { texto: 'Sin stock', clase: 'unavailable', color: '#ca5c62' }
  };

  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const create = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  };
  const storageRead = (key, fallback) => {
    try { const content = localStorage.getItem(key); return content ? JSON.parse(content) : fallback; }
    catch { return fallback; }
  };
  const storageWrite = (key, value) => {
    try { localStorage.setItem(key, JSON.stringify(value)); return true; }
    catch { aviso('El navegador no permitió guardar los datos locales.'); return false; }
  };
  let inventario = [];
  async function api(path, options = {}) {
    let response;
    try {
      response = await fetch(path, {
        ...options,
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
      });
    } catch {
      throw new Error('No hay conexión con el servidor. Abre INICIAR_WINDOWS.bat y utiliza http://127.0.0.1:8765');
    }
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || `Error del servidor (${response.status}).`);
    return result;
  }
  const fechaLocal = date => new Intl.DateTimeFormat('es-PE', { day: '2-digit', month: 'short', year: 'numeric', hour:'2-digit', minute:'2-digit' }).format(new Date(date));
  const identificador = () => `${Date.now()}-${Math.random().toString(36).slice(2,9)}`;
  let tratamientos = storageRead(TREAT_KEY, []);
  if (!Array.isArray(tratamientos)) tratamientos = [];
  let preferencias = storageRead(PREF_KEY, { texto:false, contraste:false, voz:false });
  if (!preferencias || typeof preferencias !== 'object') preferencias = { texto:false, contraste:false, voz:false };
  let toastTimer;

  function aviso(texto) {
    const toast = $('#toast');
    toast.textContent = texto;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 4300);
  }
  function hablar(texto) {
    if (!preferencias.voz || !('speechSynthesis' in window)) return;
    try {
      window.speechSynthesis.cancel();
      const frase = new SpeechSynthesisUtterance(texto);
      frase.lang = 'es-PE'; frase.rate = 0.92;
      window.speechSynthesis.speak(frase);
    } catch { /* Síntesis no soportada: se mantiene el aviso visual. */ }
  }

  // ------------------------ REGISTRO E INICIO DE SESIÓN ------------------------
  function actualizarDatosUsuario(usuario) {
    usuarioActual = usuario || null;
    rolActual = usuario && ['paciente','cuidador','ambos','medico'].includes(usuario.rol) ? usuario.rol : null;
    actualizarNavegacionPorRol();
    const nombreCompleto = usuario ? `${usuario.nombres} ${usuario.apellidos}`.trim() : 'Usuario';
    $('#usuario-chip').textContent = nombreCompleto || 'Usuario';
    $('#perfil-nombres').textContent = usuario?.nombres || '-';
    $('#perfil-apellidos').textContent = usuario?.apellidos || '-';
    $('#perfil-dni').textContent = usuario?.dni || '-';
    $('#perfil-correo').textContent = usuario?.correo || '-';
    const nombresRoles = { paciente:'Paciente', cuidador:'Cuidador', ambos:'Paciente y Cuidador', medico:'Médico' };
    $('#perfil-rol').textContent = nombresRoles[usuario?.rol] || '-';
    $('#perfil-cuidador').hidden = usuario?.rol !== 'cuidador';
    $('#perfil-medico').hidden = usuario?.rol !== 'medico';
    $('#perfil-dni-paciente').textContent = usuario?.dni_paciente || '-';
    $('#perfil-ruc').textContent = usuario?.ruc || '-';
    $('#perfil-puesto').textContent = usuario?.puesto || '-';
    $('#perfil-cuidador').hidden = !['cuidador','ambos'].includes(usuario?.rol);
    actualizarFormulariosPorRol();
  }
  function alternarAuth(modo) {
    const esLogin = modo === 'login';
    $('#panel-login').hidden = !esLogin;
    $('#panel-registro').hidden = esLogin;
    $('#tab-login').classList.toggle('active', esLogin);
    $('#tab-registro').classList.toggle('active', !esLogin);
    $('#tab-login').setAttribute('aria-selected', String(esLogin));
    $('#tab-registro').setAttribute('aria-selected', String(!esLogin));
    (esLogin ? $('#dni-login') : $('#reg-nombres')).focus();
  }
  function actualizarCamposRol() {
    const rol = $('#reg-rol').value;
    const cuidador = rol === 'cuidador';
    const medico = rol === 'medico';
    $('#reg-campos-cuidador').hidden = !cuidador;
    $('#reg-campos-medico').hidden = !medico;
    ['#reg-dni-paciente'].forEach(id => {
      $(id).disabled = !cuidador;
      $(id).required = cuidador;
    });
    ['#reg-ruc','#reg-puesto'].forEach(id => {
      $(id).disabled = !medico;
      $(id).required = medico;
    });
  }
  $('#reg-rol').addEventListener('change', actualizarCamposRol);
  function mostrarAplicacion() {
    $('#pantalla-login').hidden = true;
    $('#aplicacion').hidden = false;
    mostrarVista('inicio');
  }
  function mostrarLogin() {
    $('#aplicacion').hidden = true;
    $('#pantalla-login').hidden = false;
    $('#form-login').reset();
    $('#form-registro').reset();
    actualizarCamposRol();
    $('#error-login').hidden = true;
    $('#error-registro').hidden = true;
    $('#ok-registro').textContent = '';
    alternarAuth('login');
    window.scrollTo(0,0);
  }
  $$('.auth-tab').forEach(btn => btn.addEventListener('click', () => alternarAuth(btn.dataset.auth)));
  $('#form-login').addEventListener('submit', async event => {
    event.preventDefault();
    const error = $('#error-login');
    const boton = $('#form-login button[type="submit"]');
    boton.disabled = true;
    error.hidden = true;
    try {
      const respuesta = await api('/api/login', {
        method: 'POST',
        body: JSON.stringify({ dni: $('#dni-login').value.trim(), contrasena: $('#contrasena-login').value })
      });
      actualizarDatosUsuario(respuesta.usuario);
      await cargarInventario();
      $('#contrasena-login').value = '';
      mostrarAplicacion();
      aviso('Bienvenido a MediCuida. Inventario cargado correctamente.');
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
      $('#contrasena-login').value = '';
      $('#contrasena-login').focus();
    } finally {
      boton.disabled = false;
    }
  });
  $('#form-registro').addEventListener('submit', async event => {
    event.preventDefault();
    const error = $('#error-registro');
    const boton = $('#form-registro button[type="submit"]');
    boton.disabled = true;
    error.hidden = true;
    try {
      const respuesta = await api('/api/register', {
        method: 'POST',
        body: JSON.stringify({
          rol: $('#reg-rol').value,
          nombres: $('#reg-nombres').value.trim(),
          apellidos: $('#reg-apellidos').value.trim(),
          dni: $('#reg-dni').value.trim(),
          correo: $('#reg-email').value.trim(),
          dni_paciente: $('#reg-rol').value === 'cuidador' ? $('#reg-dni-paciente').value.trim() : null,
          ruc: $('#reg-rol').value === 'medico' ? $('#reg-ruc').value.trim() : null,
          puesto: $('#reg-rol').value === 'medico' ? $('#reg-puesto').value.trim() : null,
          contrasena: $('#reg-clave').value
        })
      });
      $('#dni-login').value = $('#reg-dni').value.trim();
      $('#contrasena-login').value = '';
      $('#form-registro').reset();
      actualizarCamposRol();
      alternarAuth('login');
      aviso(respuesta.mensaje || 'Registro completado. Ahora inicia sesión.');
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    } finally {
      boton.disabled = false;
    }
  });
  [['#ver-clave','#contrasena-login'],['#ver-clave-reg','#reg-clave']].forEach(([botonId,inputId]) => {
    $(botonId).addEventListener('click', () => {
      const input = $(inputId);
      const mostrar = input.type === 'password';
      input.type = mostrar ? 'text' : 'password';
      $(botonId).textContent = mostrar ? 'Ocultar' : 'Ver';
      $(botonId).setAttribute('aria-label', mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña');
    });
  });
  $('#cerrar-sesion').addEventListener('click', async () => {
    try { await api('/api/logout', { method: 'POST' }); }
    catch { aviso('No se pudo contactar el servidor; reinicia la página si es necesario.'); }
    inventario = [];
    actualizarDatosUsuario(null);
    mostrarLogin();
  });

  // ------------------------ NAVEGACIÓN ------------------------
  function mostrarVista(nombre) {
    if ($('#aplicacion').hidden || !VISTAS.includes(nombre)) return;
    if (!puedeAbrirVista(nombre)) {
      aviso('Tu rol no tiene acceso a esta sección.');
      return;
    }
    $$('.view').forEach(section => { section.hidden = section.id !== `vista-${nombre}`; });
    $$('.nav-link').forEach(button => {
      const activo = !button.hidden && button.dataset.view === nombre;
      button.classList.toggle('active', activo);
      if (activo) button.setAttribute('aria-current','page');
      else button.removeAttribute('aria-current');
    });
    if (nombre === 'consulta') mostrarResultados();
    if (nombre === 'dashboard' && rolActual === 'medico') mostrarDashboard();
    if (nombre === 'inventario' && rolActual === 'medico') mostrarInventario();
    if (nombre === 'tratamientos') mostrarTratamientos();
    if (nombre === 'historial') mostrarHistorial();
    window.scrollTo({top:0, behavior:'instant'});
    const heading = $(`#vista-${nombre} h1`);
    if (heading) { heading.tabIndex = -1; heading.focus({preventScroll:true}); }
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-view]');
    if (button) mostrarVista(button.dataset.view);
  });

  // ------------------------ INVENTARIO FICTICIO ------------------------
  function determinarEstado(stock) {
    if (stock === 0) return 'agotado';
    if (stock <= 10) return 'critico';
    return 'disponible';
  }
  function llenarSelect(id, valores) {
    const select = $(id);
    const seleccionado = select.value;
    select.querySelectorAll('option:not([value=""])').forEach(opt => opt.remove());
    [...new Set(valores)].sort((a,b) => a.localeCompare(b,'es')).forEach(text => {
      const option = document.createElement('option'); option.value = text; option.textContent = text;
      select.append(option);
    });
    select.value = [...select.options].some(opt => opt.value === seleccionado) ? seleccionado : '';
  }
  function actualizarOpcionesInventario() {
    ['#categoria-consulta','#categoria-dashboard'].forEach(id => llenarSelect(id,inventario.map(r => r.categoria)));
    ['#establecimiento-consulta','#establecimiento-dashboard'].forEach(id => llenarSelect(id,inventario.map(r => r.establecimiento)));
    [['#lista-categorias', inventario.map(r => r.categoria)],
     ['#lista-establecimientos', inventario.map(r => r.establecimiento)]].forEach(([id, valores]) => {
       const datalist = $(id);
       datalist.replaceChildren();
       [...new Set(valores)].sort((a,b) => a.localeCompare(b,'es')).forEach(value => {
         const option = document.createElement('option'); option.value = value; datalist.append(option);
       });
     });
  }
  async function cargarInventario() {
    const datos = await api('/api/medicamentos');
    inventario = datos.medicamentos;
    actualizarOpcionesInventario();
    mostrarResultados();
    if (rolActual === 'medico') {
      mostrarDashboard();
      mostrarInventario();
    }
  }
  // El mismo criterio se usa en todas las pantallas.
  // 'Con stock' incluye también stock crítico; 'Disponible' significa más de 10.
  function cumpleFiltroStock(item, estado = '') {
    if (!estado) return true;
    if (estado === 'con-stock') return item.stock > 0;
    return determinarEstado(item.stock) === estado;
  }
  function registrosFiltrados(categoria, establecimiento, busqueda = '', estado = '') {
    const term = busqueda.trim().toLocaleLowerCase('es');
    return inventario.filter(item =>
      (!categoria || item.categoria === categoria) &&
      (!establecimiento || item.establecimiento === establecimiento) &&
      cumpleFiltroStock(item, estado) &&
      (!term || `${item.id} ${item.nombre} ${item.categoria} ${item.establecimiento}`.toLocaleLowerCase('es').includes(term))
    );
  }
  function badgeEstado(estado) {
    return create('span', `status-badge ${ESTADOS[estado].clase}`, ESTADOS[estado].texto);
  }
  function mostrarResultados() {
    const datos = registrosFiltrados($('#categoria-consulta').value,$('#establecimiento-consulta').value,$('#buscar-stock').value,$('#estado-consulta').value);
    $('#total-resultados').textContent = `${datos.length} ${datos.length === 1 ? 'registro encontrado' : 'registros encontrados'} · datos simulados`;
    const grid = $('#resultados-stock');
    grid.replaceChildren();
    if (!datos.length) { grid.append(create('p','empty-state','No se encontraron medicamentos con esos filtros.')); return; }
    const fragmento = document.createDocumentFragment();
    datos.forEach(item => {
      const estado = determinarEstado(item.stock);
      const tarjeta = create('article','stock-card');
      const top = create('div','stock-card-top');
      top.append(create('span','stock-symbol','✚'), badgeEstado(estado));
      tarjeta.append(top, create('h3','',item.nombre),create('p','code',`Código: ${item.id}`),create('p','category',item.categoria));
      const datosTarjeta = create('div','stock-meta');
      [['Establecimiento',item.establecimiento],['Stock de ejemplo',`${item.stock} unidades`]].forEach(([nombre,valor]) => {
        const fila = create('div');fila.append(create('span','',nombre),create('strong','',valor));datosTarjeta.append(fila);
      });
      tarjeta.append(datosTarjeta); fragmento.append(tarjeta);
    });
    grid.append(fragmento);
  }
  $('#form-consulta').addEventListener('submit', event => {event.preventDefault();mostrarResultados();});
  ['#categoria-consulta','#establecimiento-consulta','#estado-consulta'].forEach(id => $(id).addEventListener('change',mostrarResultados));
  // Accesos rápidos de stock desde la página Inicio.
  $('[data-stock-quick]').forEach(button => button.addEventListener('click', () => {
    $('#estado-consulta').value = button.dataset.stockQuick;
    $('#categoria-consulta').value = '';
    $('#establecimiento-consulta').value = '';
    $('#buscar-stock').value = '';
    mostrarVista('consulta');
  }));
  $('#buscar-stock').addEventListener('input', mostrarResultados);
  $('#limpiar-consulta').addEventListener('click', () => {
    $('#buscar-stock').value = '';
    $('#categoria-consulta').value = '';
    $('#establecimiento-consulta').value = '';
    $('#estado-consulta').value = '';
    mostrarResultados();
  });

  // ------------------------ INDICADORES Y GRÁFICOS ------------------------
  function mostrarDashboard() {
    const registros = registrosFiltrados($('#categoria-dashboard').value,$('#establecimiento-dashboard').value,'',$('#estado-dashboard').value);
    const total = registros.length;
    $('#total-filtrado-dashboard').textContent = $('#estado-dashboard').value || $('#categoria-dashboard').value || $('#establecimiento-dashboard').value
      ? `Mostrando ${total} de ${inventario.length} registros del inventario según los filtros seleccionados.`
      : `Mostrando todo el inventario: ${total} registros de demostración.`;
    const disponibles = registros.filter(item => item.stock > 0).length;
    const criticos = registros.filter(item => determinarEstado(item.stock) === 'critico').length;
    const porcentaje = total ? (disponibles / total * 100).toFixed(1) : '0.0';
    $('#metric-total').textContent = String(total);
    $('#metric-disponibles').textContent = String(disponibles);
    $('#metric-criticos').textContent = String(criticos);
    $('#metric-porcentaje').textContent = `${porcentaje}%`;
    $('#total-dona').textContent = String(total);
    graficoCategorias(registros);
    graficoDistribucion(registros);
    graficoEvolucion(registros);
  }
  function graficoCategorias(datos) {
    const destino = $('#grafico-categorias'); destino.replaceChildren();
    const counts = new Map();
    datos.forEach(item => counts.set(item.categoria,(counts.get(item.categoria)||0)+1));
    const grupos = [...counts.entries()].sort((a,b) => b[1]-a[1]);
    if (!grupos.length) {destino.append(create('p','muted','Sin datos en esta selección.'));return;}
    const max = Math.max(...grupos.map(p => p[1]));
    grupos.forEach(([categoria,numero]) => {
      const fila = create('div','bar-row');
      const carril = create('div','bar-track');
      const barra = create('div','bar-fill'); barra.style.width = `${numero/max * 100}%`;
      carril.append(barra);
      fila.append(create('span','bar-label',categoria),carril,create('span','bar-value',numero));
      destino.append(fila);
    });
    destino.setAttribute('aria-label',grupos.map(([n,c])=>`${n}: ${c}`).join('; '));
  }
  function graficoDistribucion(datos) {
    const cantidad = {
      disponible: datos.filter(r => determinarEstado(r.stock) === 'disponible').length,
      critico: datos.filter(r => determinarEstado(r.stock) === 'critico').length,
      agotado: datos.filter(r => determinarEstado(r.stock) === 'agotado').length
    };
    const total = datos.length;
    const grupos = ['disponible','critico','agotado'];
    let posicion = 0;
    const segmentos = grupos.map(tipo => {
      const desde = posicion;
      posicion += total ? cantidad[tipo]/total*100 : 0;
      return `${ESTADOS[tipo].color} ${desde}% ${posicion}%`;
    });
    $('#grafico-dona').style.background = total ? `conic-gradient(${segmentos.join(',')})` : '#e7eef4';
    const leyenda = $('#leyenda-dona');leyenda.replaceChildren();
    grupos.forEach(tipo => {
      const fila = create('div','legend-row');
      const punto = create('span','legend-dot'); punto.style.backgroundColor = ESTADOS[tipo].color;
      fila.append(punto,create('span','',`${ESTADOS[tipo].texto}: ${cantidad[tipo]}`));leyenda.append(fila);
    });
    $('#grafico-dona').setAttribute('aria-label',grupos.map(t => `${ESTADOS[t].texto}: ${cantidad[t]}`).join('; '));
  }
  function datoFicticioHistorico(item, indice, periodo) {
    // Período 5 es el stock ficticio actual; otros períodos son variaciones simuladas.
    const desplazamiento = [-9,5,-3,8,-5,0][periodo];
    const multiplicador = 1 + (indice % 3);
    return Math.max(0,item.stock + desplazamiento*multiplicador);
  }
  function graficoEvolucion(datos) {
    const meses = ['Jun','Jul','Ago','Sep','Oct','Nov'];
    const totales = meses.map((_,periodo) => datos.reduce((sum,item) =>
      sum+datoFicticioHistorico(item,inventario.indexOf(item),periodo),0));
    const svg = $('#grafico-evolucion');svg.replaceChildren();
    const NS = 'http://www.w3.org/2000/svg';
    function svgEl(tag, atributos={}, texto) {
      const el = document.createElementNS(NS,tag);
      for(const [k,v] of Object.entries(atributos)) el.setAttribute(k,String(v));
      if(texto !== undefined) el.textContent=String(texto);
      svg.append(el); return el;
    }
    const izq=62,der=735,arriba=18,abajo=213,ancho=der-izq,alto=abajo-arriba;
    const ymax = Math.max(10,Math.ceil(Math.max(...totales)*1.15/10)*10);
    const x=i=>izq+i*ancho/(meses.length-1);
    const y=n=>abajo-n/ymax*alto;
    [0,.25,.5,.75,1].forEach(fraccion=>{
      const yy=y(ymax*fraccion);
      svgEl('line',{x1:izq,x2:der,y1:yy,y2:yy,class:'chart-gridline'});
      svgEl('text',{x:izq-12,y:yy+5,'text-anchor':'end',class:'chart-label'},Math.round(ymax*fraccion));
    });
    meses.forEach((mes,i)=> svgEl('text',{x:x(i),y:244,'text-anchor':'middle',class:'chart-label'},mes));
    const pts = totales.map((n,i)=>`${x(i)},${y(n)}`);
    svgEl('polygon',{points:`${izq},${abajo} ${pts.join(' ')} ${der},${abajo}`,class:'chart-area'});
    svgEl('polyline',{points:pts.join(' '),class:'chart-line'});
    totales.forEach((n,i)=>svgEl('circle',{cx:x(i),cy:y(n),r:5,class:'chart-point'}));
    const titulo = document.createElementNS(NS,'title');
    titulo.textContent = meses.map((m,i)=>`${m}: ${totales[i]} unidades ficticias`).join('; ');
    svg.prepend(titulo);
    $('#resumen-evolucion').textContent = meses.map((m,i)=>`${m}: ${totales[i]}`).join('  ·  ')+' unidades simuladas';
  }
  ['#categoria-dashboard','#establecimiento-dashboard','#estado-dashboard'].forEach(id => $(id).addEventListener('change',mostrarDashboard));
  $('#reiniciar-dashboard').addEventListener('click', () => {
    $('#categoria-dashboard').value='';$('#establecimiento-dashboard').value='';$('#estado-dashboard').value='';mostrarDashboard();
  });

  // ------------------------ CRUD DE INVENTARIO · API con respaldo PostgreSQL ------------------------
  function resetFormularioInventario() {
    $('#form-inventario').reset();
    $('#med-id').value = '';
    $('#med-form-title').textContent = 'Agregar medicamento';
    $('#med-guardar').textContent = 'Agregar medicamento';
    $('#med-cancelar').hidden = true;
    $('#med-feedback').textContent = '';
  }
  function mostrarInventario() {
    const tbody = $('#tabla-inventario');
    tbody.replaceChildren();
    const filtrados = registrosFiltrados('', '', '', $('#estado-inventario').value);
    $('#inventario-total').textContent = `Mostrando ${filtrados.length} de ${inventario.length} ${inventario.length === 1 ? 'medicamento registrado' : 'medicamentos registrados'} (con respaldo en PostgreSQL)`;
    if (!filtrados.length) {
      const fila = document.createElement('tr');
      const celda = create('td', '', inventario.length
        ? 'No hay medicamentos con este estado de stock. Prueba con otro filtro.'
        : 'No hay medicamentos. Agrega uno con el formulario.');
      celda.colSpan = 7;
      fila.append(celda); tbody.append(fila);
      return;
    }
    filtrados.forEach(med => {
      const fila = document.createElement('tr');
      [med.id, med.nombre, med.categoria, med.establecimiento, String(med.stock)].forEach(value => fila.append(create('td','',value)));
      const estado = create('td');
      estado.append(badgeEstado(determinarEstado(med.stock)));
      fila.append(estado);
      const acciones = create('td', 'inventory-actions');
      const editar = create('button', 'btn btn-soft btn-sm', 'Editar');
      editar.type = 'button';
      editar.setAttribute('aria-label', `Editar ${med.nombre} (${med.id})`);
      editar.addEventListener('click', () => {
        $('#med-id').value = med.id;
        $('#med-nombre').value = med.nombre;
        $('#med-categoria').value = med.categoria;
        $('#med-establecimiento').value = med.establecimiento;
        $('#med-stock').value = String(med.stock);
        $('#med-form-title').textContent = `Editar ${med.id}`;
        $('#med-guardar').textContent = 'Guardar cambios';
        $('#med-cancelar').hidden = false;
        $('#med-feedback').textContent = `Editando ${med.id}.`;
        $('#med-nombre').focus();
        $('#med-nombre').scrollIntoView({behavior:'smooth',block:'center'});
      });
      const eliminar = create('button', 'btn btn-danger btn-sm', 'Eliminar');
      eliminar.type = 'button';
      eliminar.setAttribute('aria-label', `Eliminar ${med.nombre} (${med.id})`);
      eliminar.addEventListener('click', async () => {
        if (!window.confirm(`¿Eliminar permanentemente ${med.nombre} (${med.id}) del inventario?`)) return;
        eliminar.disabled = true;
        try {
          await api(`/api/medicamentos/${encodeURIComponent(med.id)}`, {method:'DELETE'});
          if ($('#med-id').value === med.id) resetFormularioInventario();
          await cargarInventario();
          aviso(`Medicamento ${med.id} eliminado del inventario.`);
        } catch(err) {
          aviso(`No se pudo eliminar: ${err.message}`);
          eliminar.disabled = false;
        }
      });
      acciones.append(editar, eliminar); fila.append(acciones);
      tbody.append(fila);
    });
  }
  $('#med-cancelar').addEventListener('click',resetFormularioInventario);
  $('#estado-inventario').addEventListener('change',mostrarInventario);
  $('#limpiar-inventario').addEventListener('click', () => {
    $('#estado-inventario').value = '';
    mostrarInventario();
  });
  $('#actualizar-inventario').addEventListener('click',async () => {
    try { await cargarInventario(); aviso('Inventario actualizado desde el servidor.'); }
    catch(err) { aviso(err.message); }
  });
  $('#form-inventario').addEventListener('submit',async event => {
    event.preventDefault();
    const id = $('#med-id').value;
    const data = {
      nombre: $('#med-nombre').value.trim(),
      categoria: $('#med-categoria').value.trim(),
      establecimiento: $('#med-establecimiento').value.trim(),
      stock: Number($('#med-stock').value)
    };
    const feedback = $('#med-feedback');
    const boton = $('#med-guardar');
    boton.disabled = true;
    feedback.textContent = 'Guardando en la base de datos…';
    try {
      await api(id ? `/api/medicamentos/${encodeURIComponent(id)}` : '/api/medicamentos', {
        method: id ? 'PUT' : 'POST',
        body: JSON.stringify(data)
      });
      await cargarInventario();
      resetFormularioInventario();
      aviso(id ? 'Medicamento actualizado correctamente.' : 'Medicamento agregado correctamente.');
    } catch(err) { feedback.textContent = err.message; }
    finally { boton.disabled = false; }
  });

  // ------------------------ TRATAMIENTOS COMPARTIDOS POR CUENTAS (DEMO) ------------------------
  let usuarioActual = null;
  let servidorTratamientos = [];
  let historialActual = [];
  let dniVistaTratamientos = '';
  let dniVistaHistorial = '';
  const puedeSupervisar = () => ['cuidador','ambos','medico'].includes(rolActual);
  const propioDNI = () => usuarioActual?.dni || '';
  const nombreCompleto = () => usuarioActual ? (usuarioActual.nombres + ' ' + usuarioActual.apellidos).trim() : '';
  const mensajeError = error => error?.message || 'No se pudo completar la operación.';
  const tratarValor = id => $(id).value.trim();

  function actualizarFormulariosPorRol() {
    const rol = rolActual;
    const supervisor = puedeSupervisar();
    const medico = rol === 'medico';
    $('#trat-destino-box').hidden = !supervisor;
    $('#historial-consulta').hidden = !supervisor;
    $('#trat-medico-extra').hidden = !medico;
    ['#trat-medico-nombre','#trat-motivo','#trat-indicaciones'].forEach(id => {
      $(id).disabled = !medico;
      $(id).required = medico;
    });
    if (medico && !$('#trat-medico-nombre').value) $('#trat-medico-nombre').value = nombreCompleto();
    if (!supervisor) {
      $('#trat-dni-paciente').value = '';
      $('#historial-dni').value = '';
      dniVistaTratamientos = '';
      dniVistaHistorial = '';
    }
    const options = $('#perfil-cambiar-rol');
    const optMed = options.querySelector('option[value="medico"]');
    optMed.hidden = !medico;
    optMed.disabled = !medico;
    options.value = rol || 'paciente';
    $('#perfil-vinculo-dni').value = usuarioActual?.dni_paciente || '';
    actualizarOpcionesRol();
  }
  function actualizarOpcionesRol() {
    const newRole = $('#perfil-cambiar-rol').value;
    const wantsCare = newRole === 'cuidador' || newRole === 'ambos';
    const leavingDoctor = rolActual === 'medico' && newRole !== 'medico';
    $('#perfil-vinculo-box').hidden = !wantsCare;
    $('#perfil-rol-clave-box').hidden = !leavingDoctor;
    $('#perfil-rol-clave').required = leavingDoctor;
  }
  $('#perfil-cambiar-rol').addEventListener('change', actualizarOpcionesRol);
  $('#form-cambiar-rol').addEventListener('submit', async event => {
    event.preventDefault();
    const message = $('#perfil-rol-feedback');
    message.textContent = '';
    const role = $('#perfil-cambiar-rol').value;
    if (rolActual === 'medico' && role !== 'medico' &&
        !window.confirm('Al dejar de ser Médico perderás el acceso al Dashboard y al stock, y no podrás volver a ser Médico desde el perfil. ¿Continuar?')) return;
    if (role === 'medico' && rolActual === 'medico') {
      message.textContent = 'Ya tienes el rol Médico, que incluye funciones de Paciente y Cuidador.';
      return;
    }
    try {
      const result = await api('/api/rol', {
        method:'POST',
        body:JSON.stringify({
          rol:role,
          dni_paciente:['cuidador','ambos'].includes(role) ? tratarValor('#perfil-vinculo-dni') : '',
          contrasena:$('#perfil-rol-clave').value
        })
      });
      actualizarDatosUsuario(result.usuario);
      dniVistaTratamientos = '';
      dniVistaHistorial = '';
      $('#trat-dni-paciente').value = '';
      $('#historial-dni').value = '';
      $('#perfil-rol-clave').value = '';
      message.textContent = result.mensaje;
      aviso(result.mensaje);
    } catch(error) {
      message.textContent = mensajeError(error);
    }
  });

  async function cargarAvisos() {
    const caja = $('#avisos-tratamientos');
    const lista = $('#lista-avisos');
    try {
      const result = await api('/api/avisos');
      const avisos = result.avisos || [];
      caja.hidden = avisos.length === 0;
      lista.replaceChildren();
      avisos.forEach(item => {
        const nota = create('article','medical-notice');
        nota.append(create('strong','', 'Actualización de ' + item.medico_nombre));
        nota.append(create('p','',item.detalle));
        nota.append(create('small','muted','Motivo: '+item.motivo+' · '+item.fecha));
        if (!item.leido) {
          const mark = create('button','btn btn-soft btn-sm','Marcar como leído');
          mark.type='button';
          mark.addEventListener('click',async()=>{
            try { await api('/api/avisos/'+item.id+'/leer',{method:'POST'});await cargarAvisos(); }
            catch(err){ aviso(mensajeError(err)); }
          });
          nota.append(mark);
        } else {
          nota.append(create('span','status-badge available','Leído'));
        }
        lista.append(nota);
      });
    } catch {
      caja.hidden = true;
    }
  }

  function prepararTratamientoDatos(form) {
    return {
      nombre:String(form.get('nombre')||'').trim(),
      forma:String(form.get('forma')||'').trim(),
      dosis:String(form.get('dosis')||'').trim(),
      inicio:String(form.get('inicio')||''),
      fin:String(form.get('fin')||''),
      frecuencia:Number(form.get('frecuencia')),
      hora:String(form.get('hora')||'').slice(0,5),
      dni_paciente:puedeSupervisar() ? tratarValor('#trat-dni-paciente') : '',
      medico_nombre:rolActual === 'medico' ? tratarValor('#trat-medico-nombre') : '',
      motivo:rolActual === 'medico' ? tratarValor('#trat-motivo') : '',
      indicaciones:rolActual === 'medico' ? tratarValor('#trat-indicaciones') : ''
    };
  }
  $('#form-tratamiento').addEventListener('submit',async event=>{
    event.preventDefault();
    const feedback=$('#trat-feedback');
    const button=event.currentTarget.querySelector('button[type="submit"]');
    const data=prepararTratamientoDatos(new FormData(event.currentTarget));
    feedback.textContent='Guardando en el servidor…';
    button.disabled=true;
    try{
      const result=await api('/api/tratamientos',{method:'POST',body:JSON.stringify(data)});
      dniVistaTratamientos=data.dni_paciente;
      $('#form-tratamiento').reset();
      $('#trat-hora').value='08:00';
      feedback.textContent='«'+data.nombre+'» se guardó para el DNI '+result.tratamiento.titular_dni+'.';
      await mostrarTratamientos();
      aviso('Tratamiento de demostración guardado.');
    }catch(err){feedback.textContent=mensajeError(err);}
    finally{button.disabled=false;}
  });

  async function mostrarTratamientos(){
    const destino=$('#lista-tratamientos');
    destino.replaceChildren(create('div','empty-state','Cargando tratamientos desde el servidor…'));
    $('#trat-vista-persona').textContent='Consultando registros…';
    try{
      const target=puedeSupervisar() ? dniVistaTratamientos : '';
      const data=await api('/api/tratamientos?dni='+encodeURIComponent(target));
      servidorTratamientos=data.tratamientos || [];
      $('#trat-vista-persona').textContent = data.dni === propioDNI()
        ? 'Estos son tus propios medicamentos registrados en el servidor.'
        : 'Registros de demostración del paciente con DNI '+data.dni+'.';
      $('#trat-volver-mios').hidden = data.dni === propioDNI();
      destino.replaceChildren();
      if(!servidorTratamientos.length){
        destino.append(create('div','empty-state','Este DNI aún no tiene tratamientos guardados.'));
      }
      servidorTratamientos.forEach(trat=>{
        const hechas=trat.tomas.filter(t=>t.confirmada).length;
        const pendientes=trat.tomas.filter(t=>!t.confirmada);
        const tarjeta=create('article','treatment-card');
        const encabezado=create('div','treatment-header');
        const caja=create('div');
        caja.append(create('h3','',trat.nombre),
          create('p','',trat.forma+' · '+trat.dosis+' · '+trat.inicio+' a '+trat.fin));
        if(trat.medico_nombre)caja.append(create('p','muted','Médico: '+trat.medico_nombre));
        if(trat.motivo)caja.append(create('p','muted','Motivo: '+trat.motivo));
        if(trat.indicaciones)caja.append(create('p','muted','Administración: '+trat.indicaciones));
        encabezado.append(caja);
        const acciones=create('div','treatment-actions');
        if (rolActual === 'medico') {
          const editar=create('button','btn btn-soft btn-sm','Modificar');
          editar.type='button';
          editar.addEventListener('click',()=>abrirEditorTratamiento(trat));
          acciones.append(editar);
        }
        if(trat.titular_dni === propioDNI() || trat.autor_dni === propioDNI()){
          const eliminar=create('button','btn btn-danger btn-sm','Eliminar');
          eliminar.type='button';
          eliminar.addEventListener('click',async()=>{
            if(!window.confirm('¿Eliminar el tratamiento ficticio «'+trat.nombre+'» y sus tomas?'))return;
            try {
              await api('/api/tratamientos/'+trat.id,{method:'DELETE'});
              await mostrarTratamientos();
              aviso('Tratamiento de ejemplo eliminado.');
            } catch(err){aviso(mensajeError(err));}
          });
          acciones.append(eliminar);
        }
        encabezado.append(acciones);tarjeta.append(encabezado);
        const chips=create('div','treatment-schedule');
        pendientes.slice(0,4).forEach(t=>chips.append(create('span','schedule-chip',fechaLocal(t.fecha))));
        if(pendientes.length>4)chips.append(create('span','schedule-chip','+ '+(pendientes.length-4)+' pendientes'));
        if(!pendientes.length)chips.append(create('span','status-badge available','Todas las tomas confirmadas'));
        tarjeta.append(chips);
        const pie=create('div','treatment-footer');
        pie.append(create('span','muted',hechas+' de '+trat.tomas.length+' tomas confirmadas'));
        const confirmar=create('button','btn btn-primary btn-sm','✓ Confirmar siguiente toma');
        confirmar.type='button';
        if(!pendientes.length)confirmar.disabled=true;
        confirmar.addEventListener('click',async()=>{
          confirmar.disabled=true;
          try{
            await api('/api/tratamientos/'+trat.id+'/confirmar',{method:'POST'});
            await mostrarTratamientos();
            aviso('Toma de demostración confirmada.');
            hablar('Toma de demostración confirmada correctamente.');
          }catch(err){aviso(mensajeError(err));confirmar.disabled=false;}
        });
        pie.append(confirmar);tarjeta.append(pie);destino.append(tarjeta);
      });
      await cargarAvisos();
    }catch(err){
      destino.replaceChildren(create('div','empty-state',mensajeError(err)));
      $('#trat-vista-persona').textContent='No se pudieron cargar los registros.';
      $('#trat-volver-mios').hidden=false;
      $('#avisos-tratamientos').hidden=true;
    }
  }

  $('#trat-consultar-dni').addEventListener('click',async()=>{
    dniVistaTratamientos=tratarValor('#trat-dni-paciente');
    await mostrarTratamientos();
  });
  $('#trat-volver-mios').addEventListener('click',async()=>{
    dniVistaTratamientos='';
    $('#trat-dni-paciente').value='';
    await mostrarTratamientos();
  });

  function abrirEditorTratamiento(trat){
    if(rolActual!=='medico')return;
    const values={
      '#edit-trat-id':trat.id,'#edit-trat-nombre':trat.nombre,
      '#edit-trat-forma':trat.forma,'#edit-trat-dosis':trat.dosis,
      '#edit-trat-inicio':trat.inicio,'#edit-trat-fin':trat.fin,
      '#edit-trat-frecuencia':String(trat.frecuencia),
      '#edit-trat-hora':trat.hora,'#edit-trat-medico':trat.medico_nombre || nombreCompleto(),
      '#edit-trat-motivo':trat.motivo || 'Revisión de ejemplo por profesional',
      '#edit-trat-indicaciones':trat.indicaciones || 'Instrucciones ficticias de ejemplo'
    };
    Object.entries(values).forEach(([id,v])=>$(id).value=v);
    $('#edit-trat-razon').value='';
    $('#edit-trat-feedback').textContent='';
    $('#dialog-edicion-trat').showModal();
  }
  $('#cancelar-edicion-trat').addEventListener('click',()=>$('#dialog-edicion-trat').close());
  $('#form-editar-trat').addEventListener('submit',async event=>{
    event.preventDefault();
    const feedback=$('#edit-trat-feedback');
    const btn=event.currentTarget.querySelector('button[type="submit"]');
    const data={
      nombre:tratarValor('#edit-trat-nombre'),forma:tratarValor('#edit-trat-forma'),
      dosis:tratarValor('#edit-trat-dosis'),inicio:$('#edit-trat-inicio').value,
      fin:$('#edit-trat-fin').value,frecuencia:Number($('#edit-trat-frecuencia').value),
      hora:$('#edit-trat-hora').value.slice(0,5),
      medico_nombre:tratarValor('#edit-trat-medico'),
      motivo:tratarValor('#edit-trat-motivo'),
      indicaciones:tratarValor('#edit-trat-indicaciones'),
      motivo_modificacion:tratarValor('#edit-trat-razon')
    };
    if(!data.motivo_modificacion || data.motivo_modificacion.length<6){
      feedback.textContent='Describe el motivo del cambio (al menos 6 caracteres).';
      return;
    }
    btn.disabled=true;
    try{
      await api('/api/tratamientos/'+$('#edit-trat-id').value,{method:'PUT',body:JSON.stringify(data)});
      $('#dialog-edicion-trat').close();
      await mostrarTratamientos();
      aviso('Cambios guardados. Se notificará al paciente desde su cuenta.');
    }catch(err){feedback.textContent=mensajeError(err);}
    finally{btn.disabled=false;}
  });

  // ------------------------ HISTORIAL POR DNI Y EXPORTACIÓN CSV ------------------------
  async function mostrarHistorial(){
    $('#historial-total').textContent='Cargando historial…';
    const tbody=$('#tabla-historial');tbody.replaceChildren();
    try {
      const dni=puedeSupervisar() ? dniVistaHistorial : '';
      const response=await api('/api/historial?dni='+encodeURIComponent(dni));
      historialActual=response.historial || [];
      $('#historial-total').textContent=historialActual.length+' registros · DNI '+response.dni;
      $('#historial-vacio').hidden=historialActual.length>0;
      $('#exportar-csv').disabled=historialActual.length===0;
      $('#historial-mensaje').textContent=response.dni===propioDNI()
        ? 'Mostrando tu propio historial.'
        : 'Mostrando historial ficticio del paciente con DNI '+response.dni+'.';
      historialActual.forEach(reg=>{
        const fila=create('tr');
        [reg.nombre,fechaLocal(reg.programada),fechaLocal(reg.confirmada)].forEach(txt=>fila.append(create('td','',txt)));
        const estado=create('td');estado.append(create('span','status-badge available','Confirmada'));
        fila.append(estado);tbody.append(fila);
      });
    }catch(err){
      historialActual=[];
      $('#historial-total').textContent=mensajeError(err);
      $('#historial-mensaje').textContent=mensajeError(err);
      $('#historial-vacio').hidden=false;
      $('#exportar-csv').disabled=true;
    }
  }
  $('#historial-buscar').addEventListener('click',async()=>{
    dniVistaHistorial=tratarValor('#historial-dni');
    await mostrarHistorial();
  });
  function celdaCSV(text){
    let valor=String(text??'');
    if(/^[\s]*[=+\-@]/.test(valor))valor="'"+valor;
    return '"'+valor.replaceAll('"','""')+'"';
  }
  $('#exportar-csv').addEventListener('click',()=>{
    if(!historialActual.length)return;
    const filas=[['Medicamento','Horario programado','Confirmación','Estado'],
      ...historialActual.map(r=>[r.nombre,fechaLocal(r.programada),fechaLocal(r.confirmada),'Confirmada'])];
    const contenido='\uFEFF'+filas.map(row=>row.map(celdaCSV).join(';')).join('\r\n');
    const blob=new Blob([contenido],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download='MediCuida_historial_demo.csv';
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    aviso('Historial de prueba exportado en formato CSV.');
  });

  // ------------------------ ACCESIBILIDAD ------------------------
  function aplicarPreferencias() {
    document.body.classList.toggle('large-text',Boolean(preferencias.texto));
    document.body.classList.toggle('high-contrast',Boolean(preferencias.contraste));
    $('#opcion-texto').checked=Boolean(preferencias.texto);
    $('#opcion-contraste').checked=Boolean(preferencias.contraste);
    $('#opcion-voz').checked=Boolean(preferencias.voz);
  }
  [['#opcion-texto','texto'],['#opcion-contraste','contraste'],['#opcion-voz','voz']].forEach(([selector,clave])=>{
    $(selector).addEventListener('change',event=>{
      preferencias[clave]=event.target.checked;
      storageWrite(PREF_KEY,preferencias);aplicarPreferencias();
      if(clave==='voz'&&preferencias.voz)hablar('Lectura en voz alta activada.');
    });
  });
  $('#probar-voz').addEventListener('click',()=>{
    if(!('speechSynthesis' in window)){aviso('Este navegador no ofrece síntesis de voz.');return;}
    if(!preferencias.voz){aviso('Activa la opción «Confirmaciones habladas» para probarla.');return;}
    hablar('Bienvenido a MediCuida. Esta es una demostración de lectura accesible.');
    aviso('Reproduciendo lectura de prueba, si el navegador lo permite.');
  });
  $('#borrar-datos').addEventListener('click',()=>{
    if(!window.confirm('¿Borrar todos los tratamientos y el historial de esta demostración?'))return;
    tratamientos=[];storageWrite(TREAT_KEY,tratamientos);aviso('Datos de demostración restablecidos.');
  });

  // Inicio: comprobar la sesión del backend; las contraseñas nunca se guardan en el navegador.
  aplicarPreferencias();
  (async () => {
    try {
      const sesion = await api('/api/sesion');
      if (sesion.autenticado) {
        actualizarDatosUsuario(sesion.usuario);
        await cargarInventario();
        mostrarAplicacion();
        return;
      }
    } catch { /* Si el servidor falla, el login dará un error descriptivo. */ }
    mostrarLogin();
  })();
})();