import { createServer } from "node:http";

import { CONTRACT_VERSION } from "./state";

// The sync service owns ordering and fan-out. Port comes from the slot file.
export function startServer(port: number): { close: () => void } {
  const server = createServer((request, response) => {
    if (request.method === "GET" && request.url === "/health") {
      const body = JSON.stringify({ status: "ok", contract: CONTRACT_VERSION });
      response.writeHead(200, { "content-type": "application/json" });
      response.end(body);
      return;
    }
    response.writeHead(404, { "content-type": "application/json" });
    response.end(JSON.stringify({ error: "not_found" }));
  });
  server.listen(port);
  return { close: () => server.close() };
}

export const DEFAULT_PORT = 4101;
