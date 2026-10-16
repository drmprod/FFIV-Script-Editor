# ff4_editor_vwf

Editor de texto en PySide6 para la traducción de Final Fantasy IV (SNES), pensado para el flujo del desensamblado [everything8215/ff4](https://github.com/everything8215/ff4). Edita el JSON que genera `make rip`, muestra cada cadena como una tarjeta pintada con la **fuente de ancho variable del juego** (`font.png`) y calcula en vivo cuántos bytes ocupa el texto (con DTE) frente a la capacidad de su sección.

## Requisitos

- Python 3.10 o superior
- PySide6, Pillow, fonttools (ver `requirements.txt`)
- Opcional: `make` (botón *Compilar*) y Mesen en el `PATH` (botón *Mesen*)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
python3 main.py ../ff4-main/ff4-es-data.json
python3 main.py -v ff4-es-data.json      # -v imprime información de carga de secciones
```

Flujo de trabajo:

1. `make rip` genera `ff4-xx-data.json` en el repo del desensamblado.
2. Abrir el JSON en el editor (argumento de línea de comandos o botón *Open JSON*), editar y *Save*.
3. *Compilar* ejecuta `make ff4-es` en el directorio del JSON y muestra la salida en una ventana.
4. *Mesen* abre `rom/ff4-es.sfc` (o `.spc`/`.smc`) que está junto al JSON.

`Open ff4-es-data.json in editor.sh` y los `.desktop` son lanzadores de ejemplo; las rutas absolutas de los `.desktop` son de la máquina del autor y hay que adaptarlas.

### Archivos que busca junto al JSON

| Archivo | Para qué | Si falta |
|---|---|---|
| `ff4-xx.lnk` (mismo prefijo que `ff4-xx-data.json`) | capacidad en bytes de cada sección | usa `assembly[sección].range` del JSON |
| `font.png` (también en `gfx/`, `tools/` o el directorio padre) | medir y dibujar en píxeles con la fuente del juego | modo monoespaciado por caracteres |

## Interfaz

- Barra lateral con las secciones; cada sección muestra tarjetas con el texto, el número de entrada (`#NNN`), una barra de presupuesto de bytes y avisos de línea larga.
- Clic en una tarjeta para editarla. Los códigos de control (`\wait[2x4]`, `\char03`…) se resaltan; `\charNN` se muestra como `{Nombre}` según `characterNames`. Una línea de guiones representa `\line`.
- Deshacer/Rehacer: `Ctrl+Z` / `Ctrl+Shift+Z`. Cortar/copiar/pegar/seleccionar todo desde la barra o con atajos.
- *Ir a #* salta a una entrada; el selector de mapas filtra `mapDialog`; el campo *Filter strings…* filtra tarjetas.
- *⚙ View* ajusta tamaño de tarjeta, fuente, límites de línea y modo VWF, globalmente o solo para la sección actual.

## Configuración

Se guarda en `ff4_editor/ff4_editor_config.json` (ignorado por git) en tres capas: `global`, por archivo (`files[<nombre del json>]`) y overrides por sección (`section_overrides`). Las claves válidas están en `ff4_editor/typed_config.py` (`ConfigKey`).

## Estructura

```
main.py                  punto de entrada (argparse + QApplication)
ff4_editor/
  ui_mainwindow.py       ventana principal, barra de herramientas, undo, compilar/Mesen
  ui_build_dialog.py     ventana de compilación (QProcess)
  ui_view_dialog.py      diálogo View
  config.py              EditorConfig (estado efectivo)
  typed_config.py        ConfigKey, EditorSettings, SectionOverride, validación
  config_manager.py      capas global / archivo / sección y persistencia
  constants.py           secciones, límites VWF, hoja de estilo
  errors.py              excepciones, logging, carga/guardado seguro de JSON
  model/
    json_model.py        FF4Model: datos, dirty tracking, capacidades, señales
    encoding.py          costo en bytes de una cadena (DTE, códigos de control)
    linker.py            lectura del .lnk de ld65 para las capacidades
    commands.py          QUndoCommand de edición de entradas
  util/
    text_processing.py   JSON <-> texto de pantalla, nombres de personaje, reflow
    vwf_font.py          fuente de ancho variable a partir de font.png (+ TTF en memoria)
  widgets/
    card_canvas.py       lienzo que pinta todas las tarjetas
    card_editor.py       QPlainTextEdit superpuesto sobre la tarjeta activa
    card_layout.py       geometría de tarjetas
    card_data.py         datos de una tarjeta
    highlighter.py       resaltado de sintaxis
    vwf_painter.py       dibujo de texto con la fuente del juego
tests/                   pytest (ver abajo)
```

## Tests

```bash
pip install -r requirements-dev.txt
python3 -m pytest
```

Corren offscreen (`QT_QPA_PLATFORM=offscreen`) y con datos sintéticos: un `font.png`, un JSON y un `.lnk` mínimos generados en `tests/conftest.py`. No hace falta tener el JSON real ni la ROM.

- Los tests marcados `xfail(strict=True)` documentan **bugs abiertos** (cada uno cita su sección del `todo.md`). Al corregir uno, el test pasa a XPASS y falla a propósito: quitá el marcador `xfail` para convertirlo en test de regresión.
- Prueba opcional con datos reales (round trip JSON → pantalla → JSON sobre todas las cadenas):

```bash
FF4_DATA_JSON=../ff4-main/ff4-es-data.json python3 -m pytest tests/test_json_model.py -k real
```

## Limitaciones conocidas

Ver `todo.md`. Hoy lo más importante: la capacidad que sale del `.lnk` es una aproximación (los segmentos sin `start=` se suponen contiguos), el guardado del JSON no es atómico y no se hace copia `.bak`.
