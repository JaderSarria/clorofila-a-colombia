// Descarga de escenas Sentinel-2 L1C (SAFE reducido) desde el bucket público de Google Cloud
// (gcp-public-data-sentinel-2) usando la API JSON, que permite CORS. Se ejecuta en la consola
// de cualquier navegador. Cada escena se empaqueta en un .tar (solo bandas B01-B12, B8A,
// metadatos XML y máscaras de detector), listo para ACOLITE (ver aco_step.py).
// Uso:  const safe = await findL1C('S2B_18PWT_20230710_0_L2A');  await downloadSAFE(safe);
const BUCKET = 'gcp-public-data-sentinel-2';
const API = `https://storage.googleapis.com/storage/v1/b/${BUCKET}/o`;
const L1P = {};                                                     // progreso por escena

async function list(prefix, dirsOnly) {                             // lista objetos o "carpetas" bajo un prefijo
  let items = [], prefixes = [], token = '';
  do {
    const u = `${API}?prefix=${encodeURIComponent(prefix)}&maxResults=1000` +
      (dirsOnly ? '&delimiter=/' : '') + (token ? `&pageToken=${token}` : '');
    const j = await (await fetch(u)).json();
    items = items.concat(j.items || []); prefixes = prefixes.concat(j.prefixes || []); token = j.nextPageToken || '';
  } while (token);
  return { items, prefixes };
}

function tarHeader(name, size) {                                    // cabecera ustar de 512 bytes
  const h = new Uint8Array(512), enc = new TextEncoder();
  const put = (s, off, len) => h.set(enc.encode(s).slice(0, len), off);
  let prefix = '';
  if (name.length > 100) { const i = name.lastIndexOf('/', 155); prefix = name.slice(0, i); name = name.slice(i + 1); }
  put(name, 0, 100); put('0000644\0', 100, 8); put('0000000\0', 108, 8); put('0000000\0', 116, 8);
  put(size.toString(8).padStart(11, '0') + '\0', 124, 12);
  put(Math.floor(Date.now() / 1000).toString(8).padStart(11, '0') + '\0', 136, 12);
  put('        ', 148, 8); put('0', 156, 1); put('ustar\0', 257, 6); put('00', 263, 2); put(prefix, 345, 155);
  let sum = 0; for (const b of h) sum += b; put(sum.toString(8).padStart(6, '0') + '\0 ', 148, 8);
  return h;
}

async function findL1C(l2aId) {                                     // id L2A de Earth Search -> carpeta SAFE L1C
  const m = l2aId.match(/^(S2[AB])_(\d{2})([A-Z])([A-Z]{2})_(\d{8})/); if (!m) return null;
  const [_, sat, zone, band, sq, date] = m;
  const { prefixes } = await list(`tiles/${zone}/${band}/${sq}/${sat}_MSIL1C_${date}`, true);
  return prefixes.map(p => p.replace(/\/$/, '')).sort().reverse()[0] || null;   // la de procesamiento más reciente
}

async function downloadSAFE(safe) {
  const { items } = await list(safe + '/', false);
  const keep = items.filter(it => { const n = it.name; if (n.endsWith('_$folder$')) return false; if (/\.xml$|manifest\.safe$/.test(n)) return true;
    if (/IMG_DATA\/.*_B(0[1-9]|1[0-2]|8A)\.jp2$/.test(n)) return true; if (/QI_DATA\/.*(MSK_DETFOO|DETFOO).*\.(jp2|gml)$/.test(n)) return true; return false; });
  const total = keep.reduce((a, it) => a + Number(it.size), 0);
  L1P[safe] = { files: keep.length, total, got: 0, t0: Date.now() };
  const parts = [];
  for (const it of keep) {
    let buf; for (let i = 0; i < 4; i++) { try { const r = await fetch(API + '/' + encodeURIComponent(it.name) + '?alt=media'); if (!r.ok) throw new Error(r.status); buf = await r.arrayBuffer(); break; } catch (e) { await new Promise(r => setTimeout(r, 4000 * (i + 1))); } }
    if (!buf) throw new Error('fallo ' + it.name);
    const rel = it.name.slice(it.name.indexOf(safe.split('/').pop()));
    parts.push(tarHeader(rel, buf.byteLength), new Uint8Array(buf)); const pad = (512 - buf.byteLength % 512) % 512; if (pad) parts.push(new Uint8Array(pad));
    L1P[safe].got += buf.byteLength;
  }
  parts.push(new Uint8Array(1024));
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(parts, { type: 'application/x-tar' }));
  a.download = safe.split('/').pop().replace('.SAFE', '') + '.tar'; document.body.appendChild(a); a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 120000);
  L1P[safe].done = Date.now(); return { files: keep.length, total };
}

// Cola secuencial: una escena a la vez (evita saturar memoria del navegador)
async function descargarTodas(safes) {
  const DLQ = { done: [], fail: [], start: Date.now(), bytes: 0 };
  for (const s of safes) { try { const r = await downloadSAFE(s); DLQ.done.push(s); DLQ.bytes += r.total; } catch (e) { DLQ.fail.push([s, String(e)]); } }
  DLQ.end = Date.now(); return DLQ;
}
