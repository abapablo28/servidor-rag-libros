import os
import re
import sys
import json
import gzip
import ssl
import sqlite3
import hashlib
import warnings
import zipfile
import urllib.request
import urllib.parse
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple

# 1. Apagar telemetría, logs HTTP y forzar modo 100% OFFLINE ANTES de cualquier importación de IA
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_VERBOSITY"] = "error"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"

try:
    import pip_system_certs.wrapt_requests  # type: ignore
except Exception:
    pass

import logging
for _logger_name in ("huggingface_hub", "sentence_transformers", "chromadb", "httpx", "httpcore", "urllib3"):
    logging.getLogger(_logger_name).setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

import chromadb

# ==============================================================================
# CONFIGURACIÓN DE RUTAS
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "base_vectores")
SQLITE_PATH = os.path.join(DB_PATH, "chroma.sqlite3")
CATALOG_CACHE_PATH = os.path.join(DB_PATH, "catalogo_cache.json")
CLEAN_CORE_CACHE_PATH = os.path.join(BASE_DIR, "clean_core_catalog.json.gz")
TITULOS_MAP_PATH = os.path.join(BASE_DIR, "titulos_libros_sap.json")
ZIP_PATH = os.path.join(BASE_DIR, "base_vectores.zip")
URL_DEL_ZIP = "https://huggingface.co/datasets/abappablo/rag-abap/resolve/main/base_vectores.zip"

_MAPA_TITULOS: Optional[Dict[str, str]] = None


def obtener_titulo_limpio_libro(fuente: str) -> str:
    """Devuelve el título limpio, oficial y catalogado del libro (ej: '[SAP Press] Clean ABAP')."""
    global _MAPA_TITULOS
    if _MAPA_TITULOS is None:
        _MAPA_TITULOS = {}
        for p in (TITULOS_MAP_PATH, os.path.join(DB_PATH, "titulos_libros_sap.json")):
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for k, v in data.items():
                            _MAPA_TITULOS[k] = v.get("titulo_limpio", k) if isinstance(v, dict) else str(v)
                    break
                except Exception:
                    pass
    return _MAPA_TITULOS.get(fuente, fuente)

# Archivos duplicados o irrelevantes detectados en la base para excluirlos automáticamente
LIBROS_IGNORADOS = {
    "103446420-sap-fi-mm-sd-integration (1).pdf",
    "ABAP-RESTful-Application-Programming-Model.pdf",
    "BC425 en-col10-enhancement-modifications (1).pdf",
    "Cloud Integration with SAP Integration Suite __ Copy k7ng-p6cm-h5iy-jqer.pdf",
    "Core Data Services for ABAP (2019) (1).pdf",
    "Implantacion_de_soluciones_SAP_para_el_m.pdf",
    "Migration to S4HANA.pdf",
    "SAP Business Technology Platform __ Copy 94jk-rfhy-mdt3-qsza.pdf",
    "Sap_FI_Gestion_financiera_I_Parte_1_de_2 (1).pdf",
    "unidad11 (1).pdf",
    "unidad12 (1).pdf",
    "unidad14 (1).pdf",
    "unidad17 (1).pdf",
    "Hola mcp.pdf",
    "cp7_ConfirmationOfParticipation.pdf",
    "cp7_RecordOfAchievement (1).pdf",
}

# ==============================================================================
# DICCIONARIO TÉCNICO BILINGÜE SAP (ESPAÑOL <-> INGLÉS) Y MAPEO DE MÓDULOS
# ==============================================================================
SINONIMOS_SAP_ES_EN: List[Tuple[List[str], str, List[str], str]] = [
    # (Triggers en consulta, Expansión semántica EN, Frases específicas FTS5, Categoría)
    (
        ["migracion", "migrar", "conversion", "wricef", "codigo z", "custom code", "atc", "simplification", "depuracion", "limpieza", "scmon", "susg", "readiness"],
        "SAP S/4HANA system conversion custom code migration adaptation ATC ABAP Test Cockpit simplification item check SCMON SUSG clone finder obsolete transactions",
        ['"custom code"', "ATC", "SCMON", "SUSG", '"simplification item"', '"system conversion"'],
        "S4HANA_MIGRATION",
    ),
    (
        ["clean abap", "buenas practicas", "estilo", "codigo limpio", "refactor", "legibilidad", "naming"],
        "Clean ABAP style guide best practices naming conventions methods classes error handling unit test",
        ['"Clean ABAP"', '"naming conventions"', "refactoring", '"ABAP Unit"'],
        "ABAP_CORE",
    ),
    (
        ["orientado a objetos", "clases", "interfaces", "herencia", "polimorfismo", "patron", "patrones", "singleton", "factory", "abap objects"],
        "Object-Oriented Programming ABAP Objects classes interfaces inheritance design patterns singleton factory",
        ['"ABAP Objects"', '"design pattern"', "singleton", "factory", "polymorphism"],
        "ABAP_CORE",
    ),
    (
        ["cds", "core data services", "vista cds", "vistas cds", "annotations", "anotaciones", "dcl", "access control", "vdm", "asociacion", "asociaciones"],
        "Core Data Services for ABAP CDS view entity annotations associations access control DCL authorization virtual data model",
        ['"define view entity"', '"define role"', '"AccessControl"', "association", "DCL"],
        "CDS_RAP_FIORI",
    ),
    (
        ["rap", "restful", "behavior definition", "bdef", "eml", "managed", "unmanaged", "draft"],
        "ABAP RESTful Application Programming Model RAP behavior definition BDEF projection entity manipulation language EML managed unmanaged",
        ['"managed implementation"', '"behavior definition"', "EML", "BDEF"],
        "CDS_RAP_FIORI",
    ),
    (
        ["fiori", "sapui5", "ui5", "fiori elements", "launchpad", "odata", "gateway", "segw"],
        "SAP Fiori Elements SAPUI5 OData service SAP Gateway SEGW annotations smart controls",
        ["SEGW", '"OData service"', "SAPUI5", '"Fiori Elements"', "DPC_EXT"],
        "CDS_RAP_FIORI",
    ),
    (
        ["rendimiento", "performance", "optimizacion", "code pushdown", "amdp", "planviz", "st05", "sat", "for all entries"],
        "SAP HANA performance tuning ABAP code pushdown Open SQL AMDP SQLScript ST05 SAT PlanViz buffer index",
        ['"FOR ALL ENTRIES"', "AMDP", "ST05", "PlanViz", '"code pushdown"'],
        "HANA_PERF",
    ),
    (
        ["ampliacion", "ampliaciones", "enhancement", "badi", "user exit", "customer exit", "implicit", "explicit", "bte", "modificacion", "bc425"],
        "BC425 enhancements modifications BAdI Business Add-In user exit customer exit enhancement spot framework",
        ["BAdI", '"user exit"', '"customer exit"', '"enhancement spot"', "CMOD", "SMOD", "SE18", "SE19"],
        "ABAP_CORE",
    ),
    (
        ["smartforms", "sapscript", "adobe forms", "formulario", "formularios", "impresion", "sfp"],
        "SAP Interactive Forms by Adobe SmartForms SAPscript form printing output management",
        ["SmartForms", "SAPscript", '"Adobe Forms"', "SSF_FUNCTION_MODULE_NAME"],
        "WORKFLOW_FORMS",
    ),
    (
        ["workflow", "flujo de trabajo", "swdd", "work item", "my inbox", "aprobacion", "liberacion"],
        "SAP Business Workflow SWDD work item agent determination My Inbox flexible workflow S/4HANA",
        ["SWDD", '"My Inbox"', "SWO1", '"work item"'],
        "WORKFLOW_FORMS",
    ),
    (
        ["lsmw", "carga de datos", "batch input", "bapi", "migracion de datos", "grabacion", "shdb"],
        "LSMW Legacy System Migration Workbench batch input BAPI direct input data migration",
        ["LSMW", "SHDB", '"batch input"', "BAPI_"],
        "WORKFLOW_FORMS",
    ),
    (
        ["finanzas", "contabilidad", "libro mayor", "cuentas por pagar", "cuentas por cobrar", "activos fijos", "acdoca", "bseg", "bkpf", "fb01", "f110", "diferencias de pago", "impuestos"],
        "SAP FI Financial Accounting S4F12 S4F13 S4F15 S4F17 TFIN50 general ledger accounts payable receivable asset accounting ACDOCA payment",
        ["ACDOCA", "BSEG", "BKPF", "F110", "FB01", '"diferencias de pagos"', '"libro mayor"'],
        "FI_CO",
    ),
    (
        ["compras", "aprovisionamiento", "inventario", "migo", "miro", "me21n", "pedido de compra", "solicitud de pedido", "movimiento de mercancias", "stock", "valoracion"],
        "SAP MM Materials Management procurement purchasing inventory management MIGO MIRO ME21N TSCM50 TSCM52 movement type valuation",
        ["MIGO", "MIRO", "ME21N", "OBYC", '"movimientos de mercancías"', '"verificación de facturas"'],
        "MM_EWM",
    ),
    (
        ["ewm", "almacen", "almacenes", "entrega entrante", "entrega saliente", "picking", "putaway", "handling unit"],
        "SAP EWM Extended Warehouse Management warehouse process type storage bin handling unit picking putaway",
        ["EWM", '"handling unit"', "putaway", "picking"],
        "MM_EWM",
    ),
    (
        ["ventas", "facturacion", "pedido de venta", "va01", "vf01", "vl01n", "precios", "condiciones", "interlocutor", "entrega", "expedicion"],
        "SAP SD Sales and Distribution order fulfillment pricing condition technique billing delivery TSCM60 VA01 VL01N VF01",
        ["VA01", "VL01N", "VF01", "VKOA", '"clase de condición"', "facturación"],
        "SD",
    ),
    (
        ["btp", "cpi", "integration suite", "cloud integration", "iflow", "api management", "cap", "cloud connector", "event mesh", "aif"],
        "SAP BTP Business Technology Platform Cloud Integration CPI Integration Suite iFlow API Management CAP Cloud Connector",
        ["iFlow", '"Integration Suite"', '"Cloud Connector"', "AIF"],
        "BTP_INTEGRATION",
    ),
    (
        ["edocument", "facturacion electronica", "drc", "call transformation"],
        "SAP eDocument Electronic Invoicing Document and Reporting Compliance DRC XML transformation",
        ["eDocument", "EDOC_COCKPIT", '"CALL TRANSFORMATION"'],
        "BTP_INTEGRATION",
    ),
    (
        ["nomina", "infotipo", "infotype", "personal", "tiempos", "pa20", "pa30", "abkrs", "lgmst", "rasgo"],
        "SAP HR HCM Human Capital Management infotype payroll personnel administration time management THR12",
        ["PA30", "PA20", "ABKRS", "LGMST", "infotipo", "infotype"],
        "HR_HCM",
    ),
    (
        ["datasphere", "sac", "analytics cloud", "lumira", "businessobjects", "open hub", "infocube", "dso"],
        "SAP BW Data Warehousing TBW42 Datasphere SAP Analytics Cloud SAC Open Hub transformation",
        ['"open hub"', "Datasphere", "InfoCube"],
        "BW_ANALYTICS",
    ),
]


