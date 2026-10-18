# Feature: docs-public-journey — documentación pública: el viaje de onda a dato + docs de componentes + auditoría LaTeX

Parent: user request 2026-10-18 — convertir la documentación de "para el
dueño" a "para un repositorio público", profundizando el CÓMO de cada
tecnología y agregando documentación de sistema/flujo de datos de los dos
softwares (firmware ESP32 y aplicativo de escritorio), más la auditoría
de ecuaciones según los hallazgos de LaTeX/GitHub.

## Specs

- **S1** (verbatim): "modifiques la documentación para la de un
  repositorio publico y ya no solo para mi para entender el sistema"
- **S2** (verbatim): "en las partes explicativas no solo explica cual
  tecnologia lo hace sino de que forma"
- **S3** (verbatim): "el pipeline no queda muy claro, la idea es que se
  pueda imaginar el viaje y como a partir de frecuencias de ondas u ondas
  electromageticas se puede pasar a los datos que se ven en el
  aplicativo, y la función que hace cada cosa en el sistema"
- **S4** (verbatim): "vuelve a revisar que las ecuaciones estén
  referenciadas de manera correcta segun los hallazgos que tuvimos sobre
  el latex en github"
- **S5** (verbatim): "necesito documentación del sistema y flujo de datos
  del aplicativo de escritorio y del software que se flashea en la ESP32"
- **S6** (verbatim): "explicarme a que equivale la Q en Q_k"

### Hallazgos LaTeX/GitHub vigentes (base de S4, commits 66bad8b/03d9361/7bd4333)

1. Fórmulas en bloque: fence ```math (o `$$…$$`); nunca bloques de código.
2. Matemática inline: `$…$`; nunca backticks para fórmulas.
3. Comandos no soportados por GitHub MathJax — reemplazos fijados:
   `\operatorname{…}` → `\mathrm{…}`; `\tfrac` → `\frac`.
4. `\text{…}` para palabras dentro de matemática: soportado.
5. Unidades en `\mathrm{}` (ej.: `$f_s \approx 10\ \mathrm{Hz}$`).
6. Mezcla código+matemática inline con backticks desbalanceados: prohibida
   (hallazgo nuevo de esta auditoría: la línea del `deque` en
   DATA-PIPELINE §4 quedó malformada por 7bd4333).

## Tasks

| ID | Specs | Ruta | Archivos | Commit |
|----|-------|------|----------|--------|
| T1 | S1,S2,S3 | inline (parent) | `docs/HOW-IT-WORKS.md`, `docs/DATA-PIPELINE.md` (encuadre), `README.md` (filas) | C2 |
| T2 | S5 | worker W1 (background) | `docs/FIRMWARE-ESP32.md` (nuevo) | C1 |
| T3 | S5 | worker W2 (background) | `docs/DESKTOP-APP.md` (nuevo) | C1 |
| T4 | S6 | inline (parent) | `docs/SIGNAL-MODELING.md` §2, HOW-IT-WORKS, DATA-PIPELINE + respuesta directa al usuario | C2 |
| T5 | S4 | inline (parent) | todos los `.md` (auditoría + correcciones) | C3 |
| T6 | cierre | inline (parent) | `README.md` índice, `CHANGELOG.md`, verificación estructural | C3 |

Commits (work units, rama `docs/public-journey`):
- **C1**: docs nuevos de firmware y aplicativo de escritorio (T2+T3).
- **C2**: narrativa pública + viaje + Q_k (T1+T4).
- **C3**: auditoría de ecuaciones + índice + CHANGELOG + verificación (T5+T6).

Convenciones del feature: docs explicativos en español (familia HOW-IT-WORKS/
DATA-PIPELINE), README y SIGNAL-MODELING en inglés; tono público (sin
encuadre personal "para mí"); cada afirmación verificada contra el código
(archivo + función citados); matemática según los hallazgos de arriba.

## Log

- **L1** (verbatim): "si, me gustaria que hicieras modificaciones en la
  documentación, en donde modifiques la documentación para la de un
  repositorio publico y ya no solo para mi para entender el sistema,
  ahora, en las partes explicativas no solo explica cual tecnologia lo
  hace sino de que forma, o pues en el pipeline no queda muy claro, la
  idea es que se pueda imaginar el viaje y como a partir de frecuencias
  de ondas u ondas electromagneticas se puede pasar a los datos que se
  ven en el aplicativo, y la función que hace cada cosa en el sistema,
  además vuelve a revisar que las ecuaciones estén referenciadas de
  manera correcta segun los hallazgos que tuvimos sobre el latex en
  github, además de eso tambien necesito documentación del sistema y
  flujo de datos del aplicativo de escritorio y del software que se
  flashea en la ESP32 y explicarme a que equivale la Q en Q_k"
- **L2**: Rama `docs/public-journey` creada desde master (7bd4333).
  Convención de idiomas decidida: mantener español en la familia
  explicativa (tono público, no traducir); README/SIGNAL-MODELING
  siguen en inglés.
