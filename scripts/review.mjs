import { spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
process.chdir(root);
const dataRoot = resolve(process.env.AMNESIA_DATA_DIR || resolve(root, '.amnesia'));
async function health(port) { try { const r = await fetch(`http://127.0.0.1:${port}/api/health`, { signal: AbortSignal.timeout(500) }); return await r.json(); } catch { return null; } }
function open(url) { console.log(`\nOpen your review: ${url}\n`); if (process.platform === 'darwin' && !process.argv.includes('--no-open')) spawn('open', [url], { stdio: 'ignore' }); }
let existingPort;
for (let port = 8787; port < 8817; port++) { const existing = await health(port); if (existing?.app === 'amnesia' && existing.project_root === root && existing.data_root === dataRoot) { existingPort = port; break; } }
if (!existsSync(resolve(root, 'dist/index.html'))) { console.log('Build the app first: npm install && npm run build'); process.exit(1); }
let config = { provider: 'codex', ollama_url: 'http://127.0.0.1:11435' };
const file = resolve(dataRoot, 'engine.json');
if (existsSync(file)) config = { ...config, ...JSON.parse(readFileSync(file, 'utf8')) };
if (process.env.AMNESIA_PROVIDER) config.provider = process.env.AMNESIA_PROVIDER;
if (process.env.AMNESIA_OLLAMA_URL) config.ollama_url = process.env.AMNESIA_OLLAMA_URL;
const owned = [];
if (['codex', 'ollama'].includes(config.provider) && config.ollama_url === 'http://127.0.0.1:11435') {
  try { await fetch(`${config.ollama_url}/api/tags`, { signal: AbortSignal.timeout(1000) }); }
  catch {
    const model = spawn('ollama', ['serve'], { env: { ...process.env, OLLAMA_HOST: '127.0.0.1:11435', OLLAMA_NO_CLOUD: '1', OLLAMA_NOPRUNE: '1' }, stdio: 'ignore', detached: Boolean(existingPort) });
    model.on('error', () => console.log('Ollama is not installed. Select OpenAI in AI engine or install Ollama.'));
    owned.push(model);
    let ready = false;
    for (let attempt = 0; attempt < 30; attempt++) {
      try { const response = await fetch(`${config.ollama_url}/api/tags`, { signal: AbortSignal.timeout(500) }); if (response.ok) { ready = true; break; } } catch { /* Service may still be starting. */ }
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    if (!ready) console.log('Local embeddings did not start. Open AI engine for connection details.');
  }
}
if (existingPort) { for (const child of owned) child.unref(); open(`http://127.0.0.1:${existingPort}/#review`); process.exit(0); }
const server = spawn('python3', ['-m', 'backend.server', '--production'], { cwd: root, env: process.env, stdio: ['inherit', 'pipe', 'inherit'] });
owned.push(server);
let opened = false;
server.stdout.on('data', chunk => { process.stdout.write(chunk); const match = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/); if (match && !opened) { opened = true; open(match[0] + '/#review'); } });
server.on('error', error => { console.error('Python 3 is required:', error.message); process.exitCode = 1; });
function stop() { for (const process of owned) process.kill('SIGTERM'); }
process.on('SIGINT', stop); process.on('SIGTERM', stop);
server.on('exit', code => { for (const process of owned) if (process !== server) process.kill('SIGTERM'); process.exitCode = code || 0; });
