/* Visor de clorofila-a — interfaz */
'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const PALETA = ['#08306b', '#2171b5', '#4eb3d3', '#7bccc4', '#a8ddb5', '#d9f0a3', '#fee391', '#fe9929', '#cc4c02', '#662506'];
const E = {
  info: null, zonas: [], zona: null, mapas: [], escenas: [], fecha: null, modo: 'zona', poligono: null, punto: null,
  trab: null, hechosVistos: new Set(), play: null, serie: [], redcam: [], comp: null, cobertura: 'todo'
};

// ------------------------------------------------------------ utilidades
const api = async (url, opt) => {
  const r = await fetch(url, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Error ${r.status}`);
  return j;
};
const post = (url, body) => api(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const fmt = (v, d = 2) => v == null || !isFinite(v) ? '—' : (v >= 100 ? v.toFixed(0) : v.toFixed(d));
const fmtN = n => n == null ? '—' : n >= 10000 ? (n / 1000).toFixed(1).replace('.', ',') + ' mil' : String(n);
const fFecha = f => new Date(f + 'T12:00:00').toLocaleDateString('es-CO', { day: 'numeric', month: 'short', year: 'numeric' });
const hoy = () => new Date().toISOString().slice(0, 10);
const masDias = (f, d) => { const x = new Date(f + 'T12:00:00'); x.setDate(x.getDate() + d); return x.toISOString().slice(0, 10); };
function colorDe(v) {
  if (v == null) return '#ffffff';
  const t = Math.max(0, Math.min(1, (Math.log10(Math.max(v, 0.1)) + 1) / 3)) * (PALETA.length - 1);
  return PALETA[Math.round(t)];
}
let tAviso;
function aviso(txt, ms = 4500) { const a = $('#aviso'); a.textContent = txt; a.hidden = false; clearTimeout(tAviso); tAviso = setTimeout(() => a.hidden = true, ms); }

// ------------------------------------------------------------ mapa
const map = L.map('mapa', { zoomControl: false, preferCanvas: true }).setView([10.9, -74.5], 9);
L.control.zoom({ position: 'bottomright' }).addTo(map);
L.control.scale({ position: 'bottomright', imperial: false }).addTo(map);
const esri = p => `https://server.arcgisonline.com/ArcGIS/rest/services/${p}/MapServer/tile/{z}/{y}/{x}`;
const BASES = {
  'Océano': L.layerGroup([L.tileLayer(esri('Ocean/World_Ocean_Base'), { maxZoom: 13, attribution: 'Esri, GEBCO, NOAA' }),
                          L.tileLayer(esri('Ocean/World_Ocean_Reference'), { maxZoom: 13 })]),
  'Satélite': L.tileLayer(esri('World_Imagery'), { maxZoom: 18, attribution: 'Esri World Imagery' }),
  'Calles': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap' })
};
let baseActual = 'Satélite';
BASES[baseActual].addTo(map);
const capaZona = L.geoJSON(null, { style: { color: '#ffffff', weight: 1.6, dashArray: '5 5', fill: false } }).addTo(map);
const capaEst = L.layerGroup().addTo(map);
const capaAnal = L.featureGroup().addTo(map);
let capaChla = null, dibujo = null, capaNuevaZona = null;
const capaLejos = L.geoJSON(null, { style: { color: '#ffffff', weight: 1, dashArray: '3 4', fillColor: '#ffffff', fillOpacity: .38 }, interactive: false }).addTo(map);
const capaActual = () => E.comp ? 'c_' + E.comp.id : E.fecha;
let tLejos;
async function cargarLejos() {
  capaLejos.clearLayers(); if (!E.zona || !$('#chkLejos').checked) return;
  try { const g = await api(`/api/lejos/${E.zona.id}?km=${$('#dist').value}`); if (g) capaLejos.addData(g); } catch { }
}

// ------------------------------------------------------------ panel lateral
function abrirPanel(nombre) {
  const p = $('#panel');
  const yaAbierto = !p.classList.contains('cerrado') && $(`.riel button[data-panel="${nombre}"]`).classList.contains('activo');
  $$('.riel button').forEach(b => b.classList.toggle('activo', b.dataset.panel === nombre && !yaAbierto));
  if (yaAbierto) { p.classList.add('cerrado'); return; }
  p.classList.remove('cerrado');
  $$('#panel section').forEach(s => s.hidden = s.dataset.sec !== nombre);
}
$$('.riel button').forEach(b => b.onclick = () => abrirPanel(b.dataset.panel));
$('#cerrarPanel').onclick = () => { $('#panel').classList.add('cerrado'); $$('.riel button').forEach(b => b.classList.remove('activo')); };

// capas
Object.keys(BASES).forEach(k => {
  const b = document.createElement('button'); b.textContent = k; b.className = k === baseActual ? 'sel' : '';
  b.onclick = () => { map.removeLayer(BASES[baseActual]); baseActual = k; BASES[k].addTo(map); BASES[k].bringToBack?.(); $$('#bases button').forEach(x => x.classList.toggle('sel', x.textContent === k)); };
  $('#bases').appendChild(b);
});
$('#opac').oninput = e => { $('#vOpac').textContent = e.target.value; capaChla?.setOpacity(e.target.value / 100); };
$('#chkChla').onchange = e => { if (capaChla) e.target.checked ? capaChla.addTo(map) : map.removeLayer(capaChla); };
$('#chkEst').onchange = e => e.target.checked ? capaEst.addTo(map) : map.removeLayer(capaEst);
$('#chkZona').onchange = e => e.target.checked ? capaZona.addTo(map) : map.removeLayer(capaZona);
$('#chkLejos').onchange = cargarLejos;

// ------------------------------------------------------------ zonas
function pintarZonas() {
  const L_ = $('#listaZonas'); L_.innerHTML = '';
  E.zonas.forEach(z => {
    const b = document.createElement('div'); b.className = 'zona' + (E.zona?.id === z.id ? ' sel' : ''); b.tabIndex = 0;
    b.innerHTML = `<span>${z.nombre}</span><span class="n">${z.n_mapas ? z.n_mapas + ' mapas' : 'sin mapas'} · ${z.res} m${z.propia ? ' <button class="x" title="Quitar zona">×</button>' : ''}</span>`;
    b.onclick = ev => { if (ev.target.classList.contains('x')) return; elegirZona(z.id); };
    b.querySelector('.x')?.addEventListener('click', async ev => {
      ev.stopPropagation(); await api(`/api/zonas/${z.id}`, { method: 'DELETE' }); await cargarInfo(); if (E.zona?.id === z.id) elegirZona(E.zonas[0].id);
    });
    L_.appendChild(b);
  });
}
async function cargarInfo() { E.info = await api('/api/info'); E.zonas = E.info.zonas; pintarZonas(); $('#versionModelo').textContent = `${E.info.version} · ${E.info.n_muestras.toLocaleString('es-CO')} muestras`; }

async function elegirZona(id) {
  E.zona = E.zonas.find(z => z.id === id); E.fecha = null; E.escenas = []; E.punto = null; E.comp = null; cargarLejos();
  capaZona.clearLayers().addData(E.zona.geom); map.fitBounds(capaZona.getBounds(), { padding: [30, 30] });
  if (capaChla) { map.removeLayer(capaChla); capaChla = null; }
  limpiarPoligono(false);
  pintarZonas(); $('#tZona').textContent = E.zona.nombre;
  await cargarMapas();
  const ult = E.mapas.filter(m => (m.motor || 1) >= E.info.motor).at(-1) || E.mapas.at(-1);
  pintarLinea();
  if (ult) elegirFecha(ult.fecha); else pintarTarjeta();
  buscarEscenas(true);
}
async function cargarMapas() { E.mapas = await api(`/api/mapas/${E.zona.id}`); }

// crear zona
function dibujarZona(tipo) {
  borrarZonaDib();
  dibujo?.disable();
  const estilo = { color: '#f59e0b', weight: 2.5, fillOpacity: .08 };
  dibujo = tipo === 'rect' ? new L.Draw.Rectangle(map, { shapeOptions: estilo, showArea: false })
                           : new L.Draw.Polygon(map, { shapeOptions: estilo, showArea: true, metric: true, allowIntersection: false });
  dibujo._tipo = 'zona'; dibujo.enable();
  aviso(tipo === 'rect' ? 'Arrastra un rectángulo sobre el agua.' : 'Clic para cada vértice; clic en el primer punto (o doble clic) para cerrar. Esc cancela.', 6000);
}
function borrarZonaDib() {
  if (capaNuevaZona) map.removeLayer(capaNuevaZona);
  capaNuevaZona = null; $('#btnGuardarZona').disabled = true; $('#btnBorrarZonaDib').hidden = true; $('#infoNuevaZona').textContent = ''; $('#lblResZona').hidden = true; $('#tiempoZona').textContent = '';
}
$('#btnPolZona').onclick = () => dibujarZona('pol');
$('#btnRectZona').onclick = () => dibujarZona('rect');
$('#btnBorrarZonaDib').onclick = borrarZonaDib;
const RES_AUTO = km2 => km2 <= 400 ? 20 : km2 <= 1500 ? 40 : km2 <= 6000 ? 60 : km2 <= 15000 ? 100 : 200;
function estimarTiempo() {
  if (!capaNuevaZona) return;
  const km2 = capaNuevaZona._km2, r = +$('#resZona').value;
  const px = km2 * 1e6 / (r * r);                      // píxeles del área
  const min = Math.max(0.5, px / 250000 * 0.8 + km2 / 4000);   // estimación gruesa (lectura + modelo)
  $('#tiempoZona').innerHTML = `≈ ${(px / 1e6).toFixed(px > 1e6 ? 1 : 2).replace('.', ',')} millones de píxeles · ` +
    `tarda unos <b>${min < 1.5 ? '1' : Math.round(min)} min por fecha</b>` + (min > 10 ? ' — conviene una resolución más gruesa o dejarlo de noche.' : '.');
}
$('#resZona').onchange = estimarTiempo;
function nuevaZonaLista(layer) {
  capaNuevaZona = layer.addTo(map);
  const km2 = L.GeometryUtil.geodesicArea(layer.getLatLngs()[0]) / 1e6; capaNuevaZona._km2 = km2;
  const ok = km2 <= 30000;
  $('#infoNuevaZona').innerHTML = `Área dibujada: <b>${km2.toLocaleString('es-CO', { maximumFractionDigits: 1 })} km²</b>` +
    (ok ? '' : ' · <span style="color:#b45309">supera el máximo de 30.000 km²</span>');
  $('#lblResZona').hidden = !ok; $('#resZona').value = String(RES_AUTO(km2)); estimarTiempo();
  if (!ok) $('#tiempoZona').textContent = '';
  $('#btnGuardarZona').disabled = !ok; $('#btnBorrarZonaDib').hidden = false;
  if (!$('#nombreZona').value) $('#nombreZona').focus();
}
$('#btnGuardarZona').onclick = async () => {
  if (!capaNuevaZona) return;
  try {
    const r = await post('/api/zonas', { nombre: $('#nombreZona').value, geom: capaNuevaZona.toGeoJSON().geometry, res: +$('#resZona').value });
    borrarZonaDib(); $('#nombreZona').value = '';
    await cargarInfo(); await elegirZona(r.id); abrirPanel('fechas'); aviso(`Zona creada (${r.area_km2.toFixed(0)} km², ${r.res} m). Busca y calcula sus fechas en "Fechas".`);
  } catch (e) { aviso(e.message, 7000); }
};

// ------------------------------------------------------------ fechas / escenas
$('#desde').value = masDias(hoy(), -365); $('#hasta').value = hoy();
$('#nubes').oninput = e => $('#vNubes').textContent = e.target.value;
$('#dist').oninput = e => { $('#vDist').textContent = e.target.value; clearTimeout(tLejos); tLejos = setTimeout(cargarLejos, 400); };
$('#btnBuscar').onclick = () => buscarEscenas(false);
async function buscarEscenas(silencioso) {
  if (!E.zona) return;
  $('#resumenFechas').textContent = 'Buscando imágenes Sentinel‑2…'; $('#btnBuscar').disabled = true;
  try {
    E.escenas = await api(`/api/escenas/${E.zona.id}?desde=${$('#desde').value}&hasta=${$('#hasta').value}&nubes=${$('#nubes').value}&cobertura=${E.cobertura}&km=${$('#dist').value}`);
    const sin = E.escenas.filter(e => !e.calculada).length;
    $('#resumenFechas').innerHTML = `${E.escenas.length} imágenes en el periodo · <b>${E.escenas.length - sin}</b> calculadas · <b>${sin}</b> por calcular`;
    $('#btnCalcTodas').disabled = !sin;
  } catch (e) { $('#resumenFechas').textContent = e.message; if (!silencioso) aviso(e.message, 7000); }
  $('#btnBuscar').disabled = false; pintarLinea();
}
$('#btnCalcTodas').onclick = async () => {
  const f = E.escenas.filter(e => !e.calculada).map(e => e.fecha);
  if (!f.length) return;
  await post('/api/calcular', { zona: E.zona.id, fechas: f, dist_max_km: +$('#dist').value, cobertura: E.cobertura });
  aviso(`${f.length} fechas en cola. Tardan ~1 min cada una; puedes seguir usando el visor.`); sondear();
};
$('#btnCancelar').onclick = async () => { await post('/api/cancelar', {}); sondear(); };

// ------------------------------------------------------------ línea de tiempo
function fechasLinea() {
  const m = new Map();
  E.escenas.forEach(e => m.set(e.fecha, { fecha: e.fecha, nubes: e.nubes, teselas: e.teselas }));
  E.mapas.forEach(x => m.set(x.fecha, { ...(m.get(x.fecha) || {}), fecha: x.fecha, mapa: x }));
  return [...m.values()].sort((a, b) => a.fecha.localeCompare(b.fecha));
}
function pintarLinea() {
  const P = $('#pista'); P.querySelectorAll('.l-eje,.l-mes,.l-pt,.l-sel').forEach(n => n.remove());
  const F = fechasLinea(); $('#lVacio').hidden = F.length > 0;
  if (!F.length) return;
  const t = f => new Date(f + 'T12:00:00').getTime();
  let t0 = Math.min(t(F[0].fecha), t($('#desde').value)), t1 = Math.max(t(F.at(-1).fecha), t($('#hasta').value));
  if (t1 - t0 < 864e5 * 30) { t0 -= 864e5 * 15; t1 += 864e5 * 15; }
  const W = P.clientWidth - 16, x = f => 8 + (t(f) - t0) / (t1 - t0) * W;
  P.insertAdjacentHTML('beforeend', '<div class="l-eje"></div>');
  const d = new Date(t0); d.setDate(1); d.setMonth(d.getMonth() + 1);
  const meses = Math.round((t1 - t0) / 864e5 / 30), paso = meses > 30 ? 6 : meses > 14 ? 3 : meses > 7 ? 2 : 1;
  for (; d.getTime() < t1; d.setMonth(d.getMonth() + paso)) {
    const e = document.createElement('div'); e.className = 'l-mes'; e.style.left = (8 + (d.getTime() - t0) / (t1 - t0) * W) + 'px';
    e.textContent = d.toLocaleDateString('es-CO', { month: 'short', year: d.getMonth() === 0 || paso >= 3 ? '2-digit' : undefined }); P.appendChild(e);
  }
  const cola = new Set((E.trab?.pendientes || []).filter(p => p[0] === E.zona?.id).map(p => p[1]));
  if (E.trab?.actual?.zona === E.zona?.id) cola.add(E.trab.actual.fecha);
  F.forEach(f => {
    const b = document.createElement('button'); const ok = f.mapa && (f.mapa.motor || 1) >= E.info.motor;
    b.className = 'l-pt' + (f.mapa ? ' calc' : '') + (f.fecha === E.fecha && !E.comp ? ' sel' : '') + (cola.has(f.fecha) ? ' cola' : '');
    b.style.left = x(f.fecha) + 'px';
    if (f.mapa) b.style.background = colorDe(f.mapa.mediana);
    b.title = `${fFecha(f.fecha)}${f.nubes != null ? ` · nubes ${f.nubes.toFixed(0)}%` : ''}` +
      (f.mapa ? ` · mediana ${fmt(f.mapa.mediana)} µg/L${ok ? '' : ' (versión anterior)'}` : cola.has(f.fecha) ? ' · calculando…' : ' · sin calcular');
    b.onclick = () => elegirFecha(f.fecha);
    P.appendChild(b);
  });
  if (E.comp) { const r = document.createElement('div'); r.className = 'l-rango'; const a = x(E.comp.desde), b = x(E.comp.hasta);
    r.style.left = Math.max(0, a) + 'px'; r.style.width = Math.max(6, b - a) + 'px'; P.appendChild(r); }
  if (E.fecha && !E.comp) { const s = document.createElement('div'); s.className = 'l-sel'; s.style.left = x(E.fecha) + 'px'; s.textContent = fFecha(E.fecha); P.appendChild(s); }
}
window.addEventListener('resize', pintarLinea);
function moverFecha(paso, soloCalc = true) {
  const F = fechasLinea().filter(f => !soloCalc || f.mapa); if (!F.length) return;
  let i = F.findIndex(f => f.fecha === E.fecha); i = i < 0 ? F.length - 1 : (i + paso + F.length) % F.length; elegirFecha(F[i].fecha);
}
$('#ant').onclick = () => moverFecha(-1, false); $('#sig').onclick = () => moverFecha(1, false);
$('#play').onclick = () => {
  if (E.play) { clearInterval(E.play); E.play = null; $('#play').textContent = '▶'; return; }
  $('#play').textContent = '❚❚'; E.play = setInterval(() => moverFecha(1, true), 1400);
};

// ------------------------------------------------------------ fecha seleccionada
async function elegirFecha(f) {
  E.fecha = f; E.comp = null; pintarLinea();
  const m = E.mapas.find(x => x.fecha === f);
  if (capaChla) { map.removeLayer(capaChla); capaChla = null; }
  if (m) {
    capaChla = L.imageOverlay(`/api/mapa/${E.zona.id}/${f}.png?v=${encodeURIComponent(m.creado || '')}`, m.bounds,
      { opacity: $('#opac').value / 100, interactive: false, className: 'chla' });
    if ($('#chkChla').checked) capaChla.addTo(map);
    $('#dlTif').href = `/api/mapa/${E.zona.id}/${f}.tif`;
  }
  pintarTarjeta();
  if (m) { await actualizarAnalisis(); cargarRedcam(); }
}

async function verCompuesto(meta) {
  E.comp = meta; E.stats = null; E.punto = null;
  if (E.play) $('#play').click();
  if (capaChla) { map.removeLayer(capaChla); capaChla = null; }
  capaChla = L.imageOverlay(`/api/mapa/${E.zona.id}/compuestos/${meta.id}.png?v=${encodeURIComponent(meta.creado || '')}`, meta.bounds,
    { opacity: $('#opac').value / 100, interactive: false });
  if ($('#chkChla').checked) capaChla.addTo(map);
  $('#dlTif').href = `/api/mapa/${E.zona.id}/compuestos/${meta.id}.tif`;
  pintarLinea(); pintarTarjeta(); await actualizarAnalisis(); cargarRedcam();
}
const isoMenos = (meses) => { const d = new Date(); d.setMonth(d.getMonth() - meses); return d.toISOString().slice(0, 10); };
function presetPeriodo(p) {
  const ult = E.mapas.at(-1)?.fecha || hoy(), y = +ult.slice(0, 4);
  const r = { '1m': [isoMenos(1), hoy()], '3m': [isoMenos(3), hoy()], 'anio': [isoMenos(12), hoy()],
    'todo': [E.mapas[0]?.fecha || isoMenos(12), ult],
    'seca': ult.slice(5, 7) >= '05' ? [`${y - 1}-12-01`, `${y}-04-30`] : [`${y - 2}-12-01`, `${y - 1}-04-30`],
    'lluviosa': ult.slice(5, 7) >= '12' || ult.slice(5, 7) <= '06' ? [`${y - 1}-05-01`, `${y - 1}-11-30`] : [`${y}-05-01`, `${y}-11-30`] }[p];
  $('#pDesde').value = r[0]; $('#pHasta').value = r[1];
  const n = E.mapas.filter(m => m.fecha >= r[0] && m.fecha <= r[1]).length;
  $('#estadoProm').textContent = `${n} fechas calculadas en ese periodo.`;
}
$$('#presets button').forEach(b => b.onclick = () => presetPeriodo(b.dataset.p));
$('#pMinObs').oninput = e => $('#vMinObs').textContent = e.target.value;
$('#pDesde').value = isoMenos(3); $('#pHasta').value = hoy();
$('#btnPromedio').onclick = async () => {
  const b = $('#btnPromedio'); b.disabled = true; $('#estadoProm').textContent = 'Combinando las fechas…';
  try {
    const m = await post('/api/compuesto', { zona: E.zona.id, desde: $('#pDesde').value, hasta: $('#pHasta').value, stat: $('#pStat').value, min_obs: +$('#pMinObs').value });
    $('#estadoProm').textContent = `Listo: ${m.n_fechas} fechas combinadas.`; await verCompuesto(m);
  } catch (e) { $('#estadoProm').textContent = e.message; }
  b.disabled = false;
};

async function actualizarAnalisis() {
  const m = E.comp || E.mapas.find(x => x.fecha === E.fecha); if (!m) return;
  const geom = E.modo === 'poligono' && E.poligono ? E.poligono : null;
  try {
    let s = null;
    if (E.modo === 'zona' || !geom) s = { mediana: m.mediana, p10: m.p10, p90: m.p90, n: m.n };
    if (geom) s = await post('/api/estadisticas', { zona: E.zona.id, capa: capaActual(), geom });
    E.stats = s; pintarTarjeta();
    E.serie = await post('/api/serie', { zona: E.zona.id, geom }); pintarTarjeta();
  } catch (e) { aviso(e.message); }
}
async function cargarRedcam() {
  try { E.redcam = await api(`/api/redcam?zona=${E.zona.id}&capa=${capaActual()}`); } catch { E.redcam = []; }
  pintarTarjeta();
}

// ------------------------------------------------------------ tarjeta derecha
function pintarTarjeta() {
  const C = $('#tCuerpo'); $('#tFecha').textContent = E.fecha ? fFecha(E.fecha) : 'Elige una fecha';
  if (!E.zona) { C.innerHTML = ''; return; }
  if (E.comp) return pintarTarjetaComp(C);
  if (!E.fecha) { C.innerHTML = `<p class="ayuda">${E.mapas.length ? 'Elige una fecha en la línea de tiempo.' : 'Esta zona aún no tiene mapas. Abre <b>Fechas</b>, busca imágenes y calcula las que quieras.'}</p>`; return; }
  const m = E.mapas.find(x => x.fecha === E.fecha);
  const enCurso = E.trab?.actual && E.trab.actual.zona === E.zona.id && E.trab.actual.fecha === E.fecha;
  const enCola = (E.trab?.pendientes || []).some(p => p[0] === E.zona.id && p[1] === E.fecha);
  if (!m || (m.motor || 1) < E.info.motor && (enCurso || enCola)) {
    const esc = E.escenas.find(e => e.fecha === E.fecha);
    if (enCurso) {
      C.innerHTML = `<div class="estado"><b>Calculando esta fecha…</b><br>${E.trab.actual.texto}<div class="barra-prog"><i style="width:${(E.trab.actual.progreso * 100).toFixed(0)}%"></i></div></div>`;
    } else if (enCola) {
      C.innerHTML = `<div class="estado">En cola. Se calculará en cuanto termine lo que está en curso.</div>`;
    } else {
      C.innerHTML = `<div class="chips">${esc ? `<span class="chip">nubes ${esc.nubes.toFixed(0)}%</span><span class="chip">${esc.teselas}</span>` : ''}</div>
        <p class="ayuda">Esta fecha todavía no está calculada. Tarda ~1 minuto y queda guardada para verla al instante después.</p>
        <button class="pri ancho" id="btnCalcEsta">Calcular esta fecha</button>`;
      $('#btnCalcEsta').onclick = async () => { await post('/api/calcular', { zona: E.zona.id, fechas: [E.fecha], dist_max_km: +$('#dist').value, cobertura: E.cobertura }); sondear(); };
    }
    return;
  }
  const s = E.stats || m; const viejo = (m.motor || 1) < E.info.motor;
  const area = E.modo === 'poligono' && E.poligono ? 'Tu polígono' : 'Toda la zona';
  let h = `<div class="chips"><span class="chip">${m.res} m</span><span class="chip">nubes ${fmt(m.nubes_escena, 0)}%</span><span class="chip">${(m.teselas || '').replaceAll('MGRS-', '')}</span></div>`;
  if (viejo) h += `<div class="estado" style="margin-bottom:8px">Mapa de la versión anterior (con bordes rectos). <a href="#" id="recalc">Recalcular</a></div>`;
  else if (E.cobertura === 'todo' && m.cobertura !== 'todo') h += `<div class="estado" style="margin-bottom:8px">Calculado solo cerca de las estaciones. <a href="#" id="recalc">Recalcular toda la zona</a></div>`;
  h += `<div class="sub">${area}</div>`;
  h += s ? `<div class="metricas"><div class="met"><div class="et">Mediana µg/L</div><div class="v">${fmt(s.mediana)}</div></div>
        <div class="met"><div class="et">p10 – p90</div><div class="v">${fmt(s.p10, 1)}–${fmt(s.p90, 1)}</div></div>
        <div class="met"><div class="et">Píxeles</div><div class="v">${fmtN(s.n)}</div></div></div>` : '<p class="ayuda">No hay agua visible en el área en esta fecha.</p>';
  if (E.punto) h += `<div class="sub">Punto ${E.punto.lat.toFixed(5)}, ${E.punto.lng.toFixed(5)}</div><div>${E.punto.v == null ? 'Sin dato (nube, tierra, vegetación o lejos de estaciones)' : `<b style="font-size:17px">${fmt(E.punto.v)} µg/L</b>`}</div>`;
  if (E.serie && E.serie.length > 1) h += `<div class="sub">Serie de tiempo · ${area.toLowerCase()}</div>${svgSerie(E.serie)}`;
  if (E.redcam && E.redcam.length) {
    h += `<div class="sub">REDCAM a ±20 días (real vs. mapa)</div><table class="tabla"><thead><tr><th>Estación</th><th class="n">Real</th><th class="n">Mapa</th><th class="n">± d</th></tr></thead><tbody>` +
      E.redcam.slice(0, 10).map(r => `<tr><td>${r.estacion}</td><td class="n">${fmt(r.real)}</td><td class="n">${fmt(r.mapa)}</td><td class="n">${r.dias > 0 ? '+' : ''}${r.dias}</td></tr>`).join('') + '</tbody></table>';
  }
  C.innerHTML = h;
  $('#recalc')?.addEventListener('click', async ev => { ev.preventDefault(); await post('/api/calcular', { zona: E.zona.id, fechas: [E.fecha], dist_max_km: +$('#dist').value, cobertura: E.cobertura }); sondear(); });
  C.querySelectorAll('svg.serie circle').forEach(c => c.onclick = () => elegirFecha(c.dataset.f));
}
function pintarTarjetaComp(C) {
  const m = E.comp, s = E.stats || m, area = E.modo === 'poligono' && E.poligono ? 'Tu polígono' : 'Toda la zona';
  $('#tFecha').textContent = `${fFecha(m.desde)} – ${fFecha(m.hasta)}`;
  let h = `<div class="chips"><span class="chip prom">Promedio · ${m.stat_nombre}</span><span class="chip">${m.n_fechas} fechas</span>
    <span class="chip">~${fmt(m.obs_mediana, 0)} fechas con dato por píxel</span><span class="chip">${m.res} m</span></div>`;
  h += `<div class="sub">${area}</div>`;
  h += s ? `<div class="metricas"><div class="met"><div class="et">Mediana µg/L</div><div class="v">${fmt(s.mediana)}</div></div>
        <div class="met"><div class="et">p10 – p90</div><div class="v">${fmt(s.p10, 1)}–${fmt(s.p90, 1)}</div></div>
        <div class="met"><div class="et">Píxeles</div><div class="v">${fmtN(s.n)}</div></div></div>` : '<p class="ayuda">Sin datos en el área.</p>';
  if (E.punto) h += `<div class="sub">Punto ${E.punto.lat.toFixed(5)}, ${E.punto.lng.toFixed(5)}</div><div>${E.punto.v == null ? 'Sin dato' : `<b style="font-size:17px">${fmt(E.punto.v)} µg/L</b>`}</div>`;
  if (E.serie && E.serie.length > 1) h += `<div class="sub">Serie diaria · ${area.toLowerCase()} (sombreado: el periodo)</div>${svgSerie(E.serie)}`;
  if (E.redcam && E.redcam.length) {
    h += `<div class="sub">REDCAM en el periodo (${m.stat_nombre} de las muestras vs. mapa)</div><table class="tabla"><thead><tr><th>Estación</th><th class="n">Real</th><th class="n">Mapa</th><th class="n">n</th></tr></thead><tbody>` +
      E.redcam.slice(0, 12).map(r => `<tr><td>${r.estacion}</td><td class="n">${fmt(r.real)}</td><td class="n">${fmt(r.mapa)}</td><td class="n">${r.muestras}</td></tr>`).join('') + '</tbody></table>';
  }
  h += `<button class="link" id="volverDia">Volver a ver una sola fecha</button>`;
  C.innerHTML = h;
  $('#volverDia').onclick = () => elegirFecha(E.fecha || E.mapas.at(-1)?.fecha);
  C.querySelectorAll('svg.serie circle').forEach(c => c.onclick = () => elegirFecha(c.dataset.f));
}
$('#plegar').onclick = () => { $('#tarjeta').classList.toggle('plegada'); $('#plegar').textContent = $('#tarjeta').classList.contains('plegada') ? '+' : '–'; };

function svgSerie(S) {
  const W = 330, H = 150, l = 34, r = 8, t = 10, b = 22;
  const vals = S.flatMap(s => [s.p10, s.p90, s.mediana]).filter(v => v > 0);
  let lo = Math.log10(Math.min(...vals)), hi = Math.log10(Math.max(...vals)); if (hi - lo < 0.5) { lo -= .25; hi += .25; }
  const ts = S.map(s => new Date(s.fecha + 'T12:00:00').getTime()), t0 = Math.min(...ts), t1 = Math.max(...ts) || t0 + 1;
  const X = tm => l + (tm - t0) / ((t1 - t0) || 1) * (W - l - r), Y = v => t + (hi - Math.log10(Math.max(v, 1e-3))) / (hi - lo) * (H - t - b);
  const banda = S.map((s, i) => `${X(ts[i])},${Y(s.p90)}`).join(' ') + ' ' + S.map((s, i) => `${X(ts[i])},${Y(s.p10)}`).reverse().join(' ');
  const linea = S.map((s, i) => `${X(ts[i])},${Y(s.mediana)}`).join(' ');
  const ticks = []; for (let e = Math.ceil(lo); e <= Math.floor(hi); e++) for (const k of [1, 3]) { const v = k * 10 ** e; if (Math.log10(v) >= lo && Math.log10(v) <= hi) ticks.push(v); }
  return `<svg class="serie" viewBox="0 0 ${W} ${H}" role="img" aria-label="Serie de tiempo">
    ${ticks.map(v => `<line x1="${l}" x2="${W - r}" y1="${Y(v)}" y2="${Y(v)}" stroke="#e3eaed"/><text x="${l - 5}" y="${Y(v) + 3}" text-anchor="end">${v >= 1 ? v : v.toFixed(1)}</text>`).join('')}
    ${E.comp ? `<rect x="${X(Math.max(t0, new Date(E.comp.desde + 'T00:00:00').getTime()))}" y="${t}" width="${Math.max(2, X(Math.min(t1, new Date(E.comp.hasta + 'T23:59:00').getTime())) - X(Math.max(t0, new Date(E.comp.desde + 'T00:00:00').getTime())))}" height="${H - t - b}" fill="#0b3b6f14"/>` : ''}
    <polygon points="${banda}" fill="#0d7c8a22"/><polyline points="${linea}" fill="none" stroke="#0d7c8a" stroke-width="1.6"/>
    ${S.map((s, i) => `<circle cx="${X(ts[i])}" cy="${Y(s.mediana)}" r="${s.fecha === E.fecha && !E.comp ? 4.5 : 3}" fill="${s.fecha === E.fecha && !E.comp ? '#0b3b6f' : colorDe(s.mediana)}" stroke="#0b3b6f" stroke-width=".8" data-f="${s.fecha}" style="cursor:pointer"><title>${fFecha(s.fecha)}: ${fmt(s.mediana)} µg/L</title></circle>`).join('')}
    <text x="${l}" y="${H - 6}">${fFecha(S[0].fecha)}</text><text x="${W - r}" y="${H - 6}" text-anchor="end">${fFecha(S.at(-1).fecha)}</text></svg>`;
}

// ------------------------------------------------------------ análisis: zona / polígono / punto
const AYUDA_MODO = {
  zona: 'Las estadísticas y la serie corresponden a toda la zona.',
  poligono: 'Dibuja un polígono dentro de la zona. Solo sirve para resumir: no cambia la zona ni recalcula.',
  punto: 'Haz clic en el agua para ver el valor de ese punto en la fecha elegida.'
};
function ponerModo(m) {
  E.modo = m; $$('#segModo button').forEach(b => b.classList.toggle('sel', b.dataset.modo === m));
  $('#ayudaModo').textContent = AYUDA_MODO[m];
  $('#btnDibujarPol').hidden = m !== 'poligono'; $('#btnBorrarPol').hidden = m !== 'poligono' || !E.poligono;
  if (m !== 'punto') E.punto = null;
  if (m === 'poligono' && !E.poligono) iniciarPoligono();
  capaAnal.eachLayer(l => l.setStyle?.({ opacity: m === 'poligono' ? 1 : .35 }));
  E.stats = null; actualizarAnalisis();
}
$$('#segModo button').forEach(b => b.onclick = () => ponerModo(b.dataset.modo));
const AYUDA_COB = { todo: 'Se estima en toda el agua de la zona. Las partes lejos de estaciones se marcan con un velo blanco (menor confianza).',
                    cerca: 'Solo se estima cerca de las estaciones REDCAM; lo demás queda en blanco. Más rápido y más confiable.' };
function ponerCobertura(c) { E.cobertura = c; $$('#segCob button').forEach(b => b.classList.toggle('sel', b.dataset.cob === c)); $('#ayudaCob').textContent = AYUDA_COB[c]; }
$$('#segCob button').forEach(b => b.onclick = () => { ponerCobertura(b.dataset.cob); if (E.zona) buscarEscenas(true); });
ponerCobertura('todo');
function iniciarPoligono() {
  dibujo?.disable(); dibujo = new L.Draw.Polygon(map, { shapeOptions: { color: '#ffd166', weight: 2.5, fillOpacity: .05 }, showArea: true });
  dibujo._tipo = 'analisis'; dibujo.enable(); aviso('Haz clic para poner vértices y clic en el primer punto para cerrar.');
}
function limpiarPoligono(refrescar = true) {
  capaAnal.clearLayers(); E.poligono = null; $('#btnBorrarPol').hidden = true; E.stats = null;
  if (refrescar) actualizarAnalisis();
}
$('#btnDibujarPol').onclick = iniciarPoligono;
$('#btnBorrarPol').onclick = () => limpiarPoligono(true);
map.on(L.Draw.Event.CREATED, ev => {
  if (dibujo?._tipo === 'zona') {
    nuevaZonaLista(ev.layer); return;
  }
  capaAnal.clearLayers(); capaAnal.addLayer(ev.layer); E.poligono = ev.layer.toGeoJSON().geometry;
  $('#btnBorrarPol').hidden = false; E.modo = 'poligono'; ponerModo('poligono');
});
map.on('click', async ev => {
  if (dibujo?._enabled) return;
  const m = E.comp || E.mapas.find(x => x.fecha === E.fecha); if (!m) return;
  try {
    const r = await api(`/api/valor?zona=${E.zona.id}&capa=${capaActual()}&lat=${ev.latlng.lat}&lon=${ev.latlng.lng}`);
    E.punto = { lat: ev.latlng.lat, lng: ev.latlng.lng, v: r.valor };
    L.popup({ className: 'popup-v' }).setLatLng(ev.latlng).setContent(r.valor == null ? 'Sin dato' : `<b>${fmt(r.valor)} µg/L</b><br>${E.comp ? 'Promedio ' + fFecha(E.comp.desde) + ' – ' + fFecha(E.comp.hasta) : fFecha(E.fecha)}`).openOn(map);
    if (E.modo === 'punto') pintarTarjeta();
  } catch { }
});

// ------------------------------------------------------------ estaciones
async function cargarEstaciones() {
  const S = await api('/api/estaciones');
  S.forEach(s => L.circleMarker([s.lat, s.lon], { radius: 4, color: '#fff', weight: 1, fillColor: '#d7301f', fillOpacity: 1 })
    .bindTooltip(`<b>${s.lugar}</b><br>${s.n} muestras · última ${s.ultima}: ${fmt(s.ult_val)} µg/L`).addTo(capaEst));
}

// ------------------------------------------------------------ trabajos en segundo plano
let tSondeo;
async function sondear() {
  clearTimeout(tSondeo);
  try { E.trab = await api('/api/trabajos'); } catch { tSondeo = setTimeout(sondear, 5000); return; }
  const T = E.trab, n = T.pendientes.length + (T.actual ? 1 : 0);
  const ind = $('#indTrab');
  ind.hidden = !n; if (n) ind.textContent = `Calculando ${n} fecha${n > 1 ? 's' : ''}${T.actual ? ` · ${(T.actual.progreso * 100).toFixed(0)}%` : ''}`;
  $('#estadoTrab').innerHTML = n ? `${T.actual ? `En curso: <b>${T.actual.fecha}</b> (${T.actual.zona}) — ${T.actual.texto}<div class="barra-prog"><i style="width:${(T.actual.progreso * 100).toFixed(0)}%"></i></div>` : ''}${T.pendientes.length} en espera.` :
    'Nada en cola.' + (T.errores.length ? `<br>Último error: ${T.errores[0].fecha}: ${T.errores[0].error}` : '');
  $('#btnCancelar').hidden = !T.pendientes.length;
  const nuevos = T.hechos.filter(h => !E.hechosVistos.has(h.zona + h.fecha));
  T.hechos.forEach(h => E.hechosVistos.add(h.zona + h.fecha));
  if (nuevos.some(h => h.zona === E.zona?.id)) {
    await cargarMapas(); await cargarInfo();
    E.escenas.forEach(e => { if (E.mapas.some(m => m.fecha === e.fecha && (m.motor || 1) >= E.info.motor)) e.calculada = true; });
    if (nuevos.some(h => h.zona === E.zona.id && h.fecha === E.fecha)) elegirFecha(E.fecha);
  }
  const err = T.errores[0];
  if (err && !E.hechosVistos.has('err' + err.zona + err.fecha)) { E.hechosVistos.add('err' + err.zona + err.fecha); if (err.zona === E.zona?.id) aviso(`No se pudo calcular ${err.fecha}: ${err.error}`, 8000); }
  pintarLinea(); if (E.fecha) { const m = E.mapas.find(x => x.fecha === E.fecha); if (!m || T.actual?.fecha === E.fecha) pintarTarjeta(); }
  tSondeo = setTimeout(sondear, n ? 2000 : 8000);
}

// ------------------------------------------------------------ descargas
function bajarCSV(nombre, filas) {
  if (!filas.length) { aviso('No hay datos para descargar.'); return; }
  const cols = Object.keys(filas[0]);
  const txt = [cols.join(',')].concat(filas.map(f => cols.map(c => f[c] ?? '').join(','))).join('\n');
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['﻿' + txt], { type: 'text/csv' })); a.download = nombre; a.click();
}
$('#dlSerie').onclick = () => bajarCSV(`serie_${E.zona?.id}_${E.modo}.csv`, E.serie || []);
$('#dlRedcam').onclick = () => bajarCSV(`redcam_vs_mapa_${E.zona?.id}_${E.fecha}.csv`, E.redcam || []);

// ------------------------------------------------------------ inicio
(async () => {
  $$('#panel section').forEach(s => s.hidden = s.dataset.sec !== 'zonas');
  ponerModo('zona');
  await cargarInfo();
  cargarEstaciones();
  const conMapas = E.zonas.find(z => z.n_mapas) || E.zonas.find(z => z.id === 'cienaga_grande') || E.zonas[0];
  await elegirZona(conMapas.id);
  sondear();
})();
