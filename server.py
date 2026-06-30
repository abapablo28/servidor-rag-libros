import sys
from mcp.server.fastmcp import FastMCP
from bd_config import buscar_similitud

# 1. Inicializar el servidor MCP
mcp = FastMCP("Servidor-RAG-SAP")

# 2. Definir la herramienta de busqueda semantica (RAG)
@mcp.tool()
def consultar_conocimiento(pregunta: str) -> str:
    """
    Busca en la base de conocimientos tecnica local la respuesta a una pregunta.
    Usa esta herramienta cuando necesites investigar conceptos de los manuales.
    """
    try:
        # Llamar a la funcion que creamos en bd_config.py
        resultados = buscar_similitud(pregunta, top_k=3)
        
        # Validar si la base de datos devolvio resultados
        if not resultados or not resultados.get('documents') or not resultados['documents'][0]:
            return f"No se encontro informacion relevante para: '{pregunta}'."
        
        # Formatear los resultados para que la IA los pueda leer facilmente
        respuesta = "He encontrado los siguientes fragmentos tecnicos:\n\n"
        
        documentos = resultados['documents'][0]
        metadatos = resultados['metadatas'][0]
        
        for i in range(len(documentos)):
            texto = documentos[i]
            fuente = metadatos[i].get("fuente", "Documento desconocido")
            
            respuesta += f"FUENTE: {fuente}\n"
            respuesta += f"CONTEXTO: {texto}\n"
            respuesta += "-" * 50 + "\n"
            
        return respuesta
        
    except Exception as e:
        return f"Error interno al consultar la base de datos: {str(e)}"

if __name__ == "__main__":
    # 3. Ejecutar el servidor
    print("Servidor RAG MCP iniciado. Conectado a la base de vectores.", file=sys.stderr)
    
    # Soporte dual: Si escribes --web arranca para internet, si no, arranca local
    if "--web" in sys.argv:
        print("Iniciando en Modo Web (HTTP/SSE) en el puerto 8000...", file=sys.stderr)
        mcp.run(transport='sse')
    else:
        mcp.run()