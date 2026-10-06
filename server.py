import sys
from mcp.server.fastmcp import FastMCP
from bd_config import buscar_similitud

# 1. Inicializar el servidor MCP (Configurado para escuchar en cualquier IP)
mcp = FastMCP("Servidor-RAG-SAP", host="0.0.0.0", port=8000, sse_path="/sse", message_path="/sse")

# 2. Definir la herramienta de busqueda semantica (RAG)
@mcp.tool()
def consultar_conocimiento(pregunta: str, cantidad_resultados: int = 5) -> str:
    """
    Busca en la base de conocimientos SAP (tanto técnica como funcional) la respuesta a una pregunta.
    Usa esta herramienta SIEMPRE que necesites investigar manuales, procesos de negocio, configuraciones, transacciones o código.
    
    Args:
        pregunta: La pregunta, concepto o proceso exacto que deseas investigar.
        cantidad_resultados: (Opcional) Número de fragmentos a extraer de los libros. Por defecto es 5, pero puedes pedir hasta 15 si necesitas mucho contexto.
    """
    try:
        # Llamar a la funcion de la BD con el parametro dinámico
        resultados = buscar_similitud(pregunta, top_k=cantidad_resultados)
        
        # Validar si la base de datos devolvio resultados
        if not resultados or not resultados.get('documents') or not resultados['documents'][0]:
            return f"No se encontro informacion relevante en los manuales para: '{pregunta}'."
        
        # Formatear los resultados para la IA y el usuario final
        respuesta = f"He encontrado los siguientes {len(resultados['documents'][0])} fragmentos en la biblioteca:\n\n"
        
        documentos = resultados['documents'][0]
        metadatos = resultados['metadatas'][0]
        
        for i in range(len(documentos)):
            texto = documentos[i]
            
            # Limpiar el texto de caracteres nulos o corruptos (típico de PDFs) que rompen el JSON
            texto_limpio = texto.replace('\x00', '').encode('utf-8', 'ignore').decode('utf-8')
            
            # Extraer el nombre del PDF o documento
            fuente = metadatos[i].get("fuente", "Documento desconocido")
            pagina = metadatos[i].get("bloque", "N/A") 
            
            # Quitamos los emojis para máxima compatibilidad con cualquier cliente IA
            respuesta += f"FUENTE: {fuente} (Bloque: {pagina})\n"
            respuesta += f"CONTEXTO:\n{texto_limpio}\n"
            respuesta += "-" * 60 + "\n"
            
        return respuesta
        
    except Exception as e:
        return f"Error interno al consultar la base de datos vectorial: {str(e)}"

if __name__ == "__main__":
    # 3. Ejecutar el servidor
    print("Servidor RAG MCP iniciado. Conectado a la base de vectores.", file=sys.stderr)
    
    # Soporte dual: Si escribes --web arranca para internet, si no, arranca local
    if "--web" in sys.argv:
        print("Iniciando en Modo Web (HTTP/SSE) en el puerto 8000...", file=sys.stderr)
        mcp.run(transport='sse')
    else:
        mcp.run()