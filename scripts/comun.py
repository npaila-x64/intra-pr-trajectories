"""Definiciones compartidas entre los pasos de la implementación mínima."""
import re

# Rutas excluidas del alcance: pruebas, código generado, y dependencias incluidas.
_EXCLUIDAS = re.compile(
    r'(^|/)(src/test|src/it|src/integrationTest|test|tests|testing|generated|'
    r'generated-sources|build|target|out|vendor|third_party|thirdparty)(/|$)',
    re.IGNORECASE)
_NOMBRE_PRUEBA = re.compile(r'(Test|Tests|IT|TestCase)\.java$')


def es_java_produccion(ruta: str) -> bool:
    """True si la ruta corresponde a un archivo Java de producción."""
    return (ruta.endswith('.java')
            and not _EXCLUIDAS.search(ruta)
            and not _NOMBRE_PRUEBA.search(ruta.rsplit('/', 1)[-1]))