def _normalizar_para_match(texto: str) -> str:
    """Quita tildes y pasa a minúsculas para comparar palabras clave de forma robusta."""
    reemplazos = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return texto.translate(reemplazos).lower()


def clasificar_libro(nombre_pdf: str) -> str:
    """Clasifica un manual PDF dentro de un dominio técnico/funcional de SAP."""
    n = _normalizar_para_match(nombre_pdf)
    if any(k in n for k in ["migrat", "conversion", "asap", "activate"]):
        return "S4HANA_MIGRATION"
    if any(k in n for k in ["cds", "core data services", "restful", "rap", "fiori", "sapui5", "ui5", "gateway", "odata"]):
        return "CDS_RAP_FIORI"
    if any(k in n for k in ["ha100", "ha300", "ha400", "hana", "planviz", "performance tuning"]):
        return "HANA_PERF"
    if any(k in n for k in ["abap", "bc425", "code vulnerability"]):
        return "ABAP_CORE"
    if any(k in n for k in ["workflow", "smartforms", "sapscript", "adobe", "lsmw", "f920", "my_inbox"]):
        return "WORKFLOW_FORMS"
    if any(k in n for k in ["s4f", "tfin", "sap_fi", "fi_", "activos", "financier", "fi-mm-sd"]):
        return "FI_CO"
    if any(k in n for k in ["tscm50", "tscm52", "sap_mm", "ewm", "aprovisionamiento"]):
        return "MM_EWM"
    if any(k in n for k in ["tscm60", "sd", "sales", "pricing"]):
        return "SD"
    if any(k in n for k in ["btp", "cloud", "cpi", "integration", "pi", "aif", "api management", "edocument", "electronic_invo", "drc", "xml", "cp7", "cld200"]):
        return "BTP_INTEGRATION"
    if any(k in n for k in ["thr12", "hr", "hcm", "unidad"]):
        return "HR_HCM"
    if any(k in n for k in ["tbw", "analytics", "datasphere", "lumira", "businessobject", "infoview"]):
        return "BW_ANALYTICS"
    return "GENERAL_SAP"


# ==============================================================================
# INICIALIZACIÓN DIFERIDA (LAZY LOADING) PARA ARRANQUE INSTANTÁNEO EN MCP
# ==============================================================================
_model = None
_chroma_client = None
_collection = None


def asegurar_base_datos():
    """Verifica si la base de datos existe. Si no, la descarga y extrae automáticamente."""
    if not os.path.exists(DB_PATH):
        print("Base de datos vectorial no encontrada. Descargando...", file=sys.stderr)
        try:
            urllib.request.urlretrieve(URL_DEL_ZIP, ZIP_PATH)
            with zipfile.ZipFile(ZIP_PATH, "r") as zip_ref:
                zip_ref.extractall(BASE_DIR)
            os.remove(ZIP_PATH)
            print("Base de conocimientos inicializada correctamente.", file=sys.stderr)
        except Exception as e:
            print(f"Error al descargar o extraer la base de datos: {e}", file=sys.stderr)
            if os.path.exists(ZIP_PATH):
                os.remove(ZIP_PATH)


import threading
_init_lock = threading.Lock()


