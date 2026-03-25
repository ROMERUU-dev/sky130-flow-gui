# Guia Detallada de Simulacion y Visualizacion

Esta guia describe paso a paso como usar la pestaña de simulacion del proyecto y explica que hace cada control.

## 1. Flujo recomendado

1. Carga un netlist con `Browse` o crea uno con `Pegar netlist`.
2. Revisa o edita el texto en `Netlist Editor` si hace falta.
3. Elige el tipo de analisis en `Simulation Setup`.
4. Ajusta probes, temperatura, modo de guardado y parametros del analisis.
5. Ejecuta con `Run`.
6. Revisa la grafica principal, las mediciones y la grafica inferior.
7. Si quieres volver a una corrida anterior, usa `Previous simulations` y `Load Previous`.

## 2. Cargar o crear un netlist

### `Browse`

Abre un archivo `.spice`, `.sp` o `.cir` ya existente.

### `Pegar netlist`

Abre un dialogo para pegar texto SPICE.

- `Nombre`: nombre base del archivo que se va a guardar.
- El contenido se guarda automaticamente en `runs/netlists` o `workspace/netlists`.
- El archivo guardado se carga como netlist actual.

Importante:

- Pega solo texto SPICE valido.
- No pegues instrucciones en lenguaje natural debajo del netlist.
- Si pegas comentarios, usa lineas que empiecen con `*`.

## 3. Seccion `Simulation Setup`

### `Type`

Selecciona el analisis principal:

- `Transient`: forma de onda en el tiempo.
- `AC`: barrido en frecuencia.
- `DC`: barrido de una fuente o parametro DC.
- `Operating Point`: punto de operacion `.op`.

### `Save mode`

Controla que variables se guardan en el archivo `.raw`:

- `All signals`: guarda todo lo que ngspice entregue.
- `Selected probes only`: guarda solo los probes configurados en `Probe Points`.

Recomendacion:

- Usa `All signals` cuando estas explorando.
- Usa `Selected probes only` cuando el circuito es grande y quieres archivos mas ligeros.

### `Temperature (C)`

Si lo llenas, la app agrega `.temp`.

Ejemplos:

- `27`
- `85`
- `-40`

### Parametros de `Transient`

- `Step`: paso de simulacion deseado.
- `Stop`: tiempo final.
- `Start`: tiempo inicial opcional.
- `Use UIC`: agrega `uic` a `.tran`.

Ejemplo util para una senal de 1 kHz:

- `Step`: `10u`
- `Stop`: `5m`
- `Start`: `0`

### Parametros de `AC`

- `Sweep`: `dec`, `lin` u `oct`
- `Points/dec`: densidad de barrido
- `Start freq`
- `Stop freq`

### Parametros de `DC`

- `Source`: nombre de la fuente a barrer, por ejemplo `V1`
- `Start`
- `Stop`
- `Step`

### `Operating Point`

Corre `.op` para calcular un estado DC unico.

Importante:

- En `.op` no hay forma de onda en el tiempo.
- La grafica superior puede verse como una sola muestra o una linea fija.
- La grafica inferior de espectro no aplica a `.op`.

## 4. `Probe Points`

Sirve para indicar nodos o expresiones que quieres guardar o priorizar.

Puedes:

- elegir nodos detectados automaticamente
- escribir expresiones manuales como `v(out)` o `i(v1)`

Botones:

- `Add Probe Point`: agrega una fila nueva
- `Refresh Points`: relee el netlist y vuelve a detectar nodos

## 5. `Netlist Editor`

Muestra una copia editable del netlist para simulacion.

Tambien tiene:

- `Extra Directives`: para agregar lineas como `.meas`, `.param`, `.ic`, `.nodeset`, etc.

La app genera un archivo nuevo `*_generated.spice` en cada corrida. El original no se sobrescribe.

## 6. Graficas y visualizacion

La app ya no separa `Simulation` y `Visualization` en subpestañas. Todo aparece en una sola vista con scroll.

## 7. Grafica superior

La grafica superior es el visor principal de formas de onda.

### Controles principales

- `Signal`: selecciona la senal principal.
- `X scale`: zoom horizontal.
- `Y scale`: zoom vertical.
- `Reset View`: reencuadra la vista.
- `Reset Scale`: regresa ambos escalados a `1.0`.
- `Overlay`: permite superponer varias senales.
- `Clear Overlay`: limpia las superposiciones.
- `Export PNG`
- `Export SVG`

