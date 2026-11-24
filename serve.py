"""PLE agent with an explicit deliverable contract and bounded repair loop."""
import asyncio
import json
import os
import shlex
from pathlib import Path

import httpx
import taskbridge

CHECKER = Path(__file__).with_name("inspect_output.py").read_text()
SYSTEM = """Solve the engineering assignment inside its isolated project workspace.
Inventory the supplied files and application tools. Register the required output
paths with declare before writing. For an app-only or text-only task declare an
empty list and explain the destination. Distinguish inputs from deliverables.
Ground each design input in a page, sheet, cell or drawing revision. Carry units
and sign conventions through calculations. For geometry inspect placements,
clearances and connectivity; a valid IFC envelope alone is insufficient. For
spreadsheets reopen key cells, check units, formula references and totals.
Write a usable first version early. Independently recompute a governing value or
check an invariant and compare with the actual delivered file. When the task
requires an application, use its tools and read back the saved record. Inspect
only task inputs and your own outputs. Never seek grader or reference solutions.
Use finish to report paths, checked quantities and unresolved assumptions."""
TEXT = {"type": "string"}
PATHS = {"type": "array", "items": TEXT, "maxItems": 40}


def tool(tool_name, description, **fields):
    return {"type": "function", "function": {"name": tool_name, "description": description,
            "parameters": {"type": "object", "properties": fields,
                           "required": list(fields), "additionalProperties": False}}}


TOOLS = [
    tool("declare", "Set all required filesystem deliverables. Explain any app-only outputs.", paths=PATHS, destination=TEXT),
    tool("bash", "Execute a command in the isolated task project. Use Python for binary files.", command=TEXT),
    tool("write", "Write UTF-8 text to the task workspace.", path=TEXT, content=TEXT),
    tool("discover", "Search the task app tool names and schemas by keyword. Empty lists the first matches.", query=TEXT),
    tool("app", "Invoke a discovered app tool using its qualified name and JSON-encoded arguments.", name=TEXT, arguments_json=TEXT),
    tool("finish", "Reopen all declared files and submit the engineering summary.", summary=TEXT),
]


def bounded(text, limit=14000):
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n[excerpt shortened]\n" + text[-half:]


class Project:
    def __init__(self, session):
        self.session = session
        self.paths = None
        self.apps = {}
        self.finished = False
        self.repairs = 0
        self.summary = ""
        self.app_status = []

    async def connect(self):
        for spec in self.session.mcp_servers:
            client = taskbridge.MCPClient(self.session, spec["url"])
            try:
                await client.initialize()
                for item in await client.list_tools():
                    key = spec["name"] + "/" + item["name"]
                    self.apps[key] = (client, item)
            except (taskbridge.TaskError, taskbridge.MCPError, ValueError) as exc:
                self.app_status.append(f"{spec['name']} unavailable: {str(exc)[:180]}")

    async def act(self, name, args):
        if name == "declare":
            paths = args["paths"]
            if not isinstance(paths, list) or len(paths) > 40 or any(
                    not isinstance(p, str) or not p.strip() or "\0" in p for p in paths):
                raise ValueError("expected a list of up to 40 explicit paths")
            if not paths and not args["destination"].strip():
                raise ValueError("describe the app record or text response to deliver")
            self.paths = list(dict.fromkeys(paths))
            return "Registered " + json.dumps(self.paths) + " destination: " + args["destination"]
        if name == "bash":
            result = await self.session.exec(args["command"], timeout_sec=300)
            return bounded(json.dumps(result, ensure_ascii=False))
        if name == "write":
            size = await self.session.write_file(args["path"], args["content"])
            return f"Wrote {size} bytes"
        if name == "discover":
            words = args["query"].lower().split()
            matches = []
            for key, (_, item) in self.apps.items():
                if all(w in (key + " " + item["description"]).lower() for w in words):
                    matches.append({"name": key, "schema": item["inputSchema"]})
            return bounded(json.dumps({"total": len(matches), "matches": matches[:15]}))
        if name == "app":
            client, item = self.apps[args["name"]]
            payload = json.loads(args["arguments_json"])
            if not isinstance(payload, dict):
                raise ValueError("expected an object for the app arguments")
            return bounded(json.dumps(await client.call_tool(item["name"], payload)))
        if name != "finish":
            raise ValueError(f"unknown tool {name}")
        summary = args["summary"].strip()
        if not summary:
            raise ValueError("provide the deliverable summary")
        if self.paths is None:
            return "Declare the intended outputs before finishing."
        if self.paths and os.getenv("PLE_CHECK_OUTPUTS", "1") != "0":
            command = shlex.join(["python3", "-c", CHECKER, *self.paths])
            result = await self.session.exec(command, timeout_sec=90)
            report = bounded(str(result.get("output") or result.get("error") or ""), 4000)
            if result.get("exit_code") != 0:
                self.repairs += 1
                if self.repairs <= 2:
                    return "Delivery check failed. Repair the listed files and try again.\n" + report
                summary += "\nUnresolved delivery checks:\n" + report
        self.finished = True
        self.summary = summary
        return summary


def trim_history(messages):
    # Preserve tool-call adjacency, task instructions and recent observations.
    total = sum(len(json.dumps(m)) for m in messages)
    if total > 150000:
        for m in messages[2:-10]:
            if m["role"] == "tool" and len(m["content"]) > 600:
                total -= len(m["content"]) - 600
                m["content"] = bounded(m["content"], 560)
                if total <= 100000:
                    break


def compact_request(messages):
    """Reduce a long request while preserving complete tool-call exchanges."""
    for message in messages[2:]:
        if message["role"] == "tool":
            message["content"] = bounded(message["content"], 1200)
    while len(json.dumps(messages, ensure_ascii=False)) > 16000:
        first_group = next((i for i in range(3, len(messages))
                            if messages[i]["role"] in ("user", "assistant")), None)
        if first_group is None:
            break
        del messages[2:first_group]


