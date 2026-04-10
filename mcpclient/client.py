import contextlib
import shlex

from fastmcp import Client
from fastmcp.client.transports import ClientTransport
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Root
import httpx

class _HttpTransport(ClientTransport):
    """Thin transport that uses the non-deprecated streamable_http_client."""

    def __init__(self, url: str, headers: dict[str, str] | None = None, auth: httpx.Auth | None = None):
        self.url = url
        self.headers = headers or {}
        self.auth = auth

    @contextlib.asynccontextmanager
    async def connect_session(self, **session_kwargs):
        http_client = httpx.AsyncClient(
            headers=self.headers,
            auth=self.auth,
            follow_redirects=True,
            timeout=httpx.Timeout(30, read=300),
        )
        async with http_client:
            async with streamable_http_client(self.url, http_client=http_client) as transport:
                read_stream, write_stream, _ = transport
                async with ClientSession(read_stream, write_stream, **session_kwargs) as session:
                    yield session

class _SseTransport(ClientTransport):
    """Transport that connects to an MCP server via Server-Sent Events."""

    def __init__(self, url: str, headers: dict[str, str] | None = None, auth: httpx.Auth | None = None):
        self.url = url
        self.headers = headers or {}
        self.auth = auth

    @contextlib.asynccontextmanager
    async def connect_session(self, **session_kwargs):
        async with sse_client(self.url, headers=self.headers, auth=self.auth) as transport:
            read_stream, write_stream = transport
            async with ClientSession(read_stream, write_stream, **session_kwargs) as session:
                yield session

class _StdioTransport(ClientTransport):
    """Transport that spawns a local MCP server and talks over stdin/stdout."""

    def __init__(self, command: str, args: list[str] | None = None):
        self.command = command
        self.args = args or []

    @contextlib.asynccontextmanager
    async def connect_session(self, **session_kwargs):
        params = StdioServerParameters(command=self.command, args=self.args)
        async with stdio_client(params) as transport:
            read_stream, write_stream = transport
            async with ClientSession(read_stream, write_stream, **session_kwargs) as session:
                yield session

class MCPClient:
    def __init__(
        self,
        target: str | None = None,
        headers: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        command: str | None = None,
        transport: str = "http",
    ):
        self.target = target
        self.headers = headers
        self.auth = auth
        self.command = command
        self.transport = transport

    def _client(self) -> Client:
        if self.transport == "stdio":
            parts = shlex.split(self.command)
            return Client(_StdioTransport(command=parts[0], args=parts[1:]))

        kwargs: dict = {"url": self.target}
        if self.headers:
            kwargs["headers"] = self.headers
        if self.auth:
            kwargs["auth"] = httpx.BasicAuth(self.auth[0], self.auth[1])

        if self.transport == "sse":
            return Client(_SseTransport(**kwargs))
        return Client(_HttpTransport(**kwargs))

    # Enumeration
    async def list_capabilities(self) -> dict:
        async with self._client() as c:
            resources = await c.list_resources()
            templates = await c.list_resource_templates()
            tools = await c.list_tools()
            prompts = await _try(c.list_prompts)
        return {
            "resources": resources,
            "templates": templates,
            "tools": tools,
            "prompts": prompts,
        }

    # Resources
    async def read(self, uri: str) -> str:
        async with self._client() as c:
            contents = await c.read_resource(uri)
        return "\n".join(getattr(item, "text", str(item)) for item in contents)

    # Tools
    async def call(self, name: str, args: dict) -> str:
        async with self._client() as c:
            result = await c.call_tool(name, args)
        if hasattr(result, "data"):
            return str(result.data)
        return "\n".join(
            getattr(item, "text", str(item)) for item in result.content
        )

    # Prompts
    async def list_prompts(self) -> list:
        async with self._client() as c:
            return await c.list_prompts() or []

    async def get_prompt(self, name: str, args: dict) -> list:
        async with self._client() as c:
            result = await c.get_prompt(name, args)
        return getattr(result, "messages", [])

    # Roots (client to server)
    async def set_roots(self, uris: list[str]) -> None:
        """Advertise a list of root URIs to the server."""
        roots = [Root(uri=uri) for uri in uris]
        client = self._client()
        client.set_roots(roots)
        async with client as c:
            await c.send_roots_list_changed()

    # Logging
    async def set_log_level(self, level: str) -> None:
        async with self._client() as c:
            await c.set_logging_level(level)

async def _try(coro_fn):
    try:
        return await coro_fn() or []
    except Exception:
        return []
