import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';

const MCP_URL = process.env.MCP_REMOTE_URL || "http://localhost:8000/sse";

async function main() {
    console.log(`Connecting to ${MCP_URL}...`);
    const transport = new SSEClientTransport(new URL(MCP_URL));
    const client = new Client({ name: "test", version: "1.0" }, { capabilities: {} });
    
    try {
        await client.connect(transport);
        console.log("Connected successfully!");
        
        const tools = await client.listTools();
        console.log("Tools available:", tools.tools.map(t => t.name));
    } catch (e) {
        console.error("Error connecting:", e);
    }
}

main().catch(console.error);
