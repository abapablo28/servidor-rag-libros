# Servidor RAG SAP (Model Context Protocol) 🚀

Servidor **MCP (Model Context Protocol)** y motor RAG de alta precisión especializado en el ecosistema **SAP** (Desarrollo ABAP, S/4HANA, CDS, RAP, Fiori/UI5 y Consultoría Funcional FI, MM, SD, EWM, BTP, HCM, BW).

Permite a clientes de IA como **Antigravity**, **Claude Desktop**, **Claude Web** y **ChatGPT** consultar directamente más de 180 libros oficiales de **SAP Press** y manuales de **Academia SAP**.

---

## ⚡ Características Principales

* **Búsqueda Híbrida Bilingüe (BM25 + Dense Vectors + RRF):**
  * **Léxica:** Búsqueda exacta vía SQLite FTS5 (BM25) para transacciones (`MIGO`, `VA01`, `SE80`, `ATC`), tablas (`ACDOCA`, `BSEG`, `BKPF`) y sentencias ABAP (`FOR ALL ENTRIES`, `DEFINE VIEW ENTITY`).
  * **Semántica:** Vectores densos de 384 dimensiones calculados con **ONNX Runtime nativo (`all-MiniLM-L6-v2`)**, reduciendo el arranque a la mitad y ahorrando ~600 MB de RAM respecto a PyTorch estándar.
  * **Puente Español ↔ Inglés:** Cruza automáticamente manuales de Academia (español) y libros de SAP Press (inglés).
* **Reconstrucción Automática de Bloques Vecinos:**
  * Reúne bloques consecutivos en una sola consulta SQL para entregar ejemplos de código ABAP o explicaciones funcionales completas y sin cortes.
* **Multitransporte Universal:**
  * **stdio:** Conexión local para Antigravity y Claude Desktop.
  * **Streamable HTTP (`/mcp`):** Estándar moderno para Claude Web y ChatGPT MCP Connectors.
  * **SSE (`/sse`, `/messages/`):** Compatibilidad con clientes basados en Server-Sent Events.
  * **REST OpenAPI (`/api/consultar`, `/openapi.json`):** Compatible con ChatGPT Custom GPT Actions.
* **100% Modo Offline:**
  * Bloqueo de peticiones externas o telemetría para evitar cuellos de botella por proxies corporativos o timeouts de red.

---

## 🛠️ Herramientas MCP Disponibles

1. `consultar_conocimiento(pregunta, cantidad_resultados=4, query_en=None, modulo=None)`:
   * Búsqueda general híbrida en la biblioteca con contexto expandido.
2. `consultar_abap_tecnico(requerimiento_abap, keywords_ingles=None, enfoque='ABAP')`:
   * Especializada en Clean ABAP, OO, CDS, RAP, AMDP, BAdIs, optimización SQL para HANA y migración S/4HANA (une 5 bloques continuos por resultado).
3. `consultar_proceso_funcional(consulta_funcional, modulo_sap, keywords_ingles=None)`:
   * Especializada en parametrización (SPRO), transacciones y flujos estándar (`FI`, `MM`, `SD`, `EWM`, `BTP`, `HR`, `BW`).
4. `leer_paginas_libro(fuente, bloque_inicio, bloque_fin)`:
   * Permite a la IA "pasar la página" y leer rangos específicos de un manual cuando una explicación o código continúa.
5. `listar_libros_sap(categoria_o_filtro=None)`:
   * Lista el catálogo depurado de manuales disponibles en caché instantánea (<2 ms).
6. `consultar_nota_sap(numero_o_tema, contexto_adicional=None)`:
   * Resuelve y contextualiza Notas SAP y Simplification Items citados en los libros de SAP Press/Academia, detecta objetos Clean Core afectados y genera el enlace oficial directo al Launchpad `https://me.sap.com/notes/<numero>`.
7. `consultar_clean_core_sucesores(objetos_o_busqueda, nivel_filtro=None, tipo_objeto=None, cruzar_con_libros=True)`:
   * Motor integrado del **SAP Cloudification Repository** (~68,694 objetos oficiales para S/4HANA Private/Public Cloud, BTP ABAP Environment y Classic APIs, estilo ROSA). Audita el nivel Clean Core (`Level A`, `Level B`, `Level C`, `Level D`), indica qué vista CDS o API liberada reemplaza a tablas/BAPIs clásicas (`MARA` → `I_PRODUCT`, `BSEG` → `I_OPERATIONALACCTGDOCITEM`, `KNA1` → `I_CUSTOMER`) y lo cruza con tus libros.
8. `consultar_sap_help_oficial_web(consulta, incluir_comunidad=True, max_resultados=5)`:
   * Consulta en vivo URLs, secciones y fragmentos autorizados de **SAP Help Portal** (`help.sap.com`) y **SAP Community** (`community.sap.com`) para complementar la biblioteca con documentación oficial en línea.

---

## 🚀 Instalación y Puesta en Marcha

### 1. Clonar el repositorio
```bash
git clone https://github.com/abapablo28/servidor-rag-libros.git
cd servidor-rag-libros
```

### 2. Crear entorno virtual e instalar dependencias
```bash
python -m venv .venv
# En Windows:
.\.venv\Scripts\activate
# En Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

> **Nota:** La primera vez que se ejecute, el sistema descargará e inicializará automáticamente la base vectorial indexada si no existe localmente.

---

## 🔌 Configuración en Clientes

### Antigravity / Claude Desktop (Modo Local `stdio` con `uv`)
Añade lo siguiente en tu archivo de configuración de MCP (`mcp_config.json` o `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "sap-libros": {
      "command": "uv",
      "args": [
        "run",
        "--quiet",
        "--no-sync",
        "--directory",
        "C:/ruta/hacia/servidor-rag-libros",
        "server.py"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

### Modo Servidor Web (Docker / Remoto)
```bash
python server.py --web
```
O con Docker:
```bash
docker build -t servidor-rag-sap .
docker run -p 8000:8000 servidor-rag-sap
```

Endpoints disponibles:
* **Streamable HTTP MCP:** `http://localhost:8000/mcp`
* **SSE MCP:** `http://localhost:8000/sse`
* **OpenAPI REST (ChatGPT Actions):** `http://localhost:8000/openapi.json`
* **Healthcheck:** `http://localhost:8000/health`

---

## 📚 Ingesta de Nuevos Libros

Para agregar nuevos manuales en PDF:
1. Copia los archivos `.pdf` a la carpeta `pdfs/`.
2. Ejecuta:
```bash
python ingerir.py
```
El script detectará automáticamente los libros nuevos (omitiendo los ya existentes por hash MD5), los dividirá respetando saltos de párrafo y bloques de código, y actualizará la base vectorial.

---

## 📄 Licencia
Distribuido bajo licencia MIT. Ver archivo `LICENSE` para más detalles.
