import sys
import json
sys.stdout.reconfigure(encoding='utf-8')

from server import consultar_conocimiento

resultado = consultar_conocimiento('facturacion', 1)
print(resultado)
