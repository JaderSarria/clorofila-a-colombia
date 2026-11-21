# Preparación de los datos

Scripts originales con los que se construyó `datos/tabla_modelo.csv.gz`. Se incluyen como registro del
procedimiento: dependen de archivos intermedios y de descargas (Earth Engine, Earth Search, NASA POWER, GloFAS,
GLORIA) que no están en el repositorio, así que no se ejecutan de corrido. Para entrenar o validar el modelo no
hace falta correrlos: la tabla ya está lista.

| Script | Qué hace |
|---|---|
| `prep.py` | Limpieza de la clorofila-a de REDCAM y clasificación de estaciones por tipo de ambiente. |
| `1_extraer_satelite_gee.py` | Emparejamiento de los muestreos con Sentinel-2 en Google Earth Engine. |
| `sat_extract.py` | Extracción de la ventana 3 × 3 de Sentinel-2 L2A desde Earth Search (AWS). |
| `qc_exp.py` | Variables de calidad del píxel (coeficientes de variación, píxeles de agua, NDCI 5 × 5). |
| `gloria.py` | Modelo de apoyo entrenado con la base GLORIA convertida a bandas de Sentinel-2. |
| `hidro.py` | Clima (NASA POWER) y caudales de seis ríos (GloFAS-ERA5). |
| `navegador/pixel_agua_limpia_navegador.js` | Busca el píxel de agua limpia más cercano (≤ 500 m) en la misma imagen. |
| `navegador/descarga_l1c_navegador.js`, `acolite/` | Descarga de escenas L1C y corrección atmosférica con ACOLITE (prueba; no forma parte del modelo final). |