def obtener_modelo():
    """
    Carga el motor de embeddings ONNX ultraligero (all-MiniLM-L6-v2 en ONNXRuntime).
    Arranca en ~2s (vs 26s de PyTorch) y consume 600MB menos de RAM produciendo los mismos vectores 384-d.
    """
    global _model
    if _model is None:
        with _init_lock:
            if _model is None:
                try:
                    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
                    _onnx_ef = ONNXMiniLM_L6_V2()

                    class _ONNXWrapper:
                        def encode(self, textos: List[str]):
                            vecs = _onnx_ef(list(textos))
                            return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vecs]

                    _model = _ONNXWrapper()
                except Exception:
                    from sentence_transformers import SentenceTransformer
                    model_name = os.environ.get("SAP_RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
                    _model = SentenceTransformer(model_name, local_files_only=True)
    return _model


def obtener_coleccion():
    """Conecta a ChromaDB bajo demanda de forma thread-safe (Singleton)."""
    global _chroma_client, _collection
    if _collection is None:
        with _init_lock:
            if _collection is None:
                asegurar_base_datos()
                _chroma_client = chromadb.PersistentClient(path=DB_PATH)
                _collection = _chroma_client.get_or_create_collection(name="conocimiento_sap")
    return _collection


_sqlite_conn = None


def _obtener_conexion_sqlite() -> Optional[sqlite3.Connection]:
    """Abre y reutiliza una conexión permanente de solo lectura a chroma.sqlite3."""
    global _sqlite_conn
    if _sqlite_conn is None:
        asegurar_base_datos()
        if not os.path.exists(SQLITE_PATH):
            return None
        _sqlite_conn = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True, check_same_thread=False)
    return _sqlite_conn


@lru_cache(maxsize=512)
def _codificar_consulta(texto: str) -> List[float]:
    """Calcula y guarda en caché el vector de una consulta."""
    modelo = obtener_modelo()
    res = modelo.encode([texto])[0]
    return res.tolist() if hasattr(res, "tolist") else list(res)


# ==============================================================================
# CATÁLOGO DE LIBROS EN CACHÉ PERSISTENTE (< 1 ms) Y LECTURA O(1)
# ==============================================================================
@lru_cache(maxsize=1)
def obtener_catalogo_libros() -> List[Dict[str, Any]]:
    """Devuelve la lista depurada de libros en la BD con títulos limpios y caché en disco para lectura instantánea (< 1ms)."""
    if os.path.exists(CATALOG_CACHE_PATH):
        try:
            with open(CATALOG_CACHE_PATH, "r", encoding="utf-8") as f:
                datos = json.load(f)
                if isinstance(datos, list) and len(datos) > 0 and "titulo" in datos[0]:
                    return datos
        except Exception:
            pass

    conn = _obtener_conexion_sqlite()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT string_value, COUNT(*) FROM embedding_metadata "
            "WHERE key='fuente' GROUP BY string_value ORDER BY string_value"
        ).fetchall()
        catalogo = []
        for nombre, total_bloques in rows:
            if not nombre or nombre in LIBROS_IGNORADOS:
                continue
            categoria = clasificar_libro(nombre)
            n_low = nombre.lower()
            idioma = "ES" if any(x in n_low for x in ["_es", ".es-", "gestion", "aprovisionamiento", "manual", "implantacion", "contabilidad", "cumplimiento", "practica", "unidad", "memoria"]) else "EN"
            titulo_limpio = obtener_titulo_limpio_libro(nombre)
            catalogo.append({
                "fuente": nombre,
                "titulo": titulo_limpio,
                "categoria": categoria,
                "idioma": idioma,
                "total_bloques": total_bloques,
            })
        try:
            with open(CATALOG_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(catalogo, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return catalogo
    except Exception:
        return []


def limpiar_texto_sap(texto: str) -> str:
    """Limpia caracteres corruptos y cabeceras/pies de página repetitivos de manuales SAP."""
    if not texto:
        return ""
    limpio = texto.replace("\x00", "").encode("utf-8", "ignore").decode("utf-8")
    limpio = re.sub(r"\n?\d*\s*©\s*(?:Copyright\.?\s*)?\d{4}\s*SAP\s*(?:AG|SE)[^\n]*\n?", "\n", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"\n?©\s*Copyright\.?\s*Reservados todos los derechos\.?\s*\d*\n?", "\n", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"\n{3,}", "\n\n", limpio)
    return limpio.strip()


def _unir_fragmentos_con_traslape(fragmentos: List[str]) -> str:
    """
    Une bloques consecutivos (ej. bloque i-1, i, i+1) eliminando automáticamente
    el traslape de ~150 caracteres creado durante la ingesta.
    """
    if not fragmentos:
        return ""
    resultado = fragmentos[0]
    for sig in fragmentos[1:]:
        if not sig:
            continue
        max_overlap = min(250, len(resultado), len(sig))
        overlap_encontrado = 0
        for tam in range(max_overlap, 25, -1):
            if resultado[-tam:] == sig[:tam]:
                overlap_encontrado = tam
                break
        if overlap_encontrado > 0:
            resultado += sig[overlap_encontrado:]
        else:
            resultado += "\n" + sig
    return limpiar_texto_sap(resultado)


def leer_bloques_libro(fuente: str, bloque_inicio: int, bloque_fin: int) -> Dict[str, Any]:
    """
    Lee de forma instantánea (< 2ms en SQLite) una secuencia continua de bloques
    de un libro específico y los une sin cortes.
    """
    bloque_inicio = max(0, int(bloque_inicio))
    bloque_fin = max(bloque_inicio, min(int(bloque_fin), bloque_inicio + 15))
    ids_buscados = [f"{fuente}_chunk_{b}" for b in range(bloque_inicio, bloque_fin + 1)]

    conn = _obtener_conexion_sqlite()
    mapa_textos: Dict[int, str] = {}
    if conn is not None:
        try:
            placeholders = ",".join(["?"] * len(ids_buscados))
            sql = f"""
                SELECT e.embedding_id, f.string_value
                FROM embeddings e
                JOIN embedding_fulltext_search f ON f.rowid = e.id
                WHERE e.embedding_id IN ({placeholders})
            """
            for eid, texto in conn.execute(sql, ids_buscados).fetchall():
                try:
                    num = int(eid.rsplit("_chunk_", 1)[1])
                    mapa_textos[num] = texto
                except Exception:
                    pass
        except Exception:
            pass

    bloques_ordenados = [mapa_textos[b] for b in sorted(mapa_textos.keys())]
    texto_unido = _unir_fragmentos_con_traslape(bloques_ordenados)
    return {
        "fuente": fuente,
        "bloque_inicio": min(mapa_textos.keys()) if mapa_textos else bloque_inicio,
        "bloque_fin": max(mapa_textos.keys()) if mapa_textos else bloque_fin,
        "bloques_encontrados": len(mapa_textos),
        "contenido_continuo": texto_unido,
    }


# ==============================================================================
# MOTOR DE BÚSQUEDA HÍBRIDO BILINGÜE (FTS5 BM25 + VECTORIAL + DOMINIO + VECINOS)
# ==============================================================================
def expandir_consulta_sap(pregunta: str, query_en: Optional[str] = None, modulo: Optional[str] = None) -> Dict[str, Any]:
    """
    Analiza la consulta del usuario y genera:
    1. Términos técnicos en inglés y español para cruzar barrera de idioma.
    2. Categorías/módulos de libros prioritarios.
    3. Expresiones FTS5 BM25 con acentos preservados y términos técnicos en inglés.
    """
    pregunta_norm = _normalizar_para_match(pregunta)
    expansiones_en = []
    fts_phrases = []
    categorias = set()

    categoria_principal = None
    if modulo:
        mod_up = modulo.strip().upper()
        mapa_mod = {
            "ABAP": "ABAP_CORE",
            "MIGRACION": "S4HANA_MIGRATION",
            "S4HANA": "S4HANA_MIGRATION",
            "CDS": "CDS_RAP_FIORI",
            "RAP": "CDS_RAP_FIORI",
            "FIORI": "CDS_RAP_FIORI",
            "HANA": "HANA_PERF",
            "FI": "FI_CO",
            "CO": "FI_CO",
            "MM": "MM_EWM",
            "EWM": "MM_EWM",
            "SD": "SD",
            "BTP": "BTP_INTEGRATION",
            "CPI": "BTP_INTEGRATION",
            "WORKFLOW": "WORKFLOW_FORMS",
            "HR": "HR_HCM",
            "HCM": "HR_HCM",
            "BW": "BW_ANALYTICS",
        }
        if mod_up in mapa_mod:
            categoria_principal = mapa_mod[mod_up]
            categorias.add(categoria_principal)

    for triggers, expansion, frases_fts, cat in SINONIMOS_SAP_ES_EN:
        if any(t in pregunta_norm for t in triggers):
            expansiones_en.append(expansion)
            fts_phrases.extend(frases_fts)
            categorias.add(cat)

    if not categorias and any(w in pregunta_norm for w in ["programa", "reporte", "funcion", "metodo", "clase", "tabla", "bapi", "sentencia", "loop", "select"]):
        categorias.add("ABAP_CORE")
        categorias.add("HANA_PERF")

    consulta_en_final = (query_en or "").strip()
    if expansiones_en:
        consulta_en_final = (consulta_en_final + " " + " ".join(expansiones_en[:3])).strip()
    if not consulta_en_final:
        consulta_en_final = pregunta

    # Excluir palabras genéricas que aparecen en casi todos los libros para que FTS5 sea instantáneo (<80ms)
    stopwords = {
        "como", "cual", "cuales", "para", "este", "esta", "estos", "estas", "hacer", "puedo",
        "puede", "mejor", "manera", "forma", "solo", "tengo", "idea", "desde", "hasta", "donde",
        "cuando", "porque", "sobre", "entre", "todo", "todos", "una", "uno", "unos", "unas",
        "del", "las", "los", "con", "por", "sin", "que", "the", "and", "for", "with", "how",
        "what", "necesito", "quiero", "funciona", "crear", "proceso", "mejores", "practicas",
        "sap", "abap", "hana", "s4hana", "codigo", "code", "datos", "data", "sistema", "system",
        "vista", "view", "tabla", "table", "control", "acceso", "access"
    }
    texto_combinado = f"{pregunta} {query_en or ''}"
    palabras_raw = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_]{3,}", texto_combinado)
    keywords_usuario = []
    vistas = set()
    for p in palabras_raw:
        p_low = _normalizar_para_match(p)
        if p_low not in stopwords and p_low not in vistas:
            vistas.add(p_low)
            keywords_usuario.append(p)

    return {
        "pregunta_original": pregunta,
        "consulta_en": consulta_en_final,
        "categoria_principal": categoria_principal,
        "categorias": list(categorias),
        "keywords_usuario": keywords_usuario[:8],
        "fts_phrases": fts_phrases[:8],
    }


def _buscar_fts5_sqlite(
    keywords_usuario: List[str],
    fts_phrases: List[str],
    libros_dominio: Optional[set] = None,
    libro_filtro: Optional[str] = None,
    limite: int = 30,
) -> List[Tuple[str, int, str, float]]:
    """
    Busca coincidencias léxicas exactas (BM25) en la tabla FTS5 de chroma.sqlite3.
    Mantiene tildes en español e incluye frases técnicas SAP en inglés.
    """
    conn = _obtener_conexion_sqlite()
    if conn is None:
        return []

    try:
        terminos_fts = []
        # 1. Frases técnicas del diccionario SAP (ej. '"custom code"', 'ATC', 'MIGO')
        for frase in fts_phrases:
            limpia = re.sub(r'[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_" ]', " ", frase).strip()
            if limpia and limpia not in terminos_fts:
                if " " in limpia and not limpia.startswith('"'):
                    limpia = f'"{limpia}"'
                terminos_fts.append(limpia)

        # 2. Palabras del usuario (preservando acentos)
        for kw in keywords_usuario:
            limpio = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_]", "", kw)
            if len(limpio) >= 3:
                term = f'"{limpio}"'
                if term not in terminos_fts:
                    terminos_fts.append(term)

        if not terminos_fts:
            return []

        match_expr = " OR ".join(terminos_fts[:12])
        sql = """
            SELECT e.embedding_id, f.string_value, bm25(embedding_fulltext_search) as rank_score
            FROM embedding_fulltext_search f
            JOIN embeddings e ON f.rowid = e.id
            WHERE embedding_fulltext_search MATCH ?
            ORDER BY rank_score
            LIMIT ?
        """
        rows = conn.execute(sql, (match_expr, limite * 3)).fetchall()
        resultados = []
        filtro_norm = _normalizar_para_match(libro_filtro) if libro_filtro else None
        for eid, texto, score in rows:
            if "_chunk_" not in eid:
                continue
            fuente, str_bloque = eid.rsplit("_chunk_", 1)
            if fuente in LIBROS_IGNORADOS:
                continue
            if filtro_norm and filtro_norm not in _normalizar_para_match(fuente) and filtro_norm not in _normalizar_para_match(obtener_titulo_limpio_libro(fuente)):
                continue
            try:
                bloque = int(str_bloque)
            except ValueError:
                bloque = 0
            resultados.append((fuente, bloque, texto, float(score)))
            if len(resultados) >= limite:
                break
        return resultados
    except Exception:
        return []


