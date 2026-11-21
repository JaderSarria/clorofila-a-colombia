// Busca, en la misma escena Sentinel-2 L2A (Earth Search, COG), el píxel 3x3 de agua limpia más cercano a la estación
// (SCL=6, sin vegetación: no (NDVI>0 y B8A/B05>1.2), B8A<0.1), dentro de H píxeles de 20 m. Requiere geotiff.js:
//   window.GT = await import('https://cdn.jsdelivr.net/npm/geotiff@2.1.3/+esm');
// Reflectancia = DN*scale + offset (+0.1 si earthsearch:boa_offset_applied).
window.utm=function(lat, lon, zone){ const a=6378137, f=1/298.257223563, k0=0.9996, e2=f*(2-f), ep2=e2/(1-e2);
 const lon0=((zone-1)*6-180+3)*Math.PI/180, phi=lat*Math.PI/180, lam=lon*Math.PI/180;
 const N=a/Math.sqrt(1-e2*Math.sin(phi)**2), T=Math.tan(phi)**2, C=ep2*Math.cos(phi)**2, A=Math.cos(phi)*(lam-lon0);
 const M=a*((1-e2/4-3*e2**2/64-5*e2**3/256)*phi-(3*e2/8+3*e2**2/32+45*e2**3/1024)*Math.sin(2*phi)+(15*e2**2/256+45*e2**3/1024)*Math.sin(4*phi)-(35*e2**3/3072)*Math.sin(6*phi));
 const E=k0*N*(A+(1-T+C)*A**3/6+(5-18*T+T*T+72*C-58*ep2)*A**5/120)+500000;
 let Nn=k0*(M+N*Math.tan(phi)*(A*A/2+(5-T+9*C+4*C*C)*A**4/24+(61-58*T+T*T+600*C-330*ep2)*A**6/720)); if(lat<0) Nn+=10000000; return [E,Nn]; };

window.TIFS = {}; window.getTif = async (u) => TIFS[u] ||= await GT.fromUrl(u);

window.readWin = async function (url, E, N, half, res) {
  const tif = await getTif(url); const im = await tif.getImage(); const [x0, y0] = im.getOrigin(); const [rx] = im.getResolution();
  const f = res / rx; const cx = Math.floor((E - x0) / rx), cy = Math.floor((y0 - N) / rx); const h = Math.round(half * f);
  const win = [cx - h, cy - h, cx + h + f, cy + h + f]; const r = await im.readRasters({ window: win, samples: [0] }); return { data: r[0], w: r.width, hgt: r.height, f };
};

window.findItem = async function (lat, lon, date) {
  const body = { collections: ['sentinel-2-l2a'], intersects: { type: 'Point', coordinates: [lon, lat] }, datetime: `${date}T00:00:00Z/${date}T23:59:59Z`, limit: 10 };
  const j = await fetch('https://earth-search.aws.element84.com/v1/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json());
  return (j.features || []).sort((a, b) => a.properties['eo:cloud_cover'] - b.properties['eo:cloud_cover']);
};

// Uso: await extractClean(10.833, -74.57445, '2025-09-17', 25)  -> {item, orig:{B02..B12}, dist (m), clean:{B02..B12}}
window.extractClean = async function (lat, lon, date, H = 25) {
  const items = await findItem(lat, lon, date); if (!items.length) return { err: 'sin item' };
  const it = items[0]; const zone = +String(it.properties['proj:epsg']).slice(-2); const [E, N] = utm(lat, lon, zone);
  const off = it.properties['earthsearch:boa_offset_applied'];
  const B = { blue: 'B02', green: 'B03', red: 'B04', rededge1: 'B05', nir08: 'B8A', swir16: 'B11', swir22: 'B12' };
  const g = {}; const n = 2 * H + 1;
  for (const [a, b] of Object.entries(B)) {
    const rb = it.assets[a]['raster:bands'][0];
    const W = await readWin(it.assets[a].href, E, N, H, 20); const arr = new Float32Array(n * n);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      if (W.f === 2) { let s = 0, c = 0; for (let u = 0; u < 2; u++) for (let v = 0; v < 2; v++) { const x = W.data[(2 * i + u) * W.w + 2 * j + v]; if (x > 0) { s += x; c++; } } arr[i * n + j] = c ? (s / c) * rb.scale + rb.offset + (off ? 0.1 : 0) : NaN; }
      else { const x = W.data[i * W.w + j]; arr[i * n + j] = x > 0 ? x * rb.scale + rb.offset + (off ? 0.1 : 0) : NaN; }
    }
    g[b] = arr;
  }
  const S = await readWin(it.assets.scl.href, E, N, H, 20); const scl = new Uint8Array(n * n); for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) scl[i * n + j] = S.data[i * S.w + j];
  const ok = new Uint8Array(n * n);
  for (let k = 0; k < n * n; k++) { const ndvi = (g.B8A[k] - g.B04[k]) / (g.B8A[k] + g.B04[k]); const macro = ndvi > 0 && g.B8A[k] / g.B05[k] > 1.2; ok[k] = scl[k] === 6 && !macro && g.B8A[k] < 0.1 && !isNaN(g.B04[k]) ? 1 : 0; }
  const med = (ks, b) => { const v = ks.map(k => g[b][k]).filter(x => !isNaN(x)).sort((a, b) => a - b); return v.length ? v[Math.floor(v.length / 2)] : null; };
  const nb = (i, j) => { const ks = []; for (let u = -1; u <= 1; u++) for (let v = -1; v <= 1; v++) ks.push((i + u) * n + j + v); return ks; };
  const c = H; const orig = {}; for (const b of Object.values(B)) orig[b] = med(nb(c, c), b);
  let best = null;
  for (let i = 1; i < n - 1; i++) for (let j = 1; j < n - 1; j++) { const ks = nb(i, j); if (ks.every(k => ok[k])) { const dd = Math.hypot(i - c, j - c) * 20; if (!best || dd < best.d) best = { d: dd, i, j }; } }
  const out = { item: it.id, orig, nwater: ok.reduce((a, b) => a + b, 0) };
  if (best) { out.dist = best.d; out.clean = {}; for (const b of Object.values(B)) out.clean[b] = med(nb(best.i, best.j), b); }
  return out;
};
