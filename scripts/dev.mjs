import { spawn } from "node:child_process";
import net from "node:net";
async function available(start) {
  for (let port = start; port < start + 30; port++) {
    const free = await new Promise((resolve) => {
      const s = net.createServer();
      s.once("error", () => resolve(false));
      s.listen(port, "127.0.0.1", () => s.close(() => resolve(true)));
    });
    if (free) return port;
  }
  throw new Error("No available local port.");
}
const apiPort = await available(Number(process.env.AMNESIA_API_PORT || 8787));
const webPort = await available(Number(process.env.AMNESIA_WEB_PORT || 5173));
const env = {
  ...process.env,
  AMNESIA_API_PORT: String(apiPort),
  AMNESIA_WEB_PORT: String(webPort),
};
const processes = [
  spawn("python3", ["-m", "backend.server", "--port", String(apiPort)], {
    stdio: "inherit",
    env,
  }),
  spawn("npx", ["vite", "--host", "127.0.0.1", "--port", String(webPort)], {
    stdio: "inherit",
    env,
  }),
];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const p of processes) p.kill("SIGTERM");
  process.exitCode = code;
}
for (const p of processes) {
  p.on("error", () => stop(1));
  p.on("exit", (code) => {
    if (!stopping) stop(code ?? 1);
  });
}
process.on("SIGINT", () => stop());
process.on("SIGTERM", () => stop());