def buscar_hibrido_sap(
    pregunta: str,
    top_k: int = 6,
    query_en: Optional[str] = None,
    modulo: Optional[str] = None,
    libro_filtro: Optional[str] = None,
    ventana_vecinos: int = 1,
) -> List[Dict[str, Any]]:
    """
    Búsqueda Híbrida SAP ultrarrápida (< 400ms):
    1. Expande la consulta a español + inglés técnico SAP.
    2. Ejecuta FTS5 BM25 en SQLite + Consulta Vectorial HNSW en memoria.
    3. Prioriza los libros oficiales del módulo/categoría detectada, elimina duplicados
       y reconstruye bloques vecinos (bloque-1, bloque, bloque+1) sin cortes.
    """
    top_k = max(1, min(int(top_k), 15))
    info_query = expandir_consulta_sap(pregunta, query_en=query_en, modulo=modulo)
    catalogo = obtener_catalogo_libros()
    coleccion = obtener_coleccion()

    filtro_norm = _normalizar_para_match(libro_filtro) if libro_filtro else None
    libros_dominio = set()
    if filtro_norm:
        libros_dominio = {b["fuente"] for b in catalogo if filtro_norm in _normalizar_para_match(b["fuente"]) or filtro_norm in _normalizar_para_match(b.get("titulo", ""))}
    elif info_query["categorias"]:
        cats = set(info_query["categorias"])
        libros_dominio = {b["fuente"] for b in catalogo if b["categoria"] in cats}
        if "HR_HCM" not in cats:
            libros_dominio = {f for f in libros_dominio if not f.lower().startswith("unidad")}

    emb_es = _codificar_consulta(pregunta)
    emb_en = _codificar_consulta(info_query["consulta_en"]) if info_query["consulta_en"] != pregunta else emb_es

    candidatos: Dict[Tuple[str, int], Dict[str, Any]] = {}

    libros_principal = set()
    if info_query.get("categoria_principal"):
        libros_principal = {b["fuente"] for b in catalogo if b["categoria"] == info_query["categoria_principal"]}

    def _registrar_candidato(fuente: str, bloque: int, texto: str, rank: int, peso: float, origen: str):
        if fuente in LIBROS_IGNORADOS:
            return
        if fuente.lower().startswith("unidad") and "HR_HCM" not in info_query["categorias"] and not filtro_norm:
            return
        if filtro_norm and filtro_norm not in _normalizar_para_match(fuente):
            return
        clave = (fuente, bloque)
        # Bonificar fuertemente si el libro pertenece al módulo explícito o categoría detectada
        if libros_principal and fuente in libros_principal:
            bonus_dominio = 2.0
        elif libros_dominio and fuente in libros_dominio:
            bonus_dominio = 1.45
        else:
            bonus_dominio = 1.0
        rrf = peso * bonus_dominio * (1.0 / (15 + rank))
        if clave not in candidatos:
            candidatos[clave] = {"score": 0.0, "texto": texto, "origenes": set()}
        candidatos[clave]["score"] += rrf
        candidatos[clave]["origenes"].add(origen)

    # --- A. Búsqueda Léxica FTS5 BM25 en SQLite (Términos exactos en ES + EN, ~150ms) ---
    fts_hits = _buscar_fts5_sqlite(
        info_query["keywords_usuario"],
        info_query["fts_phrases"],
        libros_dominio=libros_dominio,
        libro_filtro=libro_filtro,
        limite=30,
    )
    for rank, (fuente, bloque, texto, _bm25) in enumerate(fts_hits):
        _registrar_candidato(fuente, bloque, texto, rank, peso=1.50, origen="fts_bm25")

    # --- B. Búsqueda Vectorial HNSW Bilingüe (1 sola llamada en memoria, ~25ms) ---
    try:
        where_unico = {"fuente": list(libros_dominio)[0]} if len(libros_dominio) == 1 else None
        res_vec = coleccion.query(
            query_embeddings=[emb_en, emb_es],
            n_results=35,
            where=where_unico,
        )
        for idx_q, etiqueta in enumerate(["vec_en", "vec_es"]):
            docs = res_vec.get("documents", [[]])[idx_q] if res_vec.get("documents") else []
            metas = res_vec.get("metadatas", [[]])[idx_q] if res_vec.get("metadatas") else []
            for rank, (doc, meta) in enumerate(zip(docs, metas)):
                if doc and meta:
                    _registrar_candidato(
                        meta.get("fuente", ""),
                        int(meta.get("bloque", 0)),
                        doc,
                        rank,
                        peso=1.15 if idx_q == 0 else 1.0,
                        origen=etiqueta,
                    )
    except Exception:
        pass

    # --- C. Re-scoring por coincidencia de keywords en texto y título del libro ---
    todas_kw_norm = [
        _normalizar_para_match(re.sub(r'"', "", k))
        for k in (info_query["keywords_usuario"] + info_query["fts_phrases"])
        if len(k) >= 3
    ]
    for (fuente, bloque), info in candidatos.items():
        txt_norm = _normalizar_para_match(info["texto"])
        fuente_norm = _normalizar_para_match(fuente)
        matches_texto = sum(1 for k in todas_kw_norm if k in txt_norm)
        matches_titulo = sum(1 for k in todas_kw_norm if k in fuente_norm)
        info["score"] += (matches_texto * 0.015) + (matches_titulo * 0.020)

        # Penalizar páginas que son solo índice ("..... 45") o portada vacía
        if info["texto"].count("...") > 5 or len(info["texto"].strip()) < 140:
            info["score"] *= 0.35

    ordenados = sorted(candidatos.items(), key=lambda x: x[1]["score"], reverse=True)

    # --- D. Selección diversificada y sin bloques solapados ni textos idénticos ---
    seleccionados: List[Tuple[str, int, Dict[str, Any]]] = []
    huellas_vistas = set()
    bloques_por_libro: Dict[str, List[int]] = {}

    for (fuente, bloque), info in ordenados:
        bloques_previos = bloques_por_libro.get(fuente, [])
        if any(abs(bloque - b_prev) <= max(1, ventana_vecinos * 2) for b_prev in bloques_previos):
            continue

        # Limitar a máximo 2 fragmentos de un mismo libro si hay suficientes candidatos para dar variedad
        if len(bloques_previos) >= 2 and len(ordenados) > top_k * 2 and not filtro_norm:
            continue

        texto_alnum = re.sub(r"\W+", "", info["texto"].lower())[:200]
        if len(texto_alnum) < 30:
            continue
        huella = hashlib.md5(texto_alnum.encode("utf-8")).hexdigest()
        if huella in huellas_vistas:
            continue

        huellas_vistas.add(huella)
        bloques_por_libro.setdefault(fuente, []).append(bloque)
        seleccionados.append((fuente, bloque, info))
        if len(seleccionados) >= top_k:
            break

    # --- E. Reconstrucción masiva de bloques vecinos en 1 sola consulta SQL ---
    ids_todos = []
    pedidos_por_candidato = []
    for fuente, bloque, info in seleccionados:
        b_ini = max(0, bloque - ventana_vecinos) if ventana_vecinos > 0 else bloque
        b_fin = bloque + ventana_vecinos if ventana_vecinos > 0 else bloque
        lista_ids = [f"{fuente}_chunk_{b}" for b in range(b_ini, b_fin + 1)]
        ids_todos.extend(lista_ids)
        pedidos_por_candidato.append((fuente, bloque, b_ini, b_fin, lista_ids, info))

    conn = _obtener_conexion_sqlite()
    mapa_textos_global: Dict[str, str] = {}
    if conn is not None and ids_todos:
        try:
            for i_chunk in range(0, len(ids_todos), 100):
                lote_ids = ids_todos[i_chunk:i_chunk + 100]
                placeholders = ",".join(["?"] * len(lote_ids))
                sql = f"""
                    SELECT e.embedding_id, f.string_value
                    FROM embeddings e
                    JOIN embedding_fulltext_search f ON f.rowid = e.id
                    WHERE e.embedding_id IN ({placeholders})
                """
                for eid, txt in conn.execute(sql, lote_ids).fetchall():
                    mapa_textos_global[eid] = txt
        except Exception:
            pass

    resultados_finales = []
    for fuente, bloque, b_ini, b_fin, lista_ids, info in pedidos_por_candidato:
        textos_bloques = [mapa_textos_global[eid] for eid in lista_ids if eid in mapa_textos_global]
        if textos_bloques:
            texto_final = _unir_fragmentos_con_traslape(textos_bloques)
            rango_bloques = f"{b_ini}-{b_fin}"
        else:
            texto_final = limpiar_texto_sap(info["texto"])
            rango_bloques = str(bloque)

        cat_libro = clasificar_libro(fuente)
        titulo_limpio = obtener_titulo_limpio_libro(fuente)
        encabezado_contextual = f"[Manual SAP: {titulo_limpio} (Archivo: {fuente}) | Dominio: {cat_libro} | Bloques: {rango_bloques}]\n"
        resultados_finales.append({
            "fuente": fuente,
            "titulo": titulo_limpio,
            "categoria": cat_libro,
            "bloque": bloque,
            "rango_bloques": rango_bloques,
            "relevancia_score": round(info["score"], 4),
            "metodos_coincidencia": sorted(list(info["origenes"])),
            "contexto": encabezado_contextual + texto_final,
        })

    return resultados_finales


