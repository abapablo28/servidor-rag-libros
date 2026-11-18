import sys
import json
import threading
from typing import Optional
from mcp.server.fastmcp import FastMCP
from bd_config import (
    buscar_hibrido_sap,
    leer_bloques_libro,
    obtener_catalogo_libros,
    obtener_coleccion,
    obtener_modelo,
    resolver_nota_sap,
    consultar_clean_core_sap,
    consultar_sap_help_oficial,
    _obtener_catalogo_clean_core,
    _obtener_conexion_sqlite,
)

# Calentar motores en segundo plano al arrancar para que la primera consulta responda en <1s
def _calentar_servidor():
    try:
        _obtener_conexion_sqlite()
        obtener_catalogo_libros()
        _obtener_catalogo_clean_core()
        obtener_coleccion()
        obtener_modelo()
    except Exception:
        pass

threading.Thread(target=_calentar_servidor, daemon=True).start()

# ==============================================================================
# INSTRUCCIONES GLOBALES DEL SERVIDOR MCP (Para Claude, Antigravity y ChatGPT)
# ==============================================================================
INSTRUCCIONES_SISTEMA = """
Eres un asistente conectado a la Biblioteca Oficial de Libros y Manuales de Academia SAP + Motor Clean Core & SAP Help (Servidor-RAG-SAP).
Contiene ~184 libros oficiales de SAP Press y manuales de Academia SAP en español e inglés (ABAP, Clean ABAP, OO ABAP, CDS, RAP, Fiori/UI5, Migración S/4HANA/ATC, HANA Performance HA400, Ampliaciones BC425, FI S4F12-17/TFIN50, MM TSCM50/52, SD TSCM60, EWM, Workflow, SmartForms/Adobe, BTP/CPI, HCM THR12, BW TBW42) + 68,694 objetos oficiales del SAP Cloudification Repository (estilo ROSA).

REGLAS DE USO PARA RESPONDER CON ALTA CALIDAD Y VELOCIDAD:
1. SIEMPRE que el usuario pida código ABAP, vistas CDS, RAP, optimización SQL HANA, migración a S/4HANA o tenga una consulta funcional (FI, MM, SD, EWM, BTP, etc.), consulta primero este MCP antes de responder de memoria.
2. Muchos de los mejores libros técnicos de SAP Press están en INGLÉS y los manuales de academia están en ESPAÑOL. Por eso, al llamar a `consultar_conocimiento`, `consultar_abap_tecnico` o `consultar_proceso_funcional`, rellena SIEMPRE el parámetro `query_en` con la traducción técnica al inglés de la consulta.
3. Para máxima rapidez, pide entre 3 y 5 resultados (`cantidad_resultados=4` por defecto). Si un fragmento devuelto muestra un código ABAP o una explicación paso a paso que continúa en el bloque siguiente, usa `leer_paginas_libro(fuente, bloque_inicio, bloque_fin)` para leer los bloques siguientes del mismo libro.
4. Si en un libro o en tu análisis encuentras citada una Nota SAP (ej. Note 2399707, Note 2267308, Note 1648480, etc.), usa `consultar_nota_sap(numero_o_tema)` para obtener el resumen oficial de los libros, los objetos Clean Core afectados y el enlace directo al Launchpad me.sap.com/notes/<numero>.
5. Cuando el usuario pregunte por compatibilidad S/4HANA, Clean Core (Niveles A, B, C, D), objetos obsoletos o qué vista CDS / API usar en lugar de tablas o BAPIs clásicas (ej. MARA, BSEG, KNA1, KONV, BAPI_PO_CREATE1), usa `consultar_clean_core_sucesores(objetos_o_busqueda)`.
6. Cuando necesites enlaces y fragmentos actualizados de la documentación oficial web de SAP Help Portal (`help.sap.com`) o blogs de SAP Community, usa `consultar_sap_help_oficial_web(consulta)`.
7. En tu respuesta final al usuario, cita los manuales de SAP utilizados (nombre del PDF y bloques) y adapta el código o la explicación funcional fielmente a las buenas prácticas del libro y Clean Core.
""".strip()

