import os
import sys
import warnings
import zipfile
import urllib.request

# 1. Apagar todos los mensajes y advertencias para no romper la comunicacion JSON
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
import logging
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

import chromadb
from sentence_transformers import SentenceTransformer

# Centralizar las rutas del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "base_vectores")
ZIP_PATH = os.path.join(BASE_DIR, "base_vectores.zip")

# ACA DEBES PONER EL LINK DIRECTO DE DESCARGA DE TU ZIP
URL_DEL_ZIP = "https://silverconsultingsas-my.sharepoint.com/:u:/g/personal/juan_metaute_silverconsulting_com_co/IQBlsM9KzTjNTZBn3xqMJIrOAeYiB967GCMxUUdn-vSAv_E?download=1"

def asegurar_base_datos():
    """Verifica si la base de datos existe. Si no, la descarga y extrae automaticamente."""
    if not os.path.exists(DB_PATH):
        # Usamos file=sys.stderr para que estos textos no rompan el protocolo MCP
        print("Base de datos vectorial no encontrada.", file=sys.stderr)
        print("Descargando conocimientos desde la nube (esto puede tardar unos minutos)...", file=sys.stderr)
        
        try:
            urllib.request.urlretrieve(URL_DEL_ZIP, ZIP_PATH)
            print("Descarga completada. Extrayendo manuales...", file=sys.stderr)
            
            with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
                zip_ref.extractall(BASE_DIR)
                
            os.remove(ZIP_PATH)
            print("Base de conocimientos inicializada y lista para usarse.", file=sys.stderr)
            
        except Exception as e:
            print(f"Error al descargar o extraer la base de datos: {e}", file=sys.stderr)
            print("Asegurate de que el enlace de descarga directa sea valido.", file=sys.stderr)
            if os.path.exists(ZIP_PATH):
                os.remove(ZIP_PATH)

# 2. Ejecutar la descarga ANTES de intentar conectar
asegurar_base_datos()

# Inicializar el modelo (sin hacer print)
model = SentenceTransformer("all-MiniLM-L6-v2")

# Inicializar el cliente persistente de ChromaDB
chroma_client = chromadb.PersistentClient(path=DB_PATH)

# Obtener o crear la coleccion donde se guardara el conocimiento
collection = chroma_client.get_or_create_collection(name="conocimiento_sap")

def agregar_fragmentos(textos, metadatos, ids):
    """Convierte bloques de texto en vectores numericos y los guarda en la BD."""
    embeddings = model.encode(textos).tolist()
    collection.add(
        documents=textos,
        embeddings=embeddings,
        metadatas=metadatos,
        ids=ids
    )

def buscar_similitud(consulta, top_k=3):
    """Busca los fragmentos mas parecidos semanticamente a la consulta."""
    query_embedding = model.encode([consulta]).tolist()
    resultados = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k
    )
    return resultados