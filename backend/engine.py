"""Configured local/cloud AI, explicit diagnostics and reproducible call caching."""
import hashlib
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

DEFAULTS = {"provider": "codex", "chat_model": "gpt-5.6-sol", "embedding_model": "nomic-embed-text:latest", "ollama_url": "http://127.0.0.1:11435", "reconciliation": "policy", "temperature": None, "reasoning_effort": "low"}
MODEL_LOCK = threading.RLock()
TRACE = threading.local()


def consume_trace():
    calls = getattr(TRACE, "calls", [])
    TRACE.calls = []
    return calls


def trace(call):
    if not hasattr(TRACE, "calls"):
        TRACE.calls = []
    TRACE.calls.append(call)


def data_dir():
    return Path(os.environ.get("AMNESIA_DATA_DIR", Path(__file__).resolve().parent.parent / ".amnesia"))


def configuration():
    config = dict(DEFAULTS)
    file = data_dir() / "engine.json"
    if file.exists():
        config.update(json.loads(file.read_text()))
    overrides = {"AMNESIA_PROVIDER": "provider", "AMNESIA_MODEL": "chat_model", "AMNESIA_EMBEDDING_MODEL": "embedding_model", "AMNESIA_OLLAMA_URL": "ollama_url"}
    for env, field in overrides.items():
        if os.environ.get(env):
            config[field] = os.environ[env]
    config["temperature"] = None if config["provider"] == "codex" else 0
    return config


def save_configuration(update):
    allowed = {"provider", "chat_model", "embedding_model", "ollama_url", "reconciliation"}
    if not set(update).issubset(allowed):
        raise ValueError("Unknown engine setting.")
    config = dict(configuration(), **update)
    if config["provider"] not in ("codex", "ollama", "openai", "offline"):
        raise ValueError("Choose Codex login, local Ollama, OpenAI API, or offline rules.")
    config["temperature"] = None if config["provider"] == "codex" else 0
    if config["reconciliation"] != "policy":
        raise ValueError("Unknown reconciliation mode.")
    url = urlparse(config["ollama_url"])
    if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost") or url.username or url.password:
        raise ValueError("The local model endpoint must be a localhost HTTP URL.")
    for field in ("chat_model", "embedding_model"):
        if not isinstance(config[field], str) or len(config[field]) > 150:
            raise ValueError("Invalid model identifier.")
    if config["provider"] != "offline" and (not config["chat_model"] or not config["embedding_model"]):
        raise ValueError("Select a language model and an embedding model.")
    data_dir().mkdir(parents=True, exist_ok=True)
    temp = data_dir() / "engine.tmp"
    temp.write_text(json.dumps(config, indent=2))
    temp.replace(data_dir() / "engine.json")
    return config


def cloud_key():
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    file = data_dir() / "credentials.json"
    if file.exists():
        return json.loads(file.read_text()).get("openai_api_key")
    return None


def save_cloud_key(key):
    if not isinstance(key, str) or not 20 <= len(key.strip()) <= 500 or any(c.isspace() for c in key.strip()):
        raise ValueError("Enter a valid API key without whitespace.")
    directory = data_dir(); directory.mkdir(parents=True, exist_ok=True)
    file = directory / "credentials.json"
    fd = os.open(str(file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"openai_api_key": key.strip()}, stream)
    os.chmod(str(file), 0o600)
    return {"configured": True}


def request_json(url, body=None, headers=None, timeout=120):
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Error bodies from local models are safe diagnostics, never expose cloud credentials.
        detail = ""
        if urlparse(url).hostname in ("localhost", "127.0.0.1"):
            try:
                detail = ": " + str(json.loads(exc.read()).get("error", ""))[:200]
            except Exception:
                pass
        raise ValueError("Model service returned HTTP %s%s" % (exc.code, detail)) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError("The model service is unavailable or timed out. Open AI engine to check the connection.") from exc


def diagnostics(config=None):
    config = config or configuration()
    result = dict(config, ready=False, models=[], message="", external_enabled=config["provider"] in ("codex", "openai"))
    if config["provider"] == "offline":
        result.update(ready=True, message="Offline rules are selected. General natural-language AI is disabled.")
    elif config["provider"] == "openai":
        result.update(ready=bool(cloud_key()), key_configured=bool(cloud_key()), message="API key configured locally; test the engine to verify model access." if cloud_key() else "Add your OpenAI API key below to enable live inference.")
    else:
        try:
            tags = request_json(config["ollama_url"] + "/api/tags", timeout=3)
            models = tags.get("models", [])
            names = {m["name"] for m in models}
            available = lambda model: model in names or model + ":latest" in names
            required = (config["embedding_model"],) if config["provider"] == "codex" else (config["chat_model"], config["embedding_model"])
            missing = [m for m in required if not available(m)]
            result.update(models=[{"name": m["name"], "size": m.get("size", 0), "digest": m.get("digest")} for m in models], ready=not missing, message="Local AI is ready. No conversation data leaves this device." if not missing else "Install missing model(s): " + ", ".join(missing))
        except ValueError:
            result["message"] = "Local AI is stopped. Run npm run models:start, then check again."
        if config["provider"] == "codex":
            from .codex_provider import login_status
            status = login_status()
            result.update(codex_authenticated=status["codex_authenticated"], cli_version=status["cli_version"])
            result["ready"] = result["ready"] and status["codex_authenticated"]
            result["message"] = status["message"] + " " + ("Local embeddings are ready. Inference uses your Codex plan usage." if result["ready"] else result["message"] if status["codex_authenticated"] else "")
    return result


