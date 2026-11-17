import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';

const MCP_URL = process.env.MCP_REMOTE_URL || "http://localhost:8000/sse";

async function main() {
    const sseTransport = new SSEClientTransport(new URL(MCP_URL));
    await sseTransport.start();

    sseTransport.onmessage = (message) => {
        console.log(JSON.stringify(message));
    };

    let buffer = '';
    process.stdin.on('data', (chunk) => {
        buffer += chunk.toString();
        let newlineIndex;
        while ((newlineIndex = buffer.indexOf('\n')) !== -1) {
            const line = buffer.slice(0, newlineIndex);
            buffer = buffer.slice(newlineIndex + 1);
            if (line.trim()) {
                try {
                    const message = JSON.parse(line);
                    sseTransport.send(message);
                } catch (e) {
                    console.error("Invalid JSON from IDE", e);
                }
            }
        }
    });
}

main().catch(err => {
    console.error(err);
    process.exit(1);
});