# ==============================================================================
# CATÁLOGO OFICIAL SAP CLOUDIFICATION REPOSITORY (CLEAN CORE & SUCESORES S/4HANA)
# ==============================================================================
_CACHE_CLEAN_CORE: Optional[Dict[str, Any]] = None
_CACHE_CLEAN_CORE_POR_NOMBRE: Optional[Dict[str, List[Dict[str, Any]]]] = None

_URLS_CLOUDIFICATION_REPO = {
    "classic": ("https://raw.githubusercontent.com/SAP/abap-atc-cr-cv-s4hc/main/src/objectClassifications_SAP.json", "objectClassifications"),
    "btp": ("https://raw.githubusercontent.com/SAP/abap-atc-cr-cv-s4hc/main/src/objectReleaseInfo_BTPLatest.json", "objectReleaseInfo"),
    "public_cloud": ("https://raw.githubusercontent.com/SAP/abap-atc-cr-cv-s4hc/main/src/objectReleaseInfoLatest.json", "objectReleaseInfo"),
    "pce_s4hana": ("https://raw.githubusercontent.com/SAP/abap-atc-cr-cv-s4hc/main/src/objectReleaseInfo_PCELatest.json", "objectReleaseInfo"),
}


def _clasificar_nivel_clean_core(state: str) -> Dict[str, str]:
    """Traduce el estado técnico del Cloudification Repository al Nivel oficial de Clean Core (A, B, C, D)."""
    st = (state or "").strip()
    if st == "released":
        return {
            "nivel": "Level A",
            "estado": "released",
            "resumen": "Liberado oficialmente para ABAP Cloud (100% Clean Core & Upgrade-Safe).",
        }
    if st == "classicAPI":
        return {
            "nivel": "Level B",
            "estado": "classicAPI",
            "resumen": "API Clásica recomendada por SAP (usar mediante wrapper Tier-2 cuando no exista API Nivel A).",
        }
    if st == "deprecated":
        return {
            "nivel": "Level C/D",
            "estado": "deprecated",
            "resumen": "Objeto obsoleto/deprecado en S/4HANA. Debe reemplazarse por su sucesor oficial Nivel A.",
        }
    if st in ("notToBeReleased", "noAPI"):
        return {
            "nivel": "Level D",
            "estado": st,
            "resumen": "No liberado para ABAP Cloud (No Clean Core). Reemplazar por vista CDS o API sucesora.",
        }
    return {
        "nivel": "Level C",
        "estado": st or "internal",
        "resumen": "Objeto interno o sin clasificación directa de liberación pública.",
    }


