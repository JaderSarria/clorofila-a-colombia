import pandas as pd, numpy as np, re, unicodedata, os

def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower()
    return s

def ambiente(row):
    l = norm(row['lugar']); d = norm(row['departamento']); p = norm(row['proyecto'])
    if 'oceanico' in d or 'bloque' in l or 'linea base' in p or 'levantamiento' in p:
        return 'oceanico'
    if 'cienaga' in l or 'cgsm' in l or l in ('rinconada', 'buenavista', 'tasajera', 'nueva venecia') or 'centro cienaga' in l:
        return 'cienaga_laguna'
    if re.search(r'\b(rio|r\.|boca|desembocadura|cano|arroyo|bocatoma|distrito riego)\b', l) or 'boca.' in l:
        return 'rio_desembocadura'
    if 'cienaga grande' in norm(row['sector']):
        return 'cienaga_laguna'
    if 'manglar' in l:
        return 'manglar'
    if re.search(r'(bahia|puerto|muelle|marina|emisario|fondeadero)', l):
        return 'bahia_puerto'
    if 'playa' in l:
        return 'playa'
    return 'costero_otro'

def load(path=None):
    path = path or os.environ.get('CHLA_CSV') or ('800.csv' if os.path.exists('800.csv') else '../datos/originales/800.csv')
    df = pd.read_csv(path, sep='\t', encoding='utf-8-sig')
    for c in ['latitud', 'longitud']:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'))
    df['chla'] = df['concentracion'].astype(float)
    df['fecha'] = pd.to_datetime(df['fecha'])
    n0 = len(df)
    # Limpieza: valores > 1000 ug/L (15 registros de Antioquia 2020, físicamente imposibles -> error de unidades)
    df = df[df.chla <= 1000].copy()
    # Ceros = bajo límite de detección (0.07) -> LD/2
    df.loc[df.chla <= 0, 'chla'] = 0.035
    df['ambiente'] = df.apply(ambiente, axis=1)
    # Agregar réplicas de la misma estación y fecha (mediana)
    keys = ['id_estacion', 'fecha']
    g = (df.groupby(keys)
           .agg(chla=('chla', 'median'), n_rep=('chla', 'size'),
                latitud=('latitud', 'first'), longitud=('longitud', 'first'),
                lugar=('lugar', 'first'), departamento=('departamento', 'first'),
                region=('region', 'first'), sector=('sector', 'first'),
                temporada=('temporada', 'first'), metodo=('metodo', 'first'),
                ambiente=('ambiente', 'first'))
           .reset_index())
    g['y'] = np.log10(g['chla'])
    g['anio'] = g.fecha.dt.year
    g['mes'] = g.fecha.dt.month
    g['mes_sin'] = np.sin(2 * np.pi * g.mes / 12)
    g['mes_cos'] = np.cos(2 * np.pi * g.mes / 12)
    g['hora'] = g.fecha.dt.hour + g.fecha.dt.minute / 60
    g['t'] = (g.fecha - pd.Timestamp('2016-01-01')).dt.days / 365.25
    g['metodo_c'] = g.metodo.str.extract(r'(Lorenzen|Tricomatico|Korolef|Colorimetrico)')[0].fillna('otro')
    return g, n0, len(df)

if __name__ == '__main__':
    g, n0, n1 = load()
    print(n0, n1, len(g))
    print(g.ambiente.value_counts())
    print(g.groupby('ambiente').chla.median())
