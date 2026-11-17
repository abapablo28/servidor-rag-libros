import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from server import consultar_conocimiento

def test_mcp():
    print("Iniciando prueba del tool consultar_conocimiento...")
    pregunta = "¿Qué es SAP?"
    print(f"\nPregunta a consultar: {pregunta}\n")
    
    try:
        resultado = consultar_conocimiento(pregunta, cantidad_resultados=2)
        print("RESULTADOS OBTENIDOS:\n")
        print(resultado)
    except Exception as e:
        print(f"Error al probar el tool: {e}")

if __name__ == '__main__':
    test_mcp()