def _obtener_catalogo_clean_core() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """
    Carga en memoria los ~68,694 objetos oficiales del SAP Cloudification Repository
    desde clean_core_catalog.json.gz (o los descarga automáticamente del GitHub oficial de SAP si no existe).
    """
    global _CACHE_CLEAN_CORE, _CACHE_CLEAN_CORE_POR_NOMBRE
    if _CACHE_CLEAN_CORE is not None and _CACHE_CLEAN_CORE_POR_NOMBRE is not None:
        return _CACHE_CLEAN_CORE, _CACHE_CLEAN_CORE_POR_NOMBRE

    with _init_lock:
        if _CACHE_CLEAN_CORE is not None and _CACHE_CLEAN_CORE_POR_NOMBRE is not None:
            return _CACHE_CLEAN_CORE, _CACHE_CLEAN_CORE_POR_NOMBRE

        ruta_gz = CLEAN_CORE_CACHE_PATH
        if not os.path.exists(ruta_gz):
            alt_gz = os.path.join(DB_PATH, "clean_core_catalog.json.gz")
            if os.path.exists(alt_gz):
                ruta_gz = alt_gz

        catalog: Dict[str, Dict[str, Any]] = {}
        if os.path.exists(ruta_gz):
            try:
                with gzip.open(ruta_gz, "rt", encoding="utf-8") as f:
                    catalog = json.load(f)
            except Exception:
                catalog = {}

        # Si no existía el archivo local, lo construye desde el GitHub oficial de SAP
        if not catalog:
            ctx = ssl._create_unverified_context()
            for _, (url, root_key) in _URLS_CLOUDIFICATION_REPO.items():
                try:
                    req = urllib.request.urlopen(url, context=ctx, timeout=15)
                    items = json.loads(req.read().decode("utf-8")).get(root_key, [])
                    for item in items:
                        tadir_obj = item.get("tadirObject", "")
                        tadir_name = item.get("tadirObjName", "")
                        obj_type = item.get("objectType", tadir_obj)
                        obj_key = item.get("objectKey", tadir_name)
                        primary_name = obj_key if obj_type == "FUNC" else (tadir_name or obj_key)
                        if not primary_name:
                            continue
                        succs = []
                        for s in item.get("successors", []):
                            s_type = s.get("objectType") or s.get("tadirObject", "")
                            s_name = s.get("objectKey") or s.get("tadirObjName", "")
                            if s_name:
                                succs.append({"type": s_type, "name": s_name})
                        if item.get("successorConceptName"):
                            succs.append({"type": "CONCEPT", "name": item.get("successorConceptName")})

                        key = f"{obj_type}:{primary_name.upper()}"
                        existing = catalog.get(key, {})
                        catalog[key] = {
                            "type": obj_type,
                            "tadirType": tadir_obj or existing.get("tadirType", ""),
                            "name": primary_name.upper(),
                            "parent": tadir_name if obj_type == "FUNC" else existing.get("parent", ""),
                            "comp": item.get("applicationComponent", "") or existing.get("comp", ""),
                            "sw": item.get("softwareComponent", "") or existing.get("sw", ""),
                            "state": item.get("state", "") or existing.get("state", ""),
                            "labels": item.get("labels", existing.get("labels", [])),
                            "succ": succs if succs else existing.get("succ", []),
                        }
                except Exception:
                    continue
            if catalog:
                try:
                    with gzip.open(CLEAN_CORE_CACHE_PATH, "wt", encoding="utf-8") as f:
                        json.dump(catalog, f, separators=(",", ":"))
                except Exception:
                    pass

        por_nombre: Dict[str, List[Dict[str, Any]]] = {}
        for _, info in catalog.items():
            nom = info.get("name", "")
            if nom:
                por_nombre.setdefault(nom, []).append(info)

        _CACHE_CLEAN_CORE = catalog
        _CACHE_CLEAN_CORE_POR_NOMBRE = por_nombre
        return _CACHE_CLEAN_CORE, _CACHE_CLEAN_CORE_POR_NOMBRE