mcp = FastMCP(
    "Servidor-RAG-SAP",
    instructions=INSTRUCCIONES_SISTEMA,
    host="0.0.0.0",
    port=8000,
)


# ==============================================================================
# 1. HERRAMIENTA PRINCIPAL (HÍBRIDA BILINGÜE + RETROCOMPATIBLE)
# ==============================================================================
@mcp.tool()
def consultar_conocimiento(
    pregunta: str,
    cantidad_resultados: int = 4,
    query_en: Optional[str] = None,
    modulo: Optional[str] = None,
    libro_filtro: Optional[str] = None,
    expandir_contexto: bool = True,
) -> str:
    """
    Busca en la biblioteca de libros y manuales de SAP (técnicos ABAP y funcionales) usando
    búsqueda híbrida bilingüe (Vectorial + Léxica BM25) y reconstrucción de páginas completas.

    Args:
        pregunta: La pregunta, concepto, transacción, tabla o proceso a investigar (en español o inglés).
        cantidad_resultados: Número de fragmentos distintos a extraer (por defecto 6, máximo 15).
        query_en: (Muy recomendado) Traducción de la consulta al inglés técnico de SAP para encontrar también en libros de SAP Press en inglés (ej. "custom code migration S/4HANA ATC check").
        modulo: (Opcional) Filtrar por dominio SAP: 'ABAP', 'S4HANA', 'CDS', 'RAP', 'FIORI', 'HANA', 'FI', 'MM', 'EWM', 'SD', 'BTP', 'WORKFLOW', 'HR', 'BW'.
        libro_filtro: (Opcional) Parte del nombre de un libro específico (ej. 'Clean-ABAP', 'HA400', 'TSCM52', 'S4F12').
        expandir_contexto: Si es True (por defecto), une automáticamente el bloque anterior y siguiente del libro para evitar código o explicaciones cortadas.
    """
    try:
        ventana = 1 if expandir_contexto else 0
        resultados = buscar_hibrido_sap(
            pregunta=pregunta,
            top_k=cantidad_resultados,
            query_en=query_en,
            modulo=modulo,
            libro_filtro=libro_filtro,
            ventana_vecinos=ventana,
        )

        if not resultados:
            return json.dumps({
                "mensaje": f"No se encontró información relevante en los manuales para: '{pregunta}'.",
                "sugerencia": "Intenta usar `listar_libros_sap` para ver los manuales disponibles o términos más generales.",
                "resultados": [],
            }, ensure_ascii=False)

        return json.dumps({
            "mensaje": f"Se encontraron {len(resultados)} fragmentos de alta relevancia en la biblioteca SAP.",
            "instruccion_ia": "Basa tu respuesta o código en estos fragmentos oficiales de SAP. Si necesitas ver cómo continúa algún ejemplo o sección, llama a `leer_paginas_libro` con el nombre de la `fuente` y el siguiente `bloque`.",
            "resultados": resultados,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"Error al consultar la base de conocimientos SAP: {str(e)}"}, ensure_ascii=False)


