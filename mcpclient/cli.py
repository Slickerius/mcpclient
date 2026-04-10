import asyncio
import json
import sys

import click

from mcpclient.client import MCPClient
from mcpclient.formatter import (
    print_capabilities,
    print_error,
    print_prompt,
    print_result,
)

LOG_LEVELS = ["debug", "info", "warning", "error", "critical"]

def _run(coro):
    """Run an async coroutine, print error and exit on failure."""
    try:
        asyncio.run(coro)
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)

def _parse_auth(user: str | None, password: str | None) -> tuple[str, str] | None:
    if not user and not password:
        return None
    if user and not password:
        raise click.BadParameter("-u/--user requires -p/--password")
    if password and not user:
        raise click.BadParameter("-p/--password requires -u/--user")
    return (user, password)

def _parse_headers(headers: tuple) -> dict[str, str] | None:
    if not headers:
        return None
    out = {}
    for h in headers:
        if ":" not in h:
            raise click.BadParameter(f"header must be Name:Value, got: {h}")
        k, v = h.split(":", 1)
        out[k.strip()] = v.strip()
    return out

def _client(target, user, password, header, command, sse) -> MCPClient:
    if command:
        if user or password:
            raise click.UsageError("-c/--command cannot be used with -u/--user or -p/--password")
        if header:
            raise click.UsageError("-c/--command cannot be used with -H/--header")
        if sse:
            raise click.UsageError("--sse cannot be used with -c/--command")
        return MCPClient(command=command, transport="stdio")
    if not target:
        raise click.UsageError("Either -t/--target or -c/--command is required")
    transport = "sse" if sse else "http"
    return MCPClient(
        target=target,
        headers=_parse_headers(header),
        auth=_parse_auth(user, password),
        transport=transport,
    )

def _common(fn):
    """Add shared connection options to a command."""
    fn = click.option("-t", "--target", default=None, help="MCP server URL (HTTP/SSE)")(fn)
    fn = click.option("-u", "--user", default=None, help="HTTP Basic Auth username")(fn)
    fn = click.option("-p", "--password", default=None, help="HTTP Basic Auth password")(fn)
    fn = click.option("-H", "--header", multiple=True, help="Extra HTTP header as Name:Value (repeatable)")(fn)
    fn = click.option("-c", "--command", "command", default=None, help="Stdio command to spawn (e.g. \"python server.py\")")(fn)
    fn = click.option("--sse", is_flag=True, default=False, help="Force SSE transport instead of Streamable HTTP")(fn)
    return fn

# CLI root
@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """mcpclient - MCP (Model Context Protocol) execution tool"""

# List
@cli.command("list")
@_common
def cmd_list(target: str | None, user: str | None, password: str | None, header: tuple, command: str | None, sse: bool) -> None:
    """List all capabilities exposed by the server.

    \b
    Example:
      mcpclient list -t http://localhost:8000/mcp/
      mcpclient list -t http://localhost:8000/mcp/ -u user -p pass
      mcpclient list -t http://localhost:8000/events --sse
      mcpclient list -c "python server.py"
    """
    async def _go():
        caps = await _client(target, user, password, header, command, sse).list_capabilities()
        print_capabilities(caps)
    _run(_go())

# Read
@cli.command("read")
@_common
@click.option("-r", "--resource", required=True, help="Resource URI (URL-encode spaces as %%20)")
def cmd_read(target: str | None, user: str | None, password: str | None, header: tuple, command: str | None, sse: bool, resource: str) -> None:
    """Read a resource by URI.

    \b
    Examples:
      mcpclient read -t http://localhost:8000/mcp/ -r resource://logs
      mcpclient read -c "python server.py" -r resource://logs
    """
    async def _go():
        text = await _client(target, user, password, header, command, sse).read(resource)
        print_result(text)
    _run(_go())

# Call
@cli.command("call")
@_common
@click.option("-f", "--function", required=True, help="Tool name")
@click.option("-d", "--data", default="{}", show_default=True, help="Tool arguments as JSON")
def cmd_call(target: str | None, user: str | None, password: str | None, header: tuple, command: str | None, sse: bool, function: str, data: str) -> None:
    """Call a tool with optional JSON arguments.

    \b
    Examples:
      mcpclient call -t http://localhost:8000/mcp/ -f list_users
      mcpclient call -c "npx -y @mcp/server /tmp" -f list_files
    """
    async def _go():
        try:
            args = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in --data: {exc}") from exc
        result = await _client(target, user, password, header, command, sse).call(function, args)
        print_result(result)
    _run(_go())

# Prompts
@cli.command("list-prompts")
@_common
def cmd_list_prompts(target: str | None, user: str | None, password: str | None, header: tuple, command: str | None, sse: bool) -> None:
    """List prompt templates exposed by the server.

    \b
    Example:
      mcpclient list-prompts -t http://localhost:8000/mcp/
      mcpclient list-prompts -c "python server.py"
    """
    async def _go():
        prompts = await _client(target, user, password, header, command, sse).list_prompts()
        if not prompts:
            click.echo(click.style("(no prompts)", dim=True))
            return
        for p in prompts:
            name = getattr(p, "name", str(p))
            desc = getattr(p, "description", "") or ""
            args = getattr(p, "arguments", []) or []
            arg_parts = []
            for a in args:
                aname = getattr(a, "name", str(a))
                req = getattr(a, "required", False)
                arg_parts.append(click.style(aname, bold=True) if req else f"[{aname}]")
            sig = click.style(name, fg="yellow") + "(" + ", ".join(arg_parts) + ")"
            click.echo(sig)
            if desc.strip():
                for line in desc.strip().splitlines():
                    click.echo("  " + click.style(line, dim=True))
    _run(_go())

@cli.command("get-prompt")
@_common
@click.option("-n", "--name", required=True, help="Prompt name")
@click.option("-d", "--data", default="{}", show_default=True, help="Prompt arguments as JSON")
def cmd_get_prompt(target: str | None, user: str | None, password: str | None, header: tuple, command: str | None, sse: bool, name: str, data: str) -> None:
    """Render a prompt template with the given arguments.

    \b
    Examples:
      mcpclient get-prompt -t http://localhost:8000/mcp/ -n summarize
      mcpclient get-prompt -c "python server.py" -n summarize -d '{"doc_id": "42"}'
    """
    async def _go():
        try:
            args = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in --data: {exc}") from exc
        messages = await _client(target, user, password, header, command, sse).get_prompt(name, args)
        print_prompt(messages)
    _run(_go())

# Roots
@cli.command("set-roots")
@_common
@click.option("-r", "--root", multiple=True, required=True, help="Root URI to advertise (repeatable)")
def cmd_set_roots(target: str | None, user: str | None, password: str | None, header: tuple, command: str | None, sse: bool, root: tuple) -> None:
    """Declare filesystem root URIs to the server.

    \b
    Example:
      mcpclient set-roots -t http://localhost:8000/mcp/ -r file:///home/user/project
      mcpclient set-roots -c "python server.py" -r file:///home/user/project
    """
    async def _go():
        await _client(target, user, password, header, command, sse).set_roots(list(root))
        for uri in root:
            click.echo(click.style(f"root set: {uri}", fg="green"))
    _run(_go())

# Logging
@cli.command("set-log-level")
@_common
@click.option("-l", "--level", required=True, type=click.Choice(LOG_LEVELS), help="Log level")
def cmd_set_log_level(target: str | None, user: str | None, password: str | None, header: tuple, command: str | None, sse: bool, level: str) -> None:
    """Ask the server to change its log verbosity level.

    \b
    Example:
      mcpclient set-log-level -t http://localhost:8000/mcp/ -l debug
      mcpclient set-log-level -c "python server.py" -l debug
    """
    async def _go():
        await _client(target, user, password, header, command, sse).set_log_level(level)
        click.echo(click.style(f"Log level set to {level}", fg="green"))
    _run(_go())
