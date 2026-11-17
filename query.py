import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from server import consultar_conocimiento


def run_query():
    pregunta = (
        "¿Cómo es la mejor manera de hacer un rastreo de objetos y limpieza si solo tengo el código WRICEF "
        "y la idea es hacer depuración para migrar a S/4HANA? Mejores prácticas para rastrear código Z, "
        "limpiar y preparar migración a S4HANA."
    )
    print(f"Consultando: {pregunta}\n")
    resultado = consultar_conocimiento(pregunta, cantidad_resultados=4)
    print("Resultado obtenido:\n", resultado[:500], "...")


if __name__ == "__main__":
    run_query()