def _cache_get(cache_key):
    file = data_dir() / "model-cache.sqlite3"
    file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(file), timeout=60) as db:
        db.execute("CREATE TABLE IF NOT EXISTS calls(key TEXT PRIMARY KEY,response TEXT NOT NULL,created_at REAL NOT NULL)")
        row = db.execute("SELECT response FROM calls WHERE key=?", (cache_key,)).fetchone()
        return json.loads(row[0]) if row else None


def _cache_put(cache_key, result):
    with sqlite3.connect(str(data_dir() / "model-cache.sqlite3"), timeout=60) as db:
        db.execute("INSERT OR REPLACE INTO calls VALUES (?,?,?)", (cache_key, json.dumps(result), time.time()))


def structured(messages, schema, task, config=None, cache=False):
    started = time.perf_counter()
    config = config or configuration()
    if config["provider"] == "offline":
        raise ValueError("This action requires an AI model. Select Codex login, local Ollama, or OpenAI API in AI engine.")
    cache_key = hashlib.sha256(json.dumps({"v": 3, "provider": config["provider"], "model": config["chat_model"], "messages": messages, "schema": schema, "task": task}, sort_keys=True).encode()).hexdigest()
    if cache:
        previous = _cache_get(cache_key)
        if previous is not None:
            trace({"task": task, "cache_hit": True, "elapsed_ms": (time.perf_counter()-started)*1000, "model": config["chat_model"]})
            return previous
    if config["provider"] == "codex":
        from .codex_provider import run
        parsed, usage = run(messages, schema, task, config)
        content, result = json.dumps(parsed), {"usage": usage}
    elif config["provider"] == "ollama":
        with MODEL_LOCK:
            result = request_json(config["ollama_url"] + "/api/chat", {"model": config["chat_model"], "messages": messages, "format": schema, "think": False, "stream": False, "keep_alive": "30m", "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 1800 if task == "extraction" else 700, "seed": 42}})
        content = result.get("message", {}).get("content", "")
    else:
        api_key = cloud_key()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is missing on the server.")
        result = request_json("https://api.openai.com/v1/chat/completions", {"model": config["chat_model"], "messages": messages, "response_format": {"type": "json_schema", "json_schema": {"name": task, "schema": schema, "strict": True}}}, {"Authorization": "Bearer " + api_key})
        message = result.get("choices", [{}])[0].get("message", {})
        if message.get("refusal"):
            raise ValueError("The model declined this request.")
        content = message.get("content", "")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("The model returned incomplete structured data. Retry the request or choose another model.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("The model returned an invalid response.")
    if cache:
        _cache_put(cache_key, parsed)
    usage = result.get("usage", {})
    trace({"task": task, "cache_hit": False, "elapsed_ms": (time.perf_counter()-started)*1000, "model": config["chat_model"], "input_tokens": result.get("prompt_eval_count", usage.get("input_tokens", usage.get("prompt_tokens", 0))), "output_tokens": result.get("eval_count", usage.get("output_tokens", usage.get("completion_tokens", 0))), "cached_input_tokens": usage.get("cached_input_tokens", 0), "reasoning_output_tokens": usage.get("reasoning_output_tokens", 0)})
    return parsed


def embeddings(texts, config=None):
    config = config or configuration()
    if config["provider"] in ("codex", "ollama"):
        with MODEL_LOCK:
            result = request_json(config["ollama_url"] + "/api/embed", {"model": config["embedding_model"], "input": texts, "keep_alive": "30m", "truncate": False})
        return result["embeddings"]
    if config["provider"] == "openai":
        api_key = cloud_key()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is missing on the server.")
        result = request_json("https://api.openai.com/v1/embeddings", {"model": config["embedding_model"], "input": texts, "encoding_format": "float"}, {"Authorization": "Bearer " + api_key})
        return [item["embedding"] for item in sorted(result["data"], key=lambda item: item["index"])]
    raise ValueError("Dense embeddings require an AI provider.")
