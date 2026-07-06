import chromadb
import os

# Conectar a la base de datos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "base_vectores")
chroma_client = chromadb.PersistentClient(path=DB_PATH)
collection = chroma_client.get_collection(name="conocimiento_sap")

total_fragmentos = collection.count()
print(f"Analizando {total_fragmentos} fragmentos en lotes para evitar sobrecarga...")

fuentes = set()
lote_size = 5000  # Extraer de 5000 en 5000 para no saturar la memoria

# Bucle para recorrer toda la base de datos por partes
for offset in range(0, total_fragmentos, lote_size):
    print(f"Leyendo fragmentos del {offset} al {min(offset + lote_size, total_fragmentos)}...")
    
    # Obtener solo el lote actual
    resultados = collection.get(
        include=["metadatas"],
        limit=lote_size,
        offset=offset
    )
    
    # Extraer los nombres únicos de los archivos de este lote
    for meta in resultados['metadatas']:
        if meta and 'fuente' in meta:
            fuentes.add(meta['fuente'])

print("\n✅ LIBROS ENCONTRADOS EN LA BASE DE DATOS:")
for f in sorted(fuentes):
    print(f"- {f}")