# ==============================================================================
# 2. HERRAMIENTA ESPECIALIZADA PARA CÓDIGO ABAP / CDS / RAP / HANA / S4HANA
# ==============================================================================
@mcp.tool()
def consultar_abap_tecnico(
    requerimiento_abap: str,
    keywords_ingles: Optional[str] = None,
    enfoque: str = "ABAP",
    cantidad_resultados: int = 5,
) -> str:
    """
    Usa esta herramienta SIEMPRE que el usuario pida escribir, revisar, optimizar o migrar código ABAP,
    vistas CDS, modelo RAP, OData, BAdIs/User Exits, SmartForms/Adobe Forms o SQL para SAP HANA.
    Extrae ventanas amplias (5 bloques unidos por resultado) para que los ejemplos de código salgan completos.

    Args:
        requerimiento_abap: Qué código, sentencia, patrón o problema técnico ABAP se necesita resolver.
        keywords_ingles: Términos técnicos en inglés (ej. 'Clean ABAP exception class TRY CATCH', 'CDS view association annotation', 'RAP behavior definition validation').
        enfoque: Área técnica principal: 'ABAP' (Clean ABAP, OO, sintaxis, BC425), 'CDS' (Core Data Services), 'RAP' (RESTful ABAP), 'HANA' (HA400, SQL, AMDP, performance), 'MIGRACION' (S/4HANA custom code, ATC), 'WORKFLOW' (Workflow, Forms, LSMW).
        cantidad_resultados: Cantidad de secciones amplias de libros a devolver (por defecto 5).
    """
    try:
        resultados = buscar_hibrido_sap(
            pregunta=requerimiento_abap,
            top_k=cantidad_resultados,
            query_en=keywords_ingles or requerimiento_abap,
            modulo=enfoque,
            ventana_vecinos=2,  # Une [bloque-2 .. bloque+2] para entregar ejemplos de código completos
        )

        return json.dumps({
            "mensaje": f"Contexto técnico ABAP extraído de {len(resultados)} manuales oficiales (ventana extendida para código completo).",
            "guia_aplicacion": (
                "1. Aplica las convenciones de sintaxis moderna ABAP (7.40+ / S/4HANA / Clean ABAP) mostradas en estos libros.\n"
                "2. Cita el libro fuente (ej. Clean ABAP, Core Data Services for ABAP, HA400, BC425, Migrating Your Custom Code to SAP S/4HANA).\n"
                "3. Si un listado de código continúa después del rango de bloques devuelto, usa `leer_paginas_libro`."
            ),
            "resultados": resultados,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Error en consulta técnica ABAP: {str(e)}"}, ensure_ascii=False)


# ==============================================================================
# 3. HERRAMIENTA ESPECIALIZADA PARA CONSULTAS FUNCIONALES Y PROCESOS SAP
# ==============================================================================
@mcp.tool()
def consultar_proceso_funcional(
    consulta_funcional: str,
    modulo_sap: str,
    keywords_ingles: Optional[str] = None,
    cantidad_resultados: int = 6,
) -> str:
    """
    Usa esta herramienta cuando el usuario haga preguntas funcionales de procesos de negocio SAP,
    configuración (Customizing / SPRO), transacciones, tablas estándar, documentos o integración entre módulos.

    Args:
        consulta_funcional: Descripción de la duda funcional, escenario de negocio, error o transacción.
        modulo_sap: Módulo funcional: 'FI' (Finanzas S4F12-17, TFIN50), 'MM' (Compras/Inventario TSCM50/52), 'EWM' (Almacenes), 'SD' (Ventas/Facturación TSCM60), 'HR' (Nómina/HCM THR12), 'BTP' (CPI/Integración/eDocument), 'BW' (Analytics/Datasphere), 'S4HANA' (Activate/Conversión).
        keywords_ingles: Traducción de los conceptos clave al inglés (ej. 'goods receipt MIGO movement type valuation', 'payment differences clearing FB05').
        cantidad_resultados: Cantidad de fragmentos extendidos a devolver (por defecto 6).
    """
    try:
        resultados = buscar_hibrido_sap(
            pregunta=consulta_funcional,
            top_k=cantidad_resultados,
            query_en=keywords_ingles,
            modulo=modulo_sap,
            ventana_vecinos=2,
        )

        return json.dumps({
            "mensaje": f"Se encontraron {len(resultados)} secciones funcionales para el módulo {modulo_sap}.",
            "guia_aplicacion": (
                "Explica el proceso paso a paso indicando transacciones estándar, rutas de parametrización o impactos "
                "organizativos mencionados en los manuales de Academia SAP / SAP Press recuperados."
            ),
            "resultados": resultados,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Error en consulta funcional SAP: {str(e)}"}, ensure_ascii=False)


# ==============================================================================
# 4. HERRAMIENTA PARA PASAR LA PÁGINA / LEER SECUENCIA CONTINUA DE UN LIBRO
# ==============================================================================
@mcp.tool()
def leer_paginas_libro(fuente: str, bloque_inicio: int, bloque_fin: int) -> str:
    """
    Lee una secuencia continua de bloques (páginas/secciones) de un manual SAP específico.
    Úsala cuando un resultado anterior tenga un ejemplo de código ABAP o una explicación
    que continúa en los bloques siguientes o anteriores del mismo libro.

    Args:
        fuente: Nombre exacto del archivo PDF tal como aparece en el campo 'fuente' (ej. 'HA400 (SAP HANA 2.0 SPS02 - V16) ES.pdf').
        bloque_inicio: Número de bloque inicial a leer (ej. 118).
        bloque_fin: Número de bloque final a leer (máximo 15 bloques por llamada, ej. 124).
    """
    try:
        datos = leer_bloques_libro(fuente=fuente, bloque_inicio=bloque_inicio, bloque_fin=bloque_fin)
        return json.dumps(datos, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Error al leer bloques del libro '{fuente}': {str(e)}"}, ensure_ascii=False)


# ==============================================================================
# 5. HERRAMIENTA PARA EXPLORAR EL CATÁLOGO DE MANUALES SAP DISPONIBLES
# ==============================================================================
@mcp.tool()
def listar_libros_sap(categoria_o_filtro: Optional[str] = None) -> str:
    """
    Lista los libros y manuales de SAP disponibles en la base de conocimientos, junto con su
    categoría, idioma (ES/EN) y tamaño en bloques.

    Args:
        categoria_o_filtro: (Opcional) Filtra por categoría ('ABAP_CORE', 'S4HANA_MIGRATION', 'CDS_RAP_FIORI',
                            'HANA_PERF', 'FI_CO', 'MM_EWM', 'SD', 'BTP_INTEGRATION', 'WORKFLOW_FORMS', 'HR_HCM', 'BW_ANALYTICS')
                            o por cualquier palabra en el título del libro (ej. 'Fiori', 'S4F', 'TSCM', 'Clean').
    """
    try:
        catalogo = obtener_catalogo_libros()
        if categoria_o_filtro:
            f_low = categoria_o_filtro.strip().lower()
            catalogo = [
                b for b in catalogo
                if f_low in b["fuente"].lower()
                or f_low in b.get("titulo", "").lower()
                or f_low in b["categoria"].lower()
            ]
        return json.dumps({
            "total_libros": len(catalogo),
            "libros": catalogo,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Error al listar libros: {str(e)}"}, ensure_ascii=False)


# ==============================================================================
# 6. HERRAMIENTA PARA RESOLUCIÓN Y CONTEXTO DE NOTAS SAP CITADAS EN LIBROS
# ==============================================================================
@mcp.tool()
def consultar_nota_sap(numero_o_tema: str, contexto_adicional: Optional[str] = None) -> str:
    """
    Localiza y explica una Nota SAP o Simplification Item citado en la biblioteca de manuales oficiales.
    Extrae por qué los autores de SAP Press/Academia recomiendan esta nota, los cambios arquitectónicos
    o de datos asociados (ej: CVI, ACDOCA, MATNR, ST03N, S4TWL), los objetos Clean Core afectados y genera
    el enlace oficial directo al Launchpad me.sap.com/notes/<numero>.

    Args:
        numero_o_tema: Número de la Nota SAP (ej. '2399707', '2267308', '1648480') o nombre del tema/reporte ('/SDF/RC_START', 'SD Pricing data model', 'CVI Business Partner').
        contexto_adicional: (Opcional) Términos adicionales o pregunta específica sobre la nota.
    """
    try:
        res = resolver_nota_sap(numero_o_tema=numero_o_tema, contexto_adicional=contexto_adicional)
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Error al resolver Nota SAP: {str(e)}"}, ensure_ascii=False)


# ==============================================================================
# 7. HERRAMIENTA DE COMPATIBILIDAD S/4HANA & CLEAN CORE (ESTILO ROSA INTEGRADO)
# ==============================================================================
@mcp.tool()
def consultar_clean_core_sucesores(
    objetos_o_busqueda: str,
    nivel_filtro: Optional[str] = None,
    tipo_objeto: Optional[str] = None,
    cruzar_con_libros: bool = True,
) -> str:
    """
    Consulta el SAP Cloudification Repository oficial integrado (~68,694 objetos SAP para S/4HANA Private/Public Cloud,
    BTP ABAP Environment y Classic APIs, estilo ROSA).
    Evalúa si una tabla, clase, vista CDS, función/BAPI o transacción está liberada para Clean Core (Nivel A, B, C, D),
    encuentra sus objetos sucesores oficiales en S/4HANA (ej. MARA -> I_PRODUCT, BSEG -> I_OPERATIONALACCTGDOCITEM,
    KNA1 -> I_CUSTOMER) y cruza la información con tus 184 libros de SAP Press y Academia.

    Args:
        objetos_o_busqueda: Uno o varios objetos separados por coma (ej. 'MARA, BSEG, KNA1, BAPI_PO_CREATE1') o término de búsqueda ('PurchaseOrder', 'BillingDocument', 'I_Product').
        nivel_filtro: (Opcional) Filtrar por nivel Clean Core: 'Level A' (released), 'Level B' (classicAPI), 'Level C', 'Level D' (notToBeReleased/deprecated).
        tipo_objeto: (Opcional) Filtrar por tipo TADIR: 'TABL', 'DDLS', 'CDS_STOB', 'CLAS', 'FUNC', 'BDEF', 'INTF'.
        cruzar_con_libros: Si es True (por defecto), incluye citas y capítulos de los libros locales donde se explica el objeto o su sucesor.
    """
    try:
        res = consultar_clean_core_sap(
            objetos_o_busqueda=objetos_o_busqueda,
            nivel_filtro=nivel_filtro,
            tipo_objeto=tipo_objeto,
            cruzar_con_libros=cruzar_con_libros,
        )
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Error al consultar Clean Core / Cloudification Repository: {str(e)}"}, ensure_ascii=False)


# ==============================================================================
# 8. HERRAMIENTA DE DOCUMENTACIÓN OFICIAL SAP HELP & SAP COMMUNITY
# ==============================================================================
@mcp.tool()
def consultar_sap_help_oficial_web(
    consulta: str,
    incluir_comunidad: bool = True,
    max_resultados: int = 5,
) -> str:
    """
    Busca URLs, secciones y fragmentos autorizados en la documentación oficial de SAP Help Portal (help.sap.com,
    ABAP Keyword Documentation, RAP/CDS/S4HANA Help) y blogs técnicos de SAP Community (community.sap.com).
    Complementa los libros locales con enlaces oficiales vivos.

    Args:
        consulta: Término técnico, sintaxis ABAP, vista CDS, RAP o proceso funcional (preferiblemente en inglés, ej. 'RAP behavior definition determinations', 'Clean Core extensibility tiers').
        incluir_comunidad: Si es True (por defecto), incluye también artículos y soluciones de SAP Community.
        max_resultados: Número máximo de enlaces oficiales a devolver (por defecto 5).
    """
    try:
        res = consultar_sap_help_oficial(
            consulta=consulta,
            incluir_comunidad=incluir_comunidad,
            max_resultados=max_resultados,
        )
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Error al consultar SAP Help oficial: {str(e)}"}, ensure_ascii=False)


# ==============================================================================
# RECURSOS Y PROMPTS MCP (Para Claude Desktop, Antigravity y Clientes MCP)
# ==============================================================================
@mcp.resource("sap://catalogo/libros")
def recurso_catalogo_libros() -> str:
    """Catálogo completo de manuales de Academia SAP y libros de SAP Press indexados."""
    catalogo = obtener_catalogo_libros()
    return json.dumps({"total_libros": len(catalogo), "libros": catalogo}, ensure_ascii=False, indent=2)


@mcp.prompt()
def asistente_codigo_abap(requerimiento: str) -> str:
    """Plantilla para pedir desarrollo o refactorización de código ABAP respaldado por libros de SAP."""
    return (
        f"Necesito resolver el siguiente requerimiento técnico en SAP ABAP:\n\n"
        f"\"{requerimiento}\"\n\n"
        f"Por favor:\n"
        f"1. Usa primero la herramienta `consultar_abap_tecnico` pasando el requerimiento y sus keywords en inglés (`keywords_ingles`).\n"
        f"2. Si algún ejemplo de código de los libros queda cortado, usa `leer_paginas_libro` para ver los bloques siguientes.\n"
        f"3. Escribe el código siguiendo las prácticas modernas de Clean ABAP / S/4HANA de los libros encontrados y cita las fuentes."
    )


@mcp.prompt()
def consultor_funcional_sap(consulta: str, modulo: str = "FI") -> str:
    """Plantilla para resolver consultas funcionales de SAP basadas en manuales de Academia."""
    return (
        f"Tengo la siguiente consulta funcional en SAP (Módulo {modulo}):\n\n"
        f"\"{consulta}\"\n\n"
        f"Por favor:\n"
        f"1. Usa primero la herramienta `consultar_proceso_funcional` indicando `modulo_sap='{modulo}'` y `keywords_ingles`.\n"
        f"2. Si necesitas leer más páginas de un manual encontrado, usa `leer_paginas_libro`.\n"
        f"3. Explica la solución paso a paso (transacciones, configuración SPRO, flujo de documentos) citando los manuales oficiales."
    )


# ==============================================================================
# SERVIDOR MULTITRANSPORTE: STDIO + SSE + STREAMABLE HTTP (/mcp) + REST OPENAPI
# ==============================================================================
def crear_app_web_universal():
    """
    Crea una aplicación ASGI unificada compatible simultáneamente con:
    - Antigravity / Clientes SSE: GET /sse y POST /messages/ (con parche POST /sse)
    - Claude Web / ChatGPT MCP Connectors (Estándar moderno): /mcp (Streamable HTTP)
    - ChatGPT Custom GPT Actions (OpenAPI REST): POST /api/consultar, GET /api/libros, GET /openapi.json
    """
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route, Mount
    from starlette.middleware.cors import CORSMiddleware

    sse_app = mcp.sse_app()
    streamable_app = mcp.streamable_http_app()

    async def health_endpoint(request):
        catalogo = obtener_catalogo_libros()
        return JSONResponse({
            "status": "ok",
            "servidor": "Servidor-RAG-SAP",
            "libros_activos": len(catalogo),
            "endpoints": {
                "mcp_streamable_http": "/mcp",
                "mcp_sse": "/sse",
                "rest_consultar": "/api/consultar",
                "rest_libros": "/api/libros",
                "openapi_schema": "/openapi.json",
            },
        })

    async def api_listar_libros(request):
        filtro = request.query_params.get("filtro")
        data = json.loads(listar_libros_sap(filtro))
        return JSONResponse(data)

    async def api_consultar(request):
        try:
            if request.method == "GET":
                pregunta = request.query_params.get("pregunta", "")
                query_en = request.query_params.get("query_en")
                modulo = request.query_params.get("modulo")
                libro_filtro = request.query_params.get("libro_filtro")
                top_k = int(request.query_params.get("cantidad_resultados", "6"))
            else:
                body = await request.json()
                pregunta = body.get("pregunta", "")
                query_en = body.get("query_en")
                modulo = body.get("modulo")
                libro_filtro = body.get("libro_filtro")
                top_k = int(body.get("cantidad_resultados", 6))

            if not pregunta:
                return JSONResponse({"error": "El parámetro 'pregunta' es obligatorio."}, status_code=400)

            res_str = consultar_conocimiento(
                pregunta=pregunta,
                cantidad_resultados=top_k,
                query_en=query_en,
                modulo=modulo,
                libro_filtro=libro_filtro,
                expandir_contexto=True,
            )
            return JSONResponse(json.loads(res_str))
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    async def openapi_schema(request):
        host_url = str(request.base_url).rstrip("/")
        schema = {
            "openapi": "3.1.0",
            "info": {
                "title": "Servidor RAG SAP - Biblioteca Oficial SAP Press & Academia",
                "description": "API para consultar manuales oficiales de SAP (ABAP, S/4HANA, CDS, RAP, FI, MM, SD, EWM, BTP, HANA) desde ChatGPT Actions o clientes HTTP.",
                "version": "2.0.0",
            },
            "servers": [{"url": host_url}],
            "paths": {
                "/api/consultar": {
                    "post": {
                        "operationId": "consultarConocimientoSAP",
                        "summary": "Busca fragmentos técnicos ABAP o funcionales en los libros oficiales de SAP.",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["pregunta"],
                                        "properties": {
                                            "pregunta": {"type": "string", "description": "Pregunta o requerimiento técnico/funcional SAP."},
                                            "query_en": {"type": "string", "description": "Traducción técnica al inglés para buscar también en libros de SAP Press."},
                                            "modulo": {"type": "string", "description": "Módulo opcional: ABAP, S4HANA, CDS, RAP, FIORI, HANA, FI, MM, EWM, SD, BTP, WORKFLOW, HR, BW."},
                                            "libro_filtro": {"type": "string", "description": "Filtro opcional por nombre de libro PDF."},
                                            "cantidad_resultados": {"type": "integer", "default": 6},
                                        },
                                    }
                                }
                            },
                        },
                        "responses": {"200": {"description": "Fragmentos recuperados de los manuales de SAP."}},
                    }
                },
                "/api/libros": {
                    "get": {
                        "operationId": "listarLibrosSAP",
                        "summary": "Lista el catálogo de libros y manuales de SAP disponibles.",
                        "parameters": [
                            {"name": "filtro", "in": "query", "required": False, "schema": {"type": "string"}}
                        ],
                        "responses": {"200": {"description": "Lista de libros indexados."}},
                    }
                },
            },
        }
        return JSONResponse(schema)

    rest_app = Starlette(
        routes=[
            Route("/health", health_endpoint, methods=["GET"]),
            Route("/api/libros", api_listar_libros, methods=["GET"]),
            Route("/api/consultar", api_consultar, methods=["GET", "POST"]),
            Route("/openapi.json", openapi_schema, methods=["GET"]),
        ]
    )

    # Enrutador ASGI principal que combina Streamable HTTP (/mcp), SSE (/sse, /messages) y REST (/api/*)
    async def unified_asgi(scope, receive, send):
        if scope["type"] == "lifespan":
            # Inicializar el gestor de sesiones de Streamable HTTP cuando arranca Uvicorn
            async with mcp.session_manager.run():
                await rest_app(scope, receive, send)
            return

        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "GET")

            # 1. Endpoints REST y OpenAPI (ChatGPT Custom GPT Actions / Healthcheck)
            if path in ("/health", "/api/libros", "/api/consultar", "/openapi.json"):
                await rest_app(scope, receive, send)
                return

            # 2. Transporte moderno Streamable HTTP (/mcp) para Claude, ChatGPT MCP y clientes recientes
            if path == "/mcp" or path.startswith("/mcp/"):
                await streamable_app(scope, receive, send)
                return

            # 3. Parche de compatibilidad Antigravity (POST /sse -> /messages/)
            if method == "POST" and path == "/sse":
                scope = dict(scope)
                scope["path"] = "/messages/"

        await sse_app(scope, receive, send)

    return CORSMiddleware(
        unified_asgi,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )


if __name__ == "__main__":
    if "--web" in sys.argv:
        import uvicorn
        print("Iniciando Servidor RAG SAP Universal (SSE + Streamable HTTP /mcp + OpenAPI REST) en puerto 8000...", file=sys.stderr)
        app = crear_app_web_universal()
        uvicorn.run(app, host="0.0.0.0", port=8000)
    elif "--streamable-http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
