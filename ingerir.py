import os
import re
import sys
import shutil
import hashlib
# pyrefly: ignore [missing-import]
from pypdf import PdfReader
from bd_config import (
    agregar_fragmentos,
    obtener_coleccion,
    clasificar_libro,
    limpiar_texto_sap,
    LIBROS_IGNORADOS,
    CATALOG_CACHE_PATH,
    BASE_DIR,
)

PDF_DIR = os.path.join(BASE_DIR, "pdfs")


def fragmentar_texto_semantico(texto: str, tamano_chunk: int = 1000, traslape: int = 180):
    """
    Divide el texto respetando saltos de párrafo, puntos seguidos y líneas de código ABAP
    para evitar cortar palabras o sentencias a la mitad.
    """
    texto = limpiar_texto_sap(texto)
    if not texto:
        return []

    chunks = []
    inicio = 0
    longitud = len(texto)

    while inicio < longitud:
        fin = min(inicio + tamano_chunk, longitud)

        if fin < longitud:
            offset_base = max(inicio + int(tamano_chunk * 0.65), inicio)
            ventana_corte = texto[offset_base:fin]
            pos_parrafo = ventana_corte.rfind("\n\n")
            pos_linea = max(ventana_corte.rfind("\n"), ventana_corte.rfind(". "))
            pos_espacio = ventana_corte.rfind(" ")

            if pos_parrafo != -1:
                fin = offset_base + pos_parrafo + 2
            elif pos_linea != -1:
                fin = offset_base + pos_linea + 1
            elif pos_espacio != -1:
                fin = offset_base + pos_espacio + 1

        bloque_txt = texto[inicio:fin].strip()
        if len(bloque_txt) >= 40:
            chunks.append(bloque_txt)

        if fin >= longitud:
            break

        nuevo_inicio = max(inicio + 1, fin - traslape)
        espacio_traslape = texto.find(" ", nuevo_inicio, min(nuevo_inicio + 40, longitud))
        if espacio_traslape != -1:
            nuevo_inicio = espacio_traslape + 1
        inicio = nuevo_inicio

    return chunks


def indexar_un_pdf(filepath: str, coleccion, forzar: bool = False) -> bool:
    """Extrae, fragmenta e indexa un único archivo PDF en ChromaDB."""
    filename = os.path.basename(filepath)
    if not filename.lower().endswith(".pdf"):
        print(f"⚠️ El archivo '{filename}' no es un PDF.")
        return False

    if not forzar:
        existente = coleccion.get(ids=[f"{filename}_chunk_0"], include=[])
        if existente and existente.get("ids"):
            return False  # Ya está indexado

    print(f"📖 Extrayendo y limpiando texto de: {filename} ...")
    try:
        reader = PdfReader(filepath)
        texto_completo = ""
        for pagina in reader.pages:
            texto_pag = pagina.extract_text()
            if texto_pag:
                texto_completo += texto_pag + "\n"

        chunks = fragmentar_texto_semantico(texto_completo)
        if not chunks:
            print(f"⚠️ No se pudo extraer texto útil de '{filename}' (¿es un PDF escaneado como imagen?).")
            return False

        categoria = clasificar_libro(filename)
        textos_db, metadatos_db, ids_db = [], [], []

        for i, chunk in enumerate(chunks):
            textos_db.append(chunk)
            metadatos_db.append({
                "fuente": filename,
                "bloque": i,
                "categoria": categoria,
            })
            ids_db.append(f"{filename}_chunk_{i}")

        lote_max = 250
        for idx in range(0, len(textos_db), lote_max):
            agregar_fragmentos(
                textos_db[idx:idx + lote_max],
                metadatos_db[idx:idx + lote_max],
                ids_db[idx:idx + lote_max],
            )

        print(f"✅ Indexados con éxito {len(textos_db)} fragmentos de '{filename}' [Categoría: {categoria}]")
        return True

    except Exception as e:
        print(f"❌ Error al procesar '{filename}': {e}")
        return False


def procesar_pdfs(rutas_especificas=None, forzar_reindexado: bool = False):
    os.makedirs(PDF_DIR, exist_ok=True)
    coleccion = obtener_coleccion()
    nuevos = 0

    # Modo 1: Si se pasaron rutas de PDFs por línea de comandos
    if rutas_especificas:
        for ruta in rutas_especificas:
            if not os.path.exists(ruta):
                # Probar dentro de la carpeta pdfs/
                ruta_en_pdfs = os.path.join(PDF_DIR, ruta)
                if os.path.exists(ruta_en_pdfs):
                    ruta = ruta_en_pdfs
                else:
                    print(f"❌ No se encontró el archivo: {ruta}")
                    continue

            # Si el PDF está fuera de la carpeta pdfs/, copiarlo a pdfs/ para mantener el repositorio ordenado
            destino = os.path.join(PDF_DIR, os.path.basename(ruta))
            if os.path.abspath(ruta) != os.path.abspath(destino):
                shutil.copy2(ruta, destino)
                print(f"📂 Copiado a carpeta pdfs/: {os.path.basename(ruta)}")

            if indexar_un_pdf(destino, coleccion, forzar=forzar_reindexado):
                nuevos += 1
    else:
        # Modo 2: Escanear carpeta pdfs/ e indexar únicamente los libros nuevos
        print("🔍 Buscando libros nuevos en la carpeta 'pdfs/'...")
        for filename in sorted(os.listdir(PDF_DIR)):
            if not filename.lower().endswith(".pdf"):
                continue
            if filename in LIBROS_IGNORADOS or re.search(r"\(\d+\)\.pdf$|__ Copy", filename, re.IGNORECASE):
                continue
            filepath = os.path.join(PDF_DIR, filename)
            if indexar_un_pdf(filepath, coleccion, forzar=forzar_reindexado):
                nuevos += 1

    if nuevos > 0 and os.path.exists(CATALOG_CACHE_PATH):
        try:
            os.remove(CATALOG_CACHE_PATH)
        except Exception:
            pass

    print(f"\n🎉 Proceso finalizado. Nuevos libros agregados a la base vectorial: {nuevos}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    forzar = "--force" in sys.argv
    procesar_pdfs(rutas_especificas=args if args else None, forzar_reindexado=forzar)