def consultar_clean_core_sap(
    objetos_o_busqueda: str,
    nivel_filtro: Optional[str] = None,
    tipo_objeto: Optional[str] = None,
    cruzar_con_libros: bool = True,
) -> Dict[str, Any]:
    """
    Motor de Compatibilidad S/4HANA & Clean Core (basado en SAP Cloudification Repository, estilo ROSA).
    Permite:
    1. Auditar una lista de objetos SAP (ej: 'MARA, BSEG, KNA1, BAPI_PO_CREATE1') y obtener su nivel Clean Core (A, B, C, D)
       y sus sucesores oficiales liberados (ej: I_Product, I_OperationalAcctgDocItem, I_Customer).
    2. Buscar objetos y APIs liberadas por palabras clave o componente (ej: 'PurchaseOrder', 'Billing', 'BusinessPartner').
    3. Cruzar automáticamente los objetos y sus sucesores con los 184 libros de SAP Press/Academia.
    """
    catalog, por_nombre = _obtener_catalogo_clean_core()
    if not catalog:
        return {"error": "No se pudo cargar el catálogo de SAP Cloudification Repository."}

    entrada = (objetos_o_busqueda or "").strip()
    if not entrada:
        return {"error": "Debe indicar al menos un objeto SAP o término de búsqueda."}

    candidatos_raw = [t.strip().upper() for t in re.split(r"[,;\s]+", entrada) if len(t.strip()) >= 2]
    filtro_nivel = (nivel_filtro or "").strip().upper()
    filtro_tipo = (tipo_objeto or "").strip().upper()

    resultados_exactos = []
    terminos_no_exactos = []

    for cand in candidatos_raw:
        matches = por_nombre.get(cand, [])
        if matches:
            for m in matches:
                if filtro_tipo and filtro_tipo not in (m.get("type", "").upper(), m.get("tadirType", "").upper()):
                    continue
                cc_info = _clasificar_nivel_clean_core(m.get("state", ""))
                if filtro_nivel and filtro_nivel not in cc_info["nivel"].upper() and filtro_nivel not in cc_info["estado"].upper():
                    continue
                # Enriquecer cada sucesor con su propio estado Clean Core
                sucesores_enriquecidos = []
                for s in m.get("succ", []):
                    s_name = s.get("name", "").upper()
                    s_matches = por_nombre.get(s_name, [])
                    s_state = s_matches[0].get("state", "released") if s_matches else "released"
                    s_cc = _clasificar_nivel_clean_core(s_state)
                    sucesores_enriquecidos.append({
                        "objeto_sucesor": s.get("name", ""),
                        "tipo": s.get("type", ""),
                        "clean_core_nivel": s_cc["nivel"],
                        "estado": s_cc["estado"],
                    })

                resultados_exactos.append({
                    "objeto": m.get("name"),
                    "tipo_objeto": m.get("type"),
                    "tadir_tipo": m.get("tadirType"),
                    "grupo_funcion": m.get("parent") or None,
                    "componente_aplicacion": m.get("comp"),
                    "componente_software": m.get("sw"),
                    "clean_core_nivel": cc_info["nivel"],
                    "estado_liberacion": cc_info["estado"],
                    "evaluacion": cc_info["resumen"],
                    "etiquetas": m.get("labels", []),
                    "sucesores_oficiales": sucesores_enriquecidos,
                })
        else:
            terminos_no_exactos.append(cand)

    # Búsqueda inteligente multi-token si no hubo match exacto (o para términos descriptivos)
    resultados_busqueda = []
    if not resultados_exactos and terminos_no_exactos:
        tokens = [t for t in terminos_no_exactos if len(t) >= 2]
        scored = []
        for nom, lista_infos in por_nombre.items():
            for info in lista_infos:
                if filtro_tipo and filtro_tipo not in (info.get("type", "").upper(), info.get("tadirType", "").upper()):
                    continue
                cc_info = _clasificar_nivel_clean_core(info.get("state", ""))
                if filtro_nivel and filtro_nivel not in cc_info["nivel"].upper() and filtro_nivel not in cc_info["estado"].upper():
                    continue

                comp = info.get("comp", "").upper()
                score = 0
                for tok in tokens:
                    if tok == nom:
                        score += 100
                    elif nom.startswith(tok) or nom.startswith(f"I_{tok}") or nom.startswith(f"CL_{tok}"):
                        score += 50
                    elif tok in nom:
                        score += 25
                    elif tok in comp:
                        score += 15
                if score > 0:
                    # Priorizar APIs liberadas Nivel A y objetos con sucesores claros
                    if info.get("state") == "released":
                        score += 10
                    elif info.get("succ"):
                        score += 5
                    scored.append((score, info, cc_info))

        scored.sort(key=lambda x: x[0], reverse=True)
        for score, m, cc_info in scored[:15]:
            sucesores_enriquecidos = [
                {"objeto_sucesor": s.get("name", ""), "tipo": s.get("type", "")}
                for s in m.get("succ", [])
            ]
            resultados_busqueda.append({
                "objeto": m.get("name"),
                "tipo_objeto": m.get("type"),
                "componente_aplicacion": m.get("comp"),
                "clean_core_nivel": cc_info["nivel"],
                "estado_liberacion": cc_info["estado"],
                "evaluacion": cc_info["resumen"],
                "sucesores_oficiales": sucesores_enriquecidos,
            })

    # Cruzar con los 184 libros en SQLite FTS5
    referencias_libros = []
    if cruzar_con_libros:
        conn = _obtener_conexion_sqlite()
        if conn is not None:
            terminos_libro = []
            for r in (resultados_exactos or resultados_busqueda)[:4]:
                terminos_libro.append(r["objeto"])
                for s in r.get("sucesores_oficiales", [])[:2]:
                    terminos_libro.append(s["objeto_sucesor"])
            terminos_libro = [t for t in dict.fromkeys(terminos_libro) if len(t) >= 3]
            if terminos_libro:
                expr = " OR ".join([f'"{t}"' for t in terminos_libro[:5]])
                try:
                    sql = """
                        SELECT e.embedding_id, f.string_value
                        FROM embedding_fulltext_search f
                        JOIN embeddings e ON f.rowid = e.id
                        WHERE embedding_fulltext_search MATCH ?
                        LIMIT 5
                    """
                    for eid, txt in conn.execute(sql, (expr,)).fetchall():
                        if "_chunk_" not in eid:
                            continue
                        fuente, str_chunk = eid.rsplit("_chunk_", 1)
                        if fuente in LIBROS_IGNORADOS:
                            continue
                        referencias_libros.append({
                            "fuente": fuente,
                            "categoria": clasificar_libro(fuente),
                            "bloque": int(str_chunk) if str_chunk.isdigit() else 0,
                            "extracto": txt[:320].replace("\n", " ").strip(),
                        })
                except Exception:
                    pass

    # Métricas de cumplimiento Clean Core
    todos = resultados_exactos or resultados_busqueda
    total_eval = len(todos)
    cumplen = sum(1 for r in todos if r["clean_core_nivel"] in ("Level A", "Level B"))
    tasa = round((cumplen / total_eval) * 100, 1) if total_eval else 0.0

    return {
        "fuente_oficial": "SAP Cloudification Repository (S/4HANA PCE, Public Cloud, BTP & Classic APIs)",
        "total_objetos_catalogo": len(catalog),
        "objetos_evaluados": total_eval,
        "tasa_cumplimiento_clean_core": f"{tasa}%",
        "resultados_exactos": resultados_exactos,
        "resultados_busqueda": resultados_busqueda,
        "citas_en_tus_libros_sap": referencias_libros,
    }


# ==============================================================================
# CONSULTA EN VIVO A SAP HELP PORTAL & SAP COMMUNITY (DOCUMENTACIÓN OFICIAL)
# ==============================================================================
def consultar_sap_help_oficial(
    consulta: str,
    incluir_comunidad: bool = True,
    max_resultados: int = 5,
) -> Dict[str, Any]:
    """
    Consulta la documentación oficial autorizada de SAP Help Portal (help.sap.com) y
    SAP Community (community.sap.com), devolviendo URLs oficiales, títulos y fragmentos,
    y cruzándolos con los manuales locales de la biblioteca.
    """
    q = (consulta or "").strip()
    if not q:
        return {"error": "La consulta no puede estar vacía."}

    ctx = ssl._create_unverified_context()
    resultados_sap_help = []
    resultados_comunidad = []

    def _llamar_endpoint_docs(tool_name: str, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        for endpoint in ("https://mcp-abap.marianzeis.de/mcp", "http://mcp-sap-docs.marianzeis.de/mcp"):
            try:
                payload = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": args},
                }).encode("utf-8")
                req = urllib.request.Request(
                    endpoint,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "User-Agent": "MCP-SAP-Libros/2.0",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    for line in raw.splitlines():
                        if line.startswith("data: "):
                            obj = json.loads(line[6:])
                            content = obj.get("result", {}).get("content", [])
                            if content and "text" in content[0]:
                                parsed = json.loads(content[0]["text"])
                                return parsed.get("results", [])
            except Exception:
                continue
        return []

    docs = _llamar_endpoint_docs("search", {"query": q})
    for d in docs[:max_resultados]:
        resultados_sap_help.append({
            "titulo": d.get("title", ""),
            "url_oficial": d.get("url", ""),
            "biblioteca": d.get("library_id", ""),
            "fragmento_autorizado": (d.get("snippet", "") or "")[:450],
        })

    if incluir_comunidad:
        comm = _llamar_endpoint_docs("sap_community_search", {"query": q})
        for c in comm[:max(3, max_resultados // 2)]:
            resultados_comunidad.append({
                "titulo": c.get("title", ""),
                "url_oficial": c.get("url", ""),
                "autor": c.get("author", ""),
                "fecha": c.get("published", ""),
                "fragmento_autorizado": (c.get("snippet", "") or "")[:400],
            })

    return {
        "consulta": q,
        "total_sap_help": len(resultados_sap_help),
        "documentacion_oficial_sap_help": resultados_sap_help,
        "comunidad_oficial_sap": resultados_comunidad,
    }


# ==============================================================================
# RESOLUCIÓN INTELIGENTE DE NOTAS SAP CITADAS EN LOS LIBROS
# ==============================================================================
def resolver_nota_sap(numero_o_tema: str, contexto_adicional: Optional[str] = None) -> Dict[str, Any]:
    """
    Localiza y explica una Nota SAP citada en la biblioteca de manuales oficiales.
    Extrae el propósito oficial, por qué los autores la recomiendan, los impactos de arquitectura,
    los objetos Clean Core relacionados y genera el enlace oficial me.sap.com/notes/<numero>.
    """
    texto_input = f"{numero_o_tema} {contexto_adicional or ''}".strip()
    match_num = re.search(r"\b([0-9]{5,8})\b", texto_input)
    numero = match_num.group(1) if match_num else None

    conn = _obtener_conexion_sqlite()
    if conn is None:
        return {"error": "Base de datos no disponible"}

    citas = []
    # 1. Si hay número de nota, búsqueda léxica directa
    if numero:
        sql = """
            SELECT e.embedding_id, f.string_value
            FROM embedding_fulltext_search f
            JOIN embeddings e ON f.rowid = e.id
            WHERE embedding_fulltext_search MATCH ?
            LIMIT 10
        """
        rows = conn.execute(sql, (f'"{numero}"',)).fetchall()
        for eid, txt in rows:
            if "_chunk_" not in eid:
                continue
            fuente, str_chunk = eid.rsplit("_chunk_", 1)
            if fuente in LIBROS_IGNORADOS:
                continue
            try:
                bloque = int(str_chunk)
            except ValueError:
                bloque = 0

            pos = txt.find(numero)
            ini = max(0, pos - 150)
            fin = min(len(txt), pos + 300)
            citas.append({
                "fuente": fuente,
                "categoria": clasificar_libro(fuente),
                "bloque": bloque,
                "extracto": txt[ini:fin].replace("\n", " ").strip(),
            })

    # 2. Si no hay número o no hubo citas por número, buscar por tema + 'Note'
    if not citas:
        terminos = [w for w in re.findall(r"[A-Za-z0-9_]{3,}", texto_input) if w.lower() not in ("nota", "note", "sap")]
        if terminos:
            expr = " AND ".join([f'"{t}"' for t in terminos[:4]]) + ' AND (Note OR Notas)'
            try:
                sql = """
                    SELECT e.embedding_id, f.string_value
                    FROM embedding_fulltext_search f
                    JOIN embeddings e ON f.rowid = e.id
                    WHERE embedding_fulltext_search MATCH ?
                    LIMIT 6
                """
                rows = conn.execute(sql, (expr,)).fetchall()
                for eid, txt in rows:
                    if "_chunk_" not in eid:
                        continue
                    fuente, str_chunk = eid.rsplit("_chunk_", 1)
                    if fuente in LIBROS_IGNORADOS:
                        continue
                    citas.append({
                        "fuente": fuente,
                        "categoria": clasificar_libro(fuente),
                        "bloque": int(str_chunk),
                        "extracto": txt[:400].replace("\n", " ").strip(),
                    })
            except Exception:
                pass

    # 3. Detectar objetos SAP mencionados en los extractos y verificar su estado Clean Core
    objetos_clean_core = []
    try:
        _, por_nombre = _obtener_catalogo_clean_core()
        texto_citas = " ".join([c["extracto"] for c in citas]) + " " + texto_input
        tokens_mayus = set(re.findall(r"\b[A-Z][A-Z0-9_/]{3,30}\b", texto_citas))
        ignorados = {"NOTE", "NOTES", "HANA", "S4HANA", "ABAP", "TABLE", "REPORT", "CHECK", "SYSTEM", "FIGURE", "CHAPTER"}
        for tok in sorted(tokens_mayus):
            if tok in ignorados or tok not in por_nombre:
                continue
            for m in por_nombre[tok][:1]:
                cc = _clasificar_nivel_clean_core(m.get("state", ""))
                objetos_clean_core.append({
                    "objeto": tok,
                    "tipo": m.get("type"),
                    "clean_core_nivel": cc["nivel"],
                    "sucesores": [s.get("name") for s in m.get("succ", [])],
                })
    except Exception:
        pass

    return {
        "numero_nota": numero,
        "enlace_oficial_launchpad": f"https://me.sap.com/notes/{numero}" if numero else None,
        "total_citas_encontradas": len(citas),
        "referencias_en_libros": citas,
        "objetos_clean_core_relacionados": objetos_clean_core[:8],
        "consejo_aplicacion": (
            f"Para consultar la corrección técnica completa con tu S-User, visita {f'https://me.sap.com/notes/{numero}' if numero else 'el Launchpad de SAP'}. "
            "En el sistema SAP GUI puedes revisar su estado o implementarla directamente mediante la transacción SNOTE."
        ),
    }


# ==============================================================================
# FUNCIONES DE COMPATIBILIDAD CON SCRIPTS EXISTENTES (ingerir.py, query.py, etc.)
# ==============================================================================
def agregar_fragmentos(textos, metadatos, ids):
    """Convierte bloques de texto en vectores numéricos y los guarda en la BD."""
    modelo = obtener_modelo()
    coleccion = obtener_coleccion()
    raw_emb = modelo.encode(textos)
    embeddings = raw_emb.tolist() if hasattr(raw_emb, "tolist") else list(raw_emb)
    coleccion.add(
        documents=textos,
        embeddings=embeddings,
        metadatas=metadatos,
        ids=ids,
    )
    if os.path.exists(CATALOG_CACHE_PATH):
        try:
            os.remove(CATALOG_CACHE_PATH)
        except Exception:
            pass


def buscar_similitud(consulta: str, top_k: int = 10) -> Dict[str, Any]:
    """
    Mantiene el formato clásico compatible con ChromaDB {'documents': [[...]], 'metadatas': [[...]]},
    potenciado por el nuevo motor híbrido bilingüe con contexto expandido.
    """
    resultados = buscar_hibrido_sap(consulta, top_k=top_k, ventana_vecinos=1)
    if not resultados:
        return {"documents": [[]], "metadatas": [[]]}

    documentos = [r["contexto"] for r in resultados]
    metadatas = [
        {
            "fuente": r["fuente"],
            "bloque": r["bloque"],
            "rango_bloques": r["rango_bloques"],
            "categoria": r["categoria"],
            "relevancia": r["relevancia_score"],
        }
        for r in resultados
    ]
    return {"documents": [documentos], "metadatas": [metadatas]}
