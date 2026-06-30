import os
# pyrefly: ignore [missing-import]
from pypdf import PdfReader
from bd_config import agregar_fragmentos, BASE_DIR

PDF_DIR = os.path.join(BASE_DIR, "pdfs")

def fragmentar_texto(texto, tamano_chunk=800, traslape=150):
    """Divide el texto en bloques pequeños manteniendo un margen de superposición."""
    chunks = []
    inicio = 0
    while inicio < len(texto):
        fin = inicio + tamano_chunk
        chunks.append(texto[inicio:fin])
        inicio += (tamano_chunk - traslape)
    return chunks

def procesar_pdfs_locales():
    if not os.path.exists(PDF_DIR):
        print(f"❌ La carpeta {PDF_DIR} no existe. Por favor, créala.")
        return

    print("🚀 Iniciando el procesamiento e indexación de PDFs...")
    
    # Recorrer la carpeta buscando documentos
    for filename in os.listdir(PDF_DIR):
        if filename.lower().endswith('.pdf'):
            filepath = os.path.join(PDF_DIR, filename)
            print(f"📖 Extrayendo texto de: {filename}")
            
            try:
                reader = PdfReader(filepath)
                texto_completo = ""
                for pagina in reader.pages:
                    texto_pag = pagina.extract_text()
                    if texto_pag:
                        texto_completo += texto_pag + "\n"
                
                # Fragmentar el documento completo en bloques semánticos
                chunks = fragmentar_texto(texto_completo)
                
                textos_db = []
                metadatos_db = []
                ids_db = []
                
                for i, chunk in enumerate(chunks):
                    textos_db.append(chunk)
                    metadatos_db.append({"fuente": filename, "bloque": i})
                    ids_db.append(f"{filename}_chunk_{i}")
                
                # Guardar en la base de datos vectorial si hay datos
                if textos_db:
                    agregar_fragmentos(textos_db, metadatos_db, ids_db)
                    print(f"✅ Indexados con éxito {len(textos_db)} fragmentos de '{filename}'")
                    
            except Exception as e:
                print(f"❌ Error al procesar el archivo {filename}: {e}")

if __name__ == "__main__":
    procesar_pdfs_locales()
    print("\n🎉 ¡Proceso RAG finalizado! Tu base de datos vectorial local está lista.")