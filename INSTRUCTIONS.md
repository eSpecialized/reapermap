# privrepomap — MCP Setup & Usage

Here's how to wire it up and try it in any of your repos.

---

## 1. Add the server to VS Code (side-by-side, doesn't touch your existing tool)

Create a workspace-scoped config in the repo you want to test against — `.vscode/mcp.json`:

```json
{
  "servers": {
    "privrepomap": {
      "type": "stdio",
      "command": "<pathToRepo>/reapermap/.venv/bin/privrepomap-mcp",
      "env": {
        "DO_NOT_TRACK": "1",
        "FASTMCP_DISABLE_TELEMETRY": "1",
        "ANONYMIZED_TELEMETRY": "False"
      }
    }
  }
}
```

This adds it under a distinct name (`privrepomap`), so your current RepoMapper tool keeps working untouched. To make it available in *every* workspace instead, put the same `servers` block in your user `mcp.json` (Command Palette → **MCP: Open User Configuration**).

---

## 2. Start it

- Open the Command Palette → **MCP: List Servers** → pick `privrepomap` → **Start Server**.
- Or just open the `.vscode/mcp.json` file; VS Code shows a **Start** code-lens above the server entry.
- Check **Output → MCP** logs if it doesn't connect. Errors go to stderr (stdout is the protocol channel), so a clean start = no output is normal.

---

## 3. Use it in chat (Agent mode)

Switch the chat to **Agent** mode, then reference the two tools. `project_root` must be an **absolute path**.

- **Repo map** — ask: *"Use the `repo_map` tool with project_root `/absolute/path/to/your/repo` and give me the structural overview."*
- **Identifier search** — ask: *"Use `search_identifiers` with project_root `/absolute/path/to/your/repo` and query `SomeFunctionName`."* (optionally pass chat_files or mentioned_idents for even better ranking).

**Tool signatures:**

```
repo_map(project_root, chat_files?, other_files?, token_limit=8192, mentioned_files?, mentioned_idents?, …)
  → { "map": str, "report": {…} }

search_identifiers(
  project_root, query,
  max_results=50, context_lines=2,
  chat_files?, other_files?, mentioned_files?, mentioned_idents?, …
)
  → { "results": [ {file, line, name, kind, context, rank}, ... ], "report": {...} }
```

The new optional context parameters on `search_identifiers` let you pass the same `chat_files` / `mentioned_idents` you already use with `repo_map`. This routes the search through the PageRank + boost machinery so primary definitions jump to the top (the main quality fix from the review).

---

## 4. Quick sanity check before chatting

Confirm the binary launches over stdio without VS Code:

```bash
<pathToRepo>/reapermap/.venv/bin/privrepomap-mcp
```

It will sit waiting on stdin (that's correct for a stdio MCP server) — `Ctrl-C` to exit.

---

> Everything stays offline — telemetry disabled, no network calls, output secret-redacted.
