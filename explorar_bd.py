import os
import chromadb

# Apuntar a tu carpeta de base de datos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "base_vectores")

def ver_vector():
    # Conectar a la base de datos
    cliente = chromadb.PersistentClient(path=DB_PATH)
    coleccion = cliente.get_collection(name="conocimiento_sap")
    
    # Extraemos solo 1 documento, pidiendo explícitamente los "embeddings"
    resultados = coleccion.get(
        limit=1,
        include=["documents", "metadatas", "embeddings"]
    )
    
    # CORRECCIÓN: Validamos de forma segura para evitar el error de NumPy
    if resultados and resultados.get('embeddings') is not None and len(resultados['embeddings']) > 0:
        id_doc = resultados['ids'][0]
        texto = resultados['documents'][0]
        vector = resultados['embeddings'][0]
        
        print("="*50)
        print(f"📄 DOCUMENTO: {id_doc}")
        print(f"📝 TEXTO: {texto[:100]}...")
        print("="*50)
        print(f"🧠 EL VECTOR (La representación de la IA):")
        print(f"Cantidad de dimensiones (números): {len(vector)}")
        print("-" * 50)
        
        # Mostramos los primeros 10 números y los últimos 5
        print(f"Los primeros números:\n{vector[:10]}")
        print("...\n[Aquí van cientos de números más]\n...")
        print(f"Los últimos números:\n{vector[-5:]}")
        print("="*50)

if __name__ == "__main__":
    ver_vector()