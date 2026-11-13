/* MediCuida · Grupo 1 · Frontend conectado a una API local Python/SQLite.
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
    rolActual = usuario && ['paciente','cuidador','medico'].includes(usuario.rol) ? usuario.rol : null;
    actualizarNavegacionPorRol();
    const nombreCompleto = usuario ? `${usuario.nombres} ${usuario.apellidos}`.trim() : 'Usuario';
    $('#usuario-chip').textContent = nombreCompleto || 'Usuario';
    $('#perfil-nombres').textContent = usuario?.nombres || '-';
    $('#perfil-apellidos').textContent = usuario?.apellidos || '-';
    $('#perfil-dni').textContent = usuario?.dni || '-';
    $('#perfil-correo').textContent = usuario?.correo || '-';
    const nombresRoles = { paciente:'Paciente', cuidador:'Cuidador', medico:'Médico' };
    $('#perfil-rol').textContent = nombresRoles[usuario?.rol] || '-';
    $('#perfil-cuidador').hidden = usuario?.rol !== 'cuidador';
    $('#perfil-medico').hidden = usuario?.rol !== 'medico';
    $('#perfil-dni-paciente').textContent = usuario?.dni_paciente || '-';
    $('#perfil-ruc').textContent = usuario?.ruc || '-';
    $('#perfil-puesto').textContent = usuario?.puesto || '-';
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
      aviso('Bienvenido a MediCuida. Inventario cargado desde SQLite.');
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
  function registrosFiltrados(categoria, establecimiento, busqueda = '') {
    const term = busqueda.trim().toLocaleLowerCase('es');
    return inventario.filter(item =>
      (!categoria || item.categoria === categoria) &&
      (!establecimiento || item.establecimiento === establecimiento) &&
      (!term || `${item.id} ${item.nombre} ${item.categoria} ${item.establecimiento}`.toLocaleLowerCase('es').includes(term))
    );
  }
  function badgeEstado(estado) {
    return create('span', `status-badge ${ESTADOS[estado].clase}`, ESTADOS[estado].texto);
  }
  function mostrarResultados() {
    const datos = registrosFiltrados($('#categoria-consulta').value,$('#establecimiento-consulta').value,$('#buscar-stock').value);
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
  ['#categoria-consulta','#establecimiento-consulta'].forEach(id => $(id).addEventListener('change',mostrarResultados));
  $('#buscar-stock').addEventListener('input', mostrarResultados);
  $('#limpiar-consulta').addEventListener('click', () => {
    $('#buscar-stock').value = '';
    $('#categoria-consulta').value = '';
    $('#establecimiento-consulta').value = '';
    mostrarResultados();
  });

  // ------------------------ INDICADORES Y GRÁFICOS ------------------------
  function mostrarDashboard() {
    const registros = registrosFiltrados($('#categoria-dashboard').value,$('#establecimiento-dashboard').value);
    const total = registros.length;
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
  ['#categoria-dashboard','#establecimiento-dashboard'].forEach(id => $(id).addEventListener('change',mostrarDashboard));
  $('#reiniciar-dashboard').addEventListener('click', () => {
    $('#categoria-dashboard').value='';$('#establecimiento-dashboard').value='';mostrarDashboard();
  });

  // ------------------------ CRUD DE INVENTARIO · API / SQLite ------------------------
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
    $('#inventario-total').textContent = `${inventario.length} ${inventario.length === 1 ? 'medicamento' : 'medicamentos'} almacenados en SQLite`;
    if (!inventario.length) {
      const fila = document.createElement('tr');
      const celda = create('td', '', 'No hay medicamentos. Agrega uno con el formulario.');
      celda.colSpan = 7;
      fila.append(celda); tbody.append(fila);
      return;
    }
    inventario.forEach(med => {
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
          aviso(`Medicamento ${med.id} eliminado de SQLite.`);
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
  $('#actualizar-inventario').addEventListener('click',async () => {
    try { await cargarInventario(); aviso('Datos actualizados desde SQLite.'); }
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
      aviso(id ? 'Medicamento actualizado en SQLite.' : 'Medicamento agregado a SQLite.');
    } catch(err) { feedback.textContent = err.message; }
    finally { boton.disabled = false; }
  });

  // ------------------------ TRATAMIENTOS DE PRUEBA ------------------------
  function diasDeEjemplo(desde, hasta) {
    const a = new Date(`${desde}T00:00:00Z`);
    const b = new Date(`${hasta}T00:00:00Z`);
    const n = Math.round((b-a)/86400000)+1;
    return Number.isFinite(n)?n:0;
  }
  function generarTomas(inicio, cantidadDias, frecuencia, hora) {
    const [hh,mm] = hora.split(':').map(Number);
    const tomas = [];
    const inicioMs = Date.parse(`${inicio}T00:00:00Z`);
    for(let dia=0;dia<cantidadDias;dia++) {
      for(let i=0;i<frecuencia;i++) {
        const fecha = new Date(inicioMs + dia*86400000 + ((hh*60+mm)+(i*1440/frecuencia))*60000);
        tomas.push({id:identificador(), fecha:fecha.toISOString(), confirmada:null});
      }
    }
    return tomas;
  }
  $('#form-tratamiento').addEventListener('submit',event=>{
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const nombre = String(form.get('nombre')||'').trim();
    const forma = String(form.get('forma')||'');
    const dosis = String(form.get('dosis')||'').trim();
    const inicio = String(form.get('inicio')||'');
    const fin = String(form.get('fin')||'');
    const frecuencia = Number(form.get('frecuencia'));
    const hora = String(form.get('hora')||'');
    const feedback = $('#trat-feedback');
    const dias = diasDeEjemplo(inicio,fin);
    if (!nombre || !forma || !dosis || !inicio || !fin || !hora || ![1,2,3].includes(frecuencia)) {
      feedback.textContent='Completa todos los campos obligatorios.';return;
    }
    if (dias < 1 || dias > 30) {
      feedback.textContent='La fecha final debe ser igual o posterior a la inicial. Para esta demo usa hasta 30 días.';return;
    }
    if (tratamientos.length >= 40) {feedback.textContent='Límite de 40 registros de demostración alcanzado.';return;}
    const nuevo = {id:identificador(),nombre,forma,dosis,inicio,fin,frecuencia,hora,
      tomas:generarTomas(inicio,dias,frecuencia,hora)};
    tratamientos.push(nuevo);
    if (!storageWrite(TREAT_KEY,tratamientos)) {tratamientos.pop();feedback.textContent='No fue posible guardar este registro.';return;}
    $('#form-tratamiento').reset();
    feedback.textContent=`«${nombre}» se guardó con ${nuevo.tomas.length} horarios de demostración.`;
    mostrarTratamientos();
    aviso('Tratamiento de ejemplo guardado.');hablar('Tratamiento de ejemplo guardado correctamente.');
  });
  function mostrarTratamientos() {
    const destino = $('#lista-tratamientos');destino.replaceChildren();
    if(!tratamientos.length){destino.append(create('div','empty-state','No hay tratamientos guardados. Completa el formulario para probar el sistema.'));return;}
    tratamientos.forEach(trat=>{
      if (!Array.isArray(trat.tomas)) return;
      const hechas = trat.tomas.filter(t=>t.confirmada).length;
      const pendientes = trat.tomas.filter(t=>!t.confirmada).sort((a,b)=>a.fecha.localeCompare(b.fecha));
      const tarjeta = create('article','treatment-card');
      const encabezado = create('div','treatment-header');const caja = create('div');
      caja.append(create('h3','',trat.nombre),create('p','',`${trat.forma} · ${trat.dosis} · ${trat.inicio} a ${trat.fin}`));
      const eliminar = create('button','btn btn-danger btn-sm','Eliminar');eliminar.type='button';
      eliminar.addEventListener('click',()=>{
        if(!window.confirm(`¿Eliminar el tratamiento de prueba «${trat.nombre}» y sus confirmaciones?`))return;
        tratamientos = tratamientos.filter(t=>t.id!==trat.id);
        storageWrite(TREAT_KEY,tratamientos);mostrarTratamientos();aviso('Tratamiento de ejemplo eliminado.');
      });
      encabezado.append(caja,eliminar); tarjeta.append(encabezado);
      const chips = create('div','treatment-schedule');
      pendientes.slice(0,4).forEach(toma=>chips.append(create('span','schedule-chip',fechaLocal(toma.fecha))));
      if(pendientes.length>4)chips.append(create('span','schedule-chip',`+ ${pendientes.length-4} pendientes`));
      if(!pendientes.length)chips.append(create('span','status-badge available','Todas las tomas confirmadas'));
      tarjeta.append(chips);
      const pie = create('div','treatment-footer');
      pie.append(create('span','muted',`${hechas} de ${trat.tomas.length} tomas confirmadas`));
      const confirmar = create('button','btn btn-primary btn-sm','✓ Confirmar siguiente toma');confirmar.type='button';
      if (!pendientes.length) confirmar.disabled=true;
      confirmar.addEventListener('click',()=>confirmarSiguiente(trat.id));
      pie.append(confirmar);tarjeta.append(pie);destino.append(tarjeta);
    });
  }
  function confirmarSiguiente(id) {
    const tratamiento = tratamientos.find(t=>t.id===id);
    if(!tratamiento || !Array.isArray(tratamiento.tomas)) return;
    const tomas = [...tratamiento.tomas].sort((a,b)=>a.fecha.localeCompare(b.fecha));
    const siguiente = tomas.find(t=>!t.confirmada);
    if(!siguiente){aviso('Ya se confirmaron las tomas de este tratamiento.');return;}
    // Protección de demo contra doble pulsación: no registra dos tomas en menos de 120 min.
    const ultima = tomas.filter(t=>t.confirmada).map(t=>Date.parse(t.confirmada)).sort((a,b)=>b-a)[0];
    if (ultima && Date.now()-ultima < 120*60000) {
      aviso('Aviso de seguridad: se bloquea otra confirmación durante 120 minutos en esta demostración.');
      return;
    }
    siguiente.confirmada = new Date().toISOString();
    if (!storageWrite(TREAT_KEY,tratamientos)) {siguiente.confirmada=null;return;}
    mostrarTratamientos();
    aviso('✓ Toma de demostración confirmada.');
    hablar('Dosis de demostración confirmada correctamente.');
  }
  // ------------------------ HISTORIAL / CSV ------------------------
  function datosHistorial() {
    return tratamientos.flatMap(trat => Array.isArray(trat.tomas) ?
      trat.tomas.filter(t=>t.confirmada).map(t=>({nombre:trat.nombre,programada:t.fecha,confirmada:t.confirmada})) : [])
      .sort((a,b)=>b.confirmada.localeCompare(a.confirmada));
  }
  function mostrarHistorial() {
    const registros = datosHistorial();
    $('#historial-total').textContent=`${registros.length} ${registros.length===1?'registro':'registros'} · solo en este navegador`;
    $('#historial-vacio').hidden=registros.length>0;
    $('#exportar-csv').disabled=registros.length===0;
    const tbody=$('#tabla-historial');tbody.replaceChildren();
    registros.forEach(reg=>{
      const fila=document.createElement('tr');
      [reg.nombre,fechaLocal(reg.programada),fechaLocal(reg.confirmada)].forEach(txt=>fila.append(create('td','',txt)));
      const estado=create('td');estado.append(badgeEstado('disponible'));estado.firstChild.textContent='Confirmada';
      fila.append(estado);tbody.append(fila);
    });
  }
  function celdaCSV(text) {
    let valor=String(text??'');
    // Excel/LibreOffice: evita que el texto proporcionado se interprete como fórmula.
    if (/^[\s]*[=+\-@]/.test(valor)) valor="'"+valor;
    return `"${valor.replaceAll('"','""')}"`;
  }
  $('#exportar-csv').addEventListener('click',()=>{
    const regs=datosHistorial();if(!regs.length)return;
    const filas=[['Medicamento','Horario programado','Confirmación','Estado'],
      ...regs.map(r=>[r.nombre,fechaLocal(r.programada),fechaLocal(r.confirmada),'Confirmada'])];
    const contenido='\uFEFF'+filas.map(row=>row.map(celdaCSV).join(';')).join('\r\n');
    const blob=new Blob([contenido],{type:'text/csv;charset=utf-8;'});
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