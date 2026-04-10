import click

def _indent_desc(text: str, indent: str = "    ") -> None:
    """Print each non-empty line of a description, indented."""
    for line in (text or "").splitlines():
        click.echo(indent + click.style(line, dim=True))

def _print_item(label: str, desc: str) -> None:
    click.echo("  " + click.style(label, fg="yellow"))
    if desc and desc.strip():
        _indent_desc(desc.strip())

def print_capabilities(caps: dict) -> None:
    resources = caps.get("resources", [])
    templates = caps.get("templates", [])
    tools = caps.get("tools", [])
    prompts = caps.get("prompts", [])

    # Resources
    click.echo(click.style("[RESOURCES]", fg="cyan", bold=True))
    if resources:
        for r in resources:
            _print_item(str(getattr(r, "uri", r)), getattr(r, "description", "") or "")
    else:
        click.echo(click.style("  (none)", dim=True))
    click.echo()

    # Resource templates
    click.echo(click.style("[RESOURCE TEMPLATES]", fg="cyan", bold=True))
    if templates:
        for t in templates:
            uri = getattr(t, "uriTemplate", None) or getattr(t, "uri", str(t))
            desc = getattr(t, "description", "") or ""
            _print_item(str(uri), desc)
    else:
        click.echo(click.style("  (none)", dim=True))
    click.echo()

    # Tools
    click.echo(click.style("[TOOLS]", fg="cyan", bold=True))
    if tools:
        for tool in tools:
            name = getattr(tool, "name", str(tool))
            desc = getattr(tool, "description", "") or ""
            params = []
            schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
            if schema and isinstance(schema, dict):
                required = set(schema.get("required", []))
                for p in schema.get("properties", {}):
                    params.append(click.style(p, bold=True) if p in required else f"[{p}]")
            sig = click.style(name, fg="yellow") + "(" + ", ".join(params) + ")"
            click.echo("  " + sig)
            if desc and desc.strip():
                _indent_desc(desc.strip())
    else:
        click.echo(click.style("  (none)", dim=True))
    click.echo()

    # Prompts
    click.echo(click.style("[PROMPTS]", fg="cyan", bold=True))
    if prompts:
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
            click.echo("  " + sig)
            if desc and desc.strip():
                _indent_desc(desc.strip())
    else:
        click.echo(click.style("  (none)", dim=True))

def print_prompt(messages: list) -> None:
    for msg in messages:
        role = getattr(msg, "role", "?")
        content = getattr(msg, "content", None)
        text = getattr(content, "text", str(content)) if content else ""
        role_str = click.style(f"[{role}]", fg="magenta", bold=True)
        click.echo(f"{role_str} {text}")

def print_result(text: str) -> None:
    click.echo(text, nl=False)
    if text and not text.endswith("\n"):
        click.echo()

def print_error(msg: str) -> None:
    click.echo(click.style(f"ERROR: {msg}", fg="red"), err=True)