def json_action_request(messages, model):
    catalog = [item["function"] for item in TOOLS]
    transcript = []
    for item in messages:
        role, content = item["role"], item.get("content") or ""
        if role == "system":
            content += ("\nChoose one available action per turn. Reply with a single JSON object "
                        "having name (string) and arguments (object). Use exact property names. "
                        "Encode multiline commands as valid JSON strings. Actions: " + json.dumps(catalog))
        elif role == "tool":
            role, content = "user", "Tool result: " + content
        elif item.get("tool_calls"):
            content = json.dumps([call["function"] for call in item["tool_calls"]])
        transcript.append({"role": role, "content": content})
    return {"model": model, "messages": transcript, "response_format": {"type": "json_object"}}


def decode_json_action(response):
    message = response["choices"][0]["message"]
    action = json.loads(message["content"])
    if not isinstance(action, dict) or action.get("name") not in {item["function"]["name"] for item in TOOLS}:
        raise ValueError("unknown action")
    if not isinstance(action.get("arguments"), dict):
        raise ValueError("expected an arguments object")
    message["content"] = None
    message["tool_calls"] = [{"id": "call_" + os.urandom(8).hex(), "type": "function",
                               "function": {"name": action["name"], "arguments": json.dumps(action["arguments"])}}]


async def completion(client, messages, model, mode):
    body = {"model": model, "messages": messages, "tools": TOOLS, "tool_choice": "auto"}
    for attempt in range(6):
        if mode["json_actions"]:
            body = json_action_request(messages, model)
        delay = 2 ** attempt
        try:
            response = await client.post("chat/completions", json=body)
            if response.is_success:
                result = response.json()
                if mode["json_actions"]:
                    try:
                        decode_json_action(result)
                    except (TypeError, KeyError, ValueError) as error:
                        if attempt == 5:
                            raise ValueError("Model did not provide a valid JSON action") from error
                        messages.append({"role": "user", "content": "Return one JSON object with a valid action name and arguments object."})
                        continue
                return result
            try:
                error = response.json().get("error") or {}
            except ValueError:
                error = {}
            detail = str(error.get("message") or "")
            failure = (str(error.get("code") or "") + " " + detail).lower()
            if response.status_code == 413 or "request too large" in failure:
                compact_request(messages)
                body["max_completion_tokens"] = 1536
            elif response.status_code == 400 and any(reason in failure for reason in
                    ("tool_use_failed", "failed to call a function", "failed to call tool", "tool call validation",
                     "failed to parse tool call arguments")):
                # Reissue the turn as a JSON action and retain that mode for this task.
                mode["json_actions"] = True
                if messages[-1].get("content") != "Call one available tool using its exact argument schema.":
                    messages.append({"role": "user", "content": "Call one available tool using its exact argument schema."})
            elif response.status_code == 429:
                raw_delay = response.headers.get("retry-after", "")
                try:
                    delay = max(delay, min(180, float(raw_delay)))
                except ValueError:
                    delay = max(delay, 15)
            elif response.status_code not in (408, 500, 502, 503, 504):
                raise RuntimeError(f"Model HTTP {response.status_code}: {failure[:850]}")
            if attempt == 5:
                raise RuntimeError(f"Model HTTP {response.status_code} after retries: {failure[:850]}")
        except httpx.TransportError:
            if attempt == 5:
                raise
        await asyncio.sleep(delay)


async def solve(session):
    project = Project(session)
    await project.connect()
    model = os.environ["MODEL_NAME"]
    endpoint = os.environ["MODEL_BASE_URL"].rstrip("/") + "/"
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": session.instruction + "\nWorkspace: " +
                 session.workdir + f"\nAvailable app tools: {len(project.apps)}. " + " ".join(project.app_status)}]
    headers = {"Authorization": "Bearer " + os.environ["MODEL_API_KEY"]}
    calls = max(2, int(os.getenv("PLE_MAX_CALLS", "80")))
    last = ""
    mode = {"json_actions": False}
    async with httpx.AsyncClient(base_url=endpoint, headers=headers, timeout=300) as client:
        for turn in range(calls):
            left = session.time_left()
            if left is not None and left < 3:
                break
            if turn == calls - 2:
                messages.append({"role": "user", "content": "Two calls remain. Close out the deliverables now."})
            trim_history(messages)
            try:
                async with asyncio.timeout(min(left - 1, 600) if left is not None else 600):
                    response = await completion(client, messages, model, mode)
            except TimeoutError:
                break
            usage = response.get("usage") or {}
            await session.usage(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                                (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
            msg = response["choices"][0]["message"]
            # Only replay fields accepted as assistant input by the Chat Completions API.
            messages.append({key: msg[key] for key in ("role", "content", "tool_calls")
                             if msg.get(key) is not None})
            if msg.get("content"):
                last = msg["content"]
            calls_out = msg.get("tool_calls") or []
            if not calls_out:
                messages.append({"role": "user", "content": "Use declare and then finish to check and deliver your work."})
            for call in calls_out:
                try:
                    fn = call["function"]
                    result = await project.act(fn["name"], json.loads(fn["arguments"]))
                except (KeyError, TypeError, ValueError, AttributeError, taskbridge.TaskError, taskbridge.MCPError) as err:
                    result = f"Tool error: {str(err)[:500]}"
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                if project.finished:
                    return project.summary
    return "Stopped at the resource limit before final verification. Declared paths: " + json.dumps(project.paths) + "\n" + last


if __name__ == "__main__":
    taskbridge.run(solve)
