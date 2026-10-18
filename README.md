# ff4_editor_vwf

Editor de texto en PySide6 para la traducción de Final Fantasy IV (SNES), pensado para el flujo del desensamblado [everything8215/ff4](https://github.com/everything8215/ff4). Edita el JSON que genera `make rip`, muestra cada cadena como una tarjeta pintada con la **fuente de ancho variable del juego** (`font.png`) y calcula en vivo cuántos bytes ocupa el texto (con DTE) frente a la capacidad de su sección.

## Requisitos

- Python 3.10 o superior
- PySide6, Pillow, fonttools (ver `requirements.txt`)
- Opcional: `make` (*Compilar › Compilar*) y Mesen en el `PATH` (*Compilar › Ejecutar en Mesen*)

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
2. Abrir el JSON en el editor (argumento de línea de comandos o *Archivo › Abrir*, `Ctrl+O`), editar y guardar con `Ctrl+S`.
3. *Compilar › Compilar* (`Ctrl+B`) ejecuta `make ff4-es` en el directorio del JSON y muestra la salida en una ventana.
4. *Ejecutar en Mesen* (`F5`) abre `rom/ff4-es.sfc` (o `.spc`/`.smc`) que está junto al JSON.

`Open ff4-es-data.json in editor.sh` y los `.desktop` son lanzadores de ejemplo; las rutas absolutas de los `.desktop` son de la máquina del autor y hay que adaptarlas.

### Archivos que busca junto al JSON

| Archivo | Para qué | Si falta |
|---|---|---|
| `ff4-xx.lnk` (mismo prefijo que `ff4-xx-data.json`) | capacidad en bytes de cada sección | usa `assembly[sección].range` del JSON |
| `font.png` (también en `gfx/`, `tools/` o el directorio padre) | medir y dibujar en píxeles con la fuente del juego | modo monoespaciado por caracteres |

## Interfaz

La interfaz está en español y sigue las convenciones de escritorio con el tema por defecto de Qt.

- Barra de menús: *Archivo* (Abrir, Abrir reciente, Guardar, Salir), *Edición* (Deshacer/Rehacer, Cortar/Copiar/Pegar, Seleccionar todo, Insertar salto de línea, Centrar, Buscar, Ir a…, Preferencias), *Ver* (barra de secciones), *Compilar*, *Ayuda*.
- Barra de herramientas con Abrir, Guardar, Deshacer, Rehacer, Compilar y Ejecutar en Mesen, y el filtro de cadenas a la derecha.
- Lista de secciones a la izquierda: negrita si tiene cambios sin guardar, icono de aviso por encima del 90 % de la capacidad e icono de error si se excede.
- Barra de estado: entradas mostradas, bytes libres y barra de uso de la sección.
- El título muestra `archivo[*]` (con `*` cuando hay cambios sin guardar); al cerrar o abrir otro archivo se pregunta si guardar.
- La ventana recuerda tamaño, posición, divisor y archivos recientes (`QSettings`).
- Clic en una tarjeta para editarla. Los códigos de control (`\wait[2x4]`, `\char03`…) se resaltan; `\charNN` se muestra como `{Nombre}`. Una línea punteada representa `\line` (cuenta como un solo carácter: Backspace/Supr la borran de una vez). Para el salto de línea automático, cada `{Nombre}` se mide como el peor caso (6 caracteres de la letra más ancha, «WWWWWW»), porque el jugador puede renombrar al personaje; si el nombre real es más largo que eso, se usa el real.

Atajos: `Ctrl+H` buscar y reemplazar en todas las secciones, `Alt+↓`/`Alt+↑` tarjeta siguiente/anterior (`Esc` cierra el editor), `Ctrl+O` abrir, `Ctrl+S` guardar, `Ctrl+Z`/`Ctrl+Shift+Z` deshacer/rehacer, `Ctrl+X/C/V/A`, `Ctrl+F` filtrar, `Ctrl+G` ir a entrada o mapa, `Ctrl+Return` insertar salto de línea, `Ctrl+E` centrar, `Ctrl+B` compilar, `F5` Mesen, `F9` barra de secciones, `Ctrl+Q` salir (o el estándar de la plataforma), Preferencias (estándar de la plataforma o `Ctrl+,`).

*Edición › Preferencias* ajusta tarjetas, fuente y modo monoespaciado o VWF, para todas las secciones o solo la actual (con botón para quitar los ajustes propios de la sección).

### Buscar y reemplazar

*Edición › Buscar y reemplazar…* (`Ctrl+H`) busca en el texto guardado en el JSON (así también se encuentran `\wait`, `\char03`…), en todas las secciones o solo en la actual, con opciones de mayúsculas y expresión regular (`\1` en el reemplazo). Doble clic en un resultado abre esa tarjeta. *Reemplazar todo* es un único paso de deshacer.

## Desarrollo

```bash
pip install -r requirements-dev.txt
make check      # ruff + mypy + pytest (offscreen), lo mismo que corre el CI
make format     # ruff format
```

## Configuración

Se guarda en `ff4_editor/ff4_editor_config.json` (ignorado por git) en tres capas: `global`, por archivo (`files[<nombre del json>]`) y overrides por sección (`section_overrides`). Las claves válidas están en `ff4_editor/typed_config.py` (`ConfigKey`).

## Estructura

```
main.py                  punto de entrada (argparse + QApplication)
ff4_editor/
  ui_mainwindow.py       ventana principal, barra de herramientas, undo, compilar/Mesen
  ui_build_dialog.py     ventana de compilación (QProcess)
  ui_view_dialog.py      diálogo de preferencias
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

## Idioma de la interfaz

Los textos del editor están en español (idioma fuente) y se traducen con el sistema de Qt (`tr`). El idioma se elige en Edición → Preferencias → «Idioma de la interfaz» (Automático / Español / English) y se aplica al reiniciar.

Para agregar un idioma: crear `ff4_xx.ts` (copiando `ff4_en.ts`), agregar el código a `LANGUAGES` en `ff4_editor/i18n.py` y compilar con `make i18n` (hay que extender el target para el nuevo `.ts`). Al agregar textos nuevos se escriben con `tr("…")` (variables con `{nombre}` y `.format`, nunca f-strings) y se corre `make i18n`; `tests/test_i18n.py` falla si queda algo sin traducir. Requiere `pyside6-lupdate` y `pyside6-lrelease` (vienen con PySide6).
