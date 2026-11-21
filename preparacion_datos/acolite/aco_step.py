import os, json, time, glob, tarfile, subprocess, shutil, numpy as np, netCDF4, sys
T0 = time.time(); BUDGET = float(sys.argv[1]) if len(sys.argv) > 1 else 34
H = os.path.expanduser('~'); DL = H + '/mnt/Downloads'; OUTDIR = H + '/mnt/Documents/clorofila_satelite'
os.makedirs(OUTDIR, exist_ok=True); RES = OUTDIR + '/acolite_rrs.csv'; ST = H + '/aco_state.json'
st = json.load(open(ST)) if os.path.exists(ST) else {'tars_done': [], 'cur': None}
def save(): json.dump(st, open(ST, 'w'))
# identificar archivos .tmp
for f in glob.glob(DL + '/*.tmp'):
    try:
        with open(f, 'rb') as fh: head = fh.read(600)
    except Exception: continue
    if head.startswith(b'[{"l2a"'): os.rename(f, DL + '/acolite_jobs.json'); continue
    if head[257:262] == b'ustar':
        name = head[345:500].split(b'\0')[0].decode() or head[:100].split(b'\0')[0].decode()
        safe = name.split('/')[0]
        if safe.endswith('.SAFE'):
            dst = DL + '/' + safe.replace('.SAFE', '.tar')
            if os.path.getsize(f) > 1e6 and not os.path.exists(dst) and time.time() - os.path.getmtime(f) > 3: os.rename(f, dst)
jobs = {j['name']: j for j in json.load(open(DL + '/acolite_jobs.json')) if j['name']}
BANDS = ['Rrs_443', 'Rrs_492', 'Rrs_560', 'Rrs_665', 'Rrs_704', 'Rrs_740', 'Rrs_783', 'Rrs_833', 'Rrs_865', 'Rrs_1614', 'Rrs_2202']
if not os.path.exists(RES): open(RES, 'w').write('k,escena,cluster,aot550,modelo,npix,flag_c,' + ','.join(BANDS) + '\n')
def left(): return BUDGET - (time.time() - T0)
while left() > 6:
    if st['cur'] is None:
        cand = [t for t in sorted(glob.glob(DL + '/S2*_MSIL1C_*.tar')) if os.path.basename(t) not in st['tars_done']]
        if not cand:
            if left() > 25:
                time.sleep(3)
                for f in glob.glob(DL + '/*.tmp'):
                    try:
                        with open(f, 'rb') as fh: head = fh.read(600)
                        if head[257:262] == b'ustar':
                            safe2 = (head[345:500].split(b'\0')[0].decode() or head[:100].split(b'\0')[0].decode()).split('/')[0]
                            dst = DL + '/' + safe2.replace('.SAFE', '.tar')
                            if safe2.endswith('.SAFE') and not os.path.exists(dst) and time.time() - os.path.getmtime(f) > 3: os.rename(f, dst)
                    except Exception: pass
                continue
            print('SIN_TARS_PENDIENTES'); break
        tar = cand[0]; safe = os.path.basename(tar).replace('.tar', '.SAFE')
        if safe not in jobs: st['tars_done'].append(os.path.basename(tar)); save(); continue
        shutil.rmtree(H + '/l1c', ignore_errors=True); os.makedirs(H + '/l1c')
        with tarfile.open(tar) as tf: tf.extractall(H + '/l1c')
        S = jobs[safe]['samples']; cl = {}
        for k, lon, lat in S: cl.setdefault((round(lat / 0.12), round(lon / 0.12)), []).append([k, lon, lat])
        st['cur'] = {'tar': os.path.basename(tar), 'safe': safe, 'clusters': list(cl.values()), 'i': 0}; save()
        print('extraido', safe, len(S), 'muestras', len(cl), 'grupos', round(time.time() - T0, 1)); continue
    c = st['cur']
    if c['i'] >= len(c['clusters']):
        st['tars_done'].append(c['tar']); st['cur'] = None; save(); shutil.rmtree(H + '/l1c', ignore_errors=True); print('escena lista', c['safe']); continue
    if left() < 20: break
    idxs = list(range(c['i'], min(c['i'] + 2, len(c['clusters']))))
    procs = []
    for ii in idxs:
        grp = c['clusters'][ii]; la = [g[2] for g in grp]; lo = [g[1] for g in grp]
        lim = '{:.4f},{:.4f},{:.4f},{:.4f}'.format(min(la) - 0.03, min(lo) - 0.03, max(la) + 0.03, max(lo) + 0.03)
        out = H + '/aco_out%d' % (ii % 2); shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
        sett = [x for x in open(H + '/aco_settings.txt').read().split('\n') if not x.startswith('limit=')] + ['limit=' + lim]
        sf = H + '/aco_set_run%d.txt' % (ii % 2); open(sf, 'w').write('\n'.join(sett))
        procs.append((ii, grp, out, subprocess.Popen([H + '/acolite_py_linux/dist/acolite/acolite', '--cli', '--settings', sf, '--inputfile', H + '/l1c/' + c['safe'], '--output', out], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)))
    for ii, grp, out, p in procs:
        try: p.wait(timeout=max(3, left() - 1))
        except subprocess.TimeoutExpired: p.kill()
    if left() < 1: break
    for ii, grp, out, p in procs:
        l2w = glob.glob(out + '/*L2W.nc'); rows = []
        if l2w:
            d = netCDF4.Dataset(l2w[0]); lat = d['lat'][:]; lon = d['lon'][:]
            aot = d.getncattr('ac_aot_550') if 'ac_aot_550' in d.ncattrs() else ''; mod = d.getncattr('ac_model') if 'ac_model' in d.ncattrs() else ''
            fl = d['l2_flags'][:] if 'l2_flags' in d.variables else None
            arrs = {b: np.ma.filled(d[b][:].astype(float), np.nan) for b in BANDS if b in d.variables}
            for k, lo_, la_ in grp:
                dd = (lat - la_) ** 2 + ((lon - lo_) * np.cos(np.radians(la_))) ** 2
                i, j = np.unravel_index(np.argmin(dd), lat.shape)
                if dd[i, j] > (0.0006) ** 2 * 4 or i < 1 or j < 1 or i >= lat.shape[0] - 1 or j >= lat.shape[1] - 1: continue
                win = (slice(i - 1, i + 2), slice(j - 1, j + 2))
                ok = np.ones((3, 3), bool)
                vals = []
                for b in BANDS:
                    a = arrs.get(b); v = np.nanmedian(np.where(ok, a[win], np.nan)) if (a is not None and ok.any()) else np.nan
                    vals.append('' if not np.isfinite(v) else '{:.6f}'.format(v))
                rows.append([k, c['safe'][:60], ii, aot, mod, int(ok.sum()), int(fl[i, j]) if fl is not None else ''] + vals)
            d.close()
        with open(RES, 'a') as fh:
            for rr in rows: fh.write(','.join(str(x) for x in rr) + '\n')
        print('grupo', ii + 1, '/', len(c['clusters']), 'muestras', len(rows), 'ok' if l2w else 'SIN L2W', round(time.time() - T0, 1))
    c['i'] = idxs[-1] + 1; save()
print('estado:', len(st['tars_done']), 'escenas listas; actual:', st['cur']['safe'][:40] if st['cur'] else None, '; filas:', sum(1 for _ in open(RES)) - 1)