### Overlay de varias senales

Sirve para comparar puntos como `p5`, `p2`, `p3`, `p4`.

Flujo:

1. Elige una senal principal en `Signal`.
2. Pulsa `Overlay`.
3. Marca las senales adicionales.
4. Acepta.

La grafica dibuja todas con colores distintos y agrega leyenda.

### Resumen inferior del visor

Debajo de la grafica aparece un resumen con:

- senales visibles
- rango X actual del conjunto
- rango Y total visible

Esto es util para confirmar que si existe excursion vertical aunque la vista se vea comprimida.

## 8. Grafica inferior

La grafica inferior es el espectro en frecuencia calculado a partir de la senal seleccionada.

### Cuando funciona

Funciona sobre todo con analisis de tiempo (`Transient`) porque calcula un espectro tipo FFT a partir de la forma de onda.

### Cuando no aplica

No suele ser util para:

- `Operating Point`
- barridos que no son dominio del tiempo
- senales con muy pocas muestras

### `Visualization Options`

- `Spectrum`
  - `Auto`: muestra espectro cuando hay datos validos
  - `Show`: fuerza mostrarlo si hay datos
  - `Hide`: lo oculta
- `Spectrum X axis`
  - `Linear Hz`
  - `Log Hz`

## 9. Mediciones

La seccion `Measurements` calcula automaticamente:

- Min
- Max
- Mean
- RMS
- Peak-to-peak
- Amplitude
- Frequency
- Period
- Phase

### `Signal`

Senal a usar para las mediciones.

### `Phase reference`

Referencia para el calculo de fase cuando aplica.

## 10. Historial de simulaciones

La app guarda cada corrida en una subcarpeta con fecha, hora y nombre del netlist.

Ejemplo:

- `workspace/results/20260323_095520_mi_netlist/`
- `workspace/logs/20260323_095520_mi_netlist/`

### Controles

- `Previous simulations`: lista archivos `.raw` anteriores
- `Load Previous`: carga la corrida elegida
- `Refresh History`: vuelve a escanear resultados

## 11. Exportacion para reportes

### `Export PNG`

Exporta la grafica con fondo blanco y resolucion alta, util para PDF.

### `Export SVG`

Exporta en formato vectorial para documentos escalables.

Recomendacion:

- Usa `SVG` si lo vas a insertar en documentos tecnicos o presentaciones.
- Usa `PNG` si lo vas a pegar en un reporte rapido o una plantilla que no maneje bien SVG.

## 12. Problemas comunes

### La grafica superior se ve plana

Causas tipicas:

- estas en `.op`
- el `Stop` es demasiado corto para la frecuencia usada
- estas viendo una senal constante como alimentacion o tierra

Solucion:

- usa `Transient`
- aumenta `Stop`
- elige `v(out)`, `v(in)` u otra senal dinamica

### La grafica inferior no aparece

Causas tipicas:

- la simulacion no es transiente
- no hay suficientes muestras
- `Spectrum` esta en `Hide`

### `Load Previous` no carga nada

Revisa:

- que exista al menos un `.raw`
- que la simulacion no haya fallado
- que el archivo de historial seleccionado corresponda a una corrida valida

## 13. Recomendaciones practicas

### Para empezar rapido

Usa:

- `Type`: `Transient`
- `Save mode`: `All signals`
- `Step`: `10u`
- `Stop`: `5m`
- `Start`: `0`

### Para proyectos grandes

Usa:

- `Save mode`: `Selected probes only`
- agrega solo nodos importantes en `Probe Points`

### Para comparar salidas

Usa:

- una senal principal
- `Overlay` para superponer el resto
- `Export SVG` para documentar el resultado

## 14. Que genera la app en cada corrida

Por cada corrida, la app crea:

- un netlist generado `*_generated.spice`
- un raw `*.raw`
- un log `*_ngspice.log`

El archivo generado es el que realmente corre ngspice, no necesariamente el netlist original sin editar.

## 15. Consejo final

Si una grafica no se ve como esperas, primero revisa:

1. tipo de analisis
2. tiempo de simulacion o barrido
3. senal seleccionada
4. `Generated Netlist`
5. log de ngspice

Con esos cinco puntos casi siempre se encuentra la causa rapidamente.
