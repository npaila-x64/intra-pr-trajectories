# Evolución intra-PR de métricas y hallazgos estáticos

Paquete de réplica **parcial** del estudio *Evolución intra-PR de métricas y hallazgos
estáticos en contribuciones de agentes de IA* (Etapa 2: diseño metodológico y resultados
preliminares). Contiene la implementación mínima que reconstruye
las trayectorias de pull requests (PRs) asociados a agentes, mide cada estado con PMD, y
analiza las tres preguntas de investigación sobre una muestra piloto de 25 PRs.

- **Versión de esta entrega:** etiqueta [`v0.2.1-etapa2`](https://github.com/npaila-x64/intra-pr-trajectories/tree/v0.2.1-etapa2)
- **Zenodo:** [10.5281/zenodo.23230281](https://doi.org/10.5281/zenodo.23230281). Reemplaza a
  `v0.2-etapa2` ([10.5281/zenodo.23229081](https://doi.org/10.5281/zenodo.23229081)), cuyo
  análisis requería repetir la extracción.

## Preguntas de investigación

- **RQ1.** ¿Cómo evolucionan el tamaño, la complejidad, y la cantidad de hallazgos de análisis
  estático a lo largo de los commits de un PR?
- **RQ2.** ¿Cómo aparecen, persisten, y desaparecen los hallazgos individuales durante el
  desarrollo de un PR?
- **RQ3.** ¿Cuánto de esa evolución queda oculto al comparar solo el estado inicial y el final
  del PR?

## Organización

```text
config/
  metricas.xml        NcssCount y CyclomaticComplexity con umbral 1 (solo métricas)
  hallazgos.xml       Las once reglas de hallazgos
scripts/
  descargar_pmd.sh    Paso 0: descarga PMD 7.28.0 y verifica su SHA-256
  seleccionar_candidatos.py   Paso 1: candidatos desde AIDev-pop
  reconstruir_trayectorias.py Paso 2: trayectorias con Git
  medir_estados.py    Paso 3: medición de cada estado con PMD
  analizar.py         Paso 4: análisis de RQ1, RQ2, y RQ3
  figura_hangar.py    Figura 1 del informe (trayectoria de Hangar#1537)
  comun.py            Filtro de archivos Java de producción
datos/
  candidatos.csv, candidatos_shas.json, seleccion_resumen.json   Salidas del paso 1
  trayectorias.json, exclusiones.csv                             Salidas del paso 2
  mediciones/         Salidas del paso 3 (métricas, hallazgos, estados, y archivos)
  resultados/         Salidas del paso 4 y planillas de auditoría
figuras/
  hangar.pdf, hangar.png      Figura 1, generada desde datos/resultados/
```

Los clones de los repositorios (`datos/repos/`, ~560 MB) y los archivos materializados de cada
estado (`datos/estados/`, ~90 MB) no se distribuyen, porque contienen código fuente completo de
proyectos de terceros bajo sus propias licencias (véase *Licencias*). El paso 3 guarda en
`datos/mediciones/` la información derivada que el análisis necesita de esos archivos: la huella
de cada estado, si cada sentencia reportada aparece intacta en los estados vecinos, y las marcas
de supresión por archivo. Por eso el análisis comienza desde los datos conservados.

## Requisitos

- Python 3.11 o superior y [uv](https://docs.astral.sh/uv/).
- Java 17 o superior para PMD (probado con OpenJDK 21).
- `git`, `curl`, `unzip`, y acceso a Hugging Face y GitHub.

```sh
uv sync
./scripts/descargar_pmd.sh
```

## Reproducción

### Desde los datos conservados (recomendado)

El análisis parte de `datos/mediciones/` y `datos/trayectorias.json`, sin repetir la extracción
ni requerir Java, PMD, o acceso a red:

```sh
uv sync
uv run python scripts/analizar.py       # RQ1–RQ3, en segundos
uv run python scripts/figura_hangar.py  # Figura 1
```

Las salidas se escriben en `datos/resultados/` y `figuras/`, y deben coincidir con las versionadas
(`git status` no muestra cambios). `analizar.py` conserva las respuestas de auditoría ya
registradas.

### Extracción completa (opcional, unos 12 minutos)

Repite la selección, la reconstrucción, y la medición, y sobrescribe `datos/`:

```sh
./scripts/descargar_pmd.sh
uv run python scripts/seleccionar_candidatos.py    # ~30 s, lee AIDev-pop desde Hugging Face
uv run python scripts/reconstruir_trayectorias.py  # ~3 min, clona 20 repositorios sin blobs
uv run python scripts/medir_estados.py             # ~8 min
```

Luego ejecute el análisis como en la sección anterior. Solo cambia `seleccion_resumen.json`, que
registra la fecha de consulta.

## Extracción y entorno

| Paso | Fuente | Fecha (UTC) |
| --- | --- | --- |
| 1. Selección | AIDev-pop en Hugging Face, revisión `37bbe153…` | 2026-10-08 03:15 |
| 2. Reconstrucción | GitHub (`git clone --filter=blob:none` y `pull/N/head`) | 2026-10-08 03:16–03:19 |
| 3. Medición | Blobs descargados desde GitHub por SHA | 2026-10-08 03:19–03:27; repetida 05:41–05:43 para agregar los datos derivados |

Los estados se identifican por SHA, por lo que una nueva extracción obtiene el mismo código
mientras los repositorios y sus referencias `pull/N/head` sigan disponibles.

Entorno de ejecución: Ubuntu 24.04.5 LTS (kernel 6.14), Python 3.14.5 gestionado con uv 0.11.19,
OpenJDK 21.0.12.1, PMD 7.28.0, y Git 2.43.0. Las versiones de las dependencias de Python están
fijadas en `uv.lock` (entre otras, pyarrow 25.0.1, fsspec 2026.9.0, y matplotlib 3.11.2).

## Resultados por pregunta

Todos los archivos están en `datos/resultados/`. `resumen.json` reúne las cifras del informe.

| Pregunta | Archivo | Contenido | En el informe |
| --- | --- | --- | --- |
| RQ1 | `rq1_series.csv` | Serie por PR y métrica, cambio neto, forma de la trayectoria, y excursiones | Tabla II, Sección IV-B |
| RQ2 | `rq2_hallazgos.csv` | Cada hallazgo seguido, con su categoría y la causa de su desaparición | Sección IV-C |
| RQ2 | `rq2_enlaces.csv` | Cada enlace entre estados consecutivos y la etapa que lo produjo | Sección IV-C |
| RQ2 | `auditoria_*.csv` | Muestras revisadas manualmente; `*_v1.csv` corresponde a la primera ronda | Sección IV-C |
| RQ3 | `rq3_pr.csv` | Por PR: hallazgos transitorios, sustituciones con conteo igual, y excursiones | Tabla II, Sección IV-D |
| RQ1–RQ3 | `figuras/hangar.pdf` | Trayectoria de tamaño y origen de los hallazgos de Hangar#1537 | Fig. 1 |

## Configuración del estudio

- **Fuente:** AIDev-pop, `hao-li/AIDev-7.6M`, revisión
  `37bbe1533e26cc1e1374917dba1186d1c8a4dc81` (v5), PRs integrados antes del 1 de abril de 2026.
- **Selección:** repositorios con Java como lenguaje principal; PRs con al menos dos commits que
  modifican archivos Java de producción (`scripts/comun.py` define las exclusiones de pruebas,
  código generado, y dependencias); historia lineal; base en la rama por defecto; orden
  aleatorio con semilla 760; 25 PRs con un máximo de cinco por repositorio.
- **Estados:** la secuencia `B → C1 → … → Cn` se obtiene de `pull/N/head`; los estados
  consecutivos con contenido idéntico en el alcance se colapsan.
- **Métricas:** NCSS de los tipos de nivel superior y suma de la complejidad ciclomática de
  métodos y constructores, con PMD 7.28.0.
- **Hallazgos:** `CognitiveComplexity`, `NPathComplexity`, `AvoidDeeplyNestedIfStmts`,
  `CollapsibleIfStatements`, `SimplifyBooleanReturns`, `ExcessiveParameterList`,
  `UnusedLocalVariable`, `UnusedPrivateField`, `UnusedFormalParameter`,
  `AvoidReassigningParameters`, y `EmptyCatchBlock`, con umbrales por defecto.
- **Emparejamiento:** exacto; misma entidad (con compatibilidad de sentencias); orden dentro de
  la entidad; movido entre archivos; y métodos renombrados. Detalles en `scripts/analizar.py`.

## Auditoría

En `auditoria_enlaces.csv` y `auditoria_desapariciones.csv`, la columna `correcto` registra la
revisión manual (`sí` o `no`). La primera ronda (`*_v1.csv`) motivó la compatibilidad de
sentencias y la detección de renombrados; la segunda ronda corresponde a los archivos actuales.

## Estado

**Implementado:** selección, reconstrucción, medición, emparejamiento, análisis de las tres
preguntas, y auditoría sobre la muestra piloto.

**Pendiente:** detectar traslados de código entre clases, validar la etapa de misma entidad con
una muestra nueva, ampliar la muestra a 100–200 PRs, y distinguir los commits del agente de los
humanos.

## Licencias

- **Código** (`scripts/`, `config/`): MIT, véase `LICENSE`.
- **Datos derivados** (`datos/`, `figuras/`): CC BY 4.0. Provienen de AIDev (CC BY 4.0) y de
  repositorios públicos de GitHub.
- **Fragmentos de código de terceros** incluidos en `datos/mediciones/hallazgos.csv` y en las
  planillas de auditoría conservan la licencia de su repositorio de origen.

