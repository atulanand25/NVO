"""
mcp_client.py
-------------
Agentic network-operations client. Connects Claude to our MCP server
(mcp_network_server.py) and lets the model call tools in a multi-turn
loop until it produces a final natural-language answer.

Run:
    # single question
    python mcp_client.py "Which device has the highest CPU utilization?"

    # scripted test suite (all 5 required queries)
    python mcp_client.py --suite

    # interactive REPL
    python mcp_client.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax


# The 5 required queries from the assignment.
REQUIRED_QUERIES: list[str] = [
    "What is the status of all interfaces on core-rtr-01?",
    "Are there any BGP neighbors that are not in Established state?",
    "Can core-rtr-01 reach edge-fw-01? Check connectivity.",
    "Which device has the highest CPU utilization? Should I be concerned?",
    "Check the health of all devices and summarize any issues you find.",
]


SYSTEM_PROMPT = (
    "You are a senior network engineer assistant. You have access to tools "
    "that query live network state (interfaces, BGP, routes, health, logs, "
    "ping). Call tools to gather evidence before drawing conclusions. When "
    "the user does not name a device, use list_devices first. Cite concrete "
    "values from tool output (interface names, IPs, counters) in your "
    "answer. Keep answers concise and operator-friendly."
)


def _load_env_file() -> None:
    """Load ANTHROPIC_API_KEY from a sibling or parent .env if present."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return
    for p in [Path.cwd() / ".env", Path(__file__).parent / ".env",
              Path(__file__).parent.parent / ".env",
              Path(__file__).parent.parent.parent / ".env"]:
        if p.is_file():
            for line in p.read_text().splitlines():
                if line.strip().startswith("ANTHROPIC_API_KEY="):
                    os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()
                    return


class NetworkMCPAgent:
    """Glue between Claude (LLM) and our MCP server (tools)."""

    def __init__(self, model: str = "claude-sonnet-4-5", console: Console | None = None):
        self.anthropic = Anthropic()
        self.model = model
        self.console = console or Console()
        self.exit_stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.anthropic_tools: list[dict[str, Any]] = []

    async def connect(self, server_script: str) -> None:
        """Launch the MCP server as a subprocess and list its tools."""
        params = StdioServerParameters(
            command=sys.executable,
            args=[server_script],
            env=os.environ.copy(),
        )
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.stdio, self.write)
        )
        await self.session.initialize()

        tools_result = await self.session.list_tools()
        self.anthropic_tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema,
            }
            for t in tools_result.tools
        ]
        self.console.print(
            Panel.fit(
                f"Connected to MCP server. Tools discovered: "
                f"[bold]{', '.join(t['name'] for t in self.anthropic_tools)}[/bold]",
                title="MCP",
                border_style="green",
            )
        )

    async def close(self) -> None:
        await self.exit_stack.aclose()

    async def ask(self, user_query: str, max_steps: int = 10) -> dict[str, Any]:
        """Run the agentic tool-use loop. Returns a transcript dict."""
        assert self.session is not None

        self.console.rule(f"[bold cyan]QUERY[/bold cyan]: {user_query}")
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_query}]
        trace: list[dict[str, Any]] = []
        final_text = ""

        for step in range(max_steps):
            resp = self.anthropic.messages.create(
                model=self.model,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                tools=self.anthropic_tools,
                messages=messages,
            )

            # Append assistant turn to the conversation.
            messages.append({"role": "assistant", "content": resp.content})

            # Collect any tool_use blocks for this turn.
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            text_blocks = [b.text for b in resp.content if b.type == "text"]

            if text_blocks:
                for tb in text_blocks:
                    self.console.print(Panel(tb, title=f"Claude (step {step+1})", border_style="blue"))

            if resp.stop_reason != "tool_use" or not tool_uses:
                # Model is done.
                final_text = "\n".join(text_blocks).strip()
                break

            # Execute each tool call against the MCP server.
            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                self.console.print(
                    f"[yellow]→ tool_call[/yellow] [bold]{tu.name}[/bold]("
                    f"{json.dumps(tu.input)})"
                )
                mcp_result = await self.session.call_tool(tu.name, tu.input)
                # FastMCP returns a list of content blocks; we stringify.
                out_text = "".join(
                    c.text if hasattr(c, "text") else str(c) for c in mcp_result.content
                )
                trace.append({
                    "step": step + 1,
                    "tool": tu.name,
                    "arguments": tu.input,
                    "result": _maybe_json(out_text),
                })
                # Truncate the echo for readability.
                preview = out_text if len(out_text) < 1200 else out_text[:1200] + "\n... [truncated]"
                self.console.print(Syntax(preview, "json", theme="monokai", line_numbers=False))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": out_text,
                })

            messages.append({"role": "user", "content": tool_results})

        self.console.print(
            Panel(final_text or "(no final text)", title="FINAL ANSWER", border_style="green")
        )
        return {"query": user_query, "tool_trace": trace, "answer": final_text}


def _maybe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return text


async def _run(args: argparse.Namespace) -> None:
    _load_env_file()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set. See README.md.", file=sys.stderr)
        sys.exit(2)

    console = Console(record=args.save_html is not None)
    agent = NetworkMCPAgent(model=args.model, console=console)
    server_path = str(Path(__file__).parent / "mcp_network_server.py")

    transcripts: list[dict[str, Any]] = []
    try:
        await agent.connect(server_path)

        if args.suite:
            queries = REQUIRED_QUERIES
        elif args.query:
            queries = [args.query]
        else:
            console.print("Interactive mode. Ctrl-D to exit.", style="dim")
            while True:
                try:
                    q = console.input("[bold]you>[/bold] ")
                except EOFError:
                    break
                if not q.strip():
                    continue
                transcripts.append(await agent.ask(q))
            queries = []

        for q in queries:
            transcripts.append(await agent.ask(q))

    finally:
        await agent.close()

    if args.save_json:
        Path(args.save_json).write_text(json.dumps(transcripts, indent=2, default=str))
        console.print(f"[green]Saved transcripts -> {args.save_json}[/green]")
    if args.save_html:
        console.save_html(args.save_html)
        console.print(f"[green]Saved rich HTML transcript -> {args.save_html}[/green]")


def main() -> None:
    ap = argparse.ArgumentParser(description="Agentic MCP network client.")
    ap.add_argument("query", nargs="?", help="Single natural-language query.")
    ap.add_argument("--suite", action="store_true", help="Run the 5 required test queries.")
    ap.add_argument("--model", default="claude-sonnet-4-5",
                    help="Anthropic model id (default: claude-sonnet-4-5).")
    ap.add_argument("--save-json", help="Write machine-readable transcripts to this path.")
    ap.add_argument("--save-html", help="Write a colorized HTML transcript to this path.")
    args = ap.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
