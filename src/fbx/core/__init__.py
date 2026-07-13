"""Core Freebox logic. Knows nothing about Typer, Rich, or MCP.

Everything in this package is a pure library: it talks to the box and returns
data or raises typed errors. The CLI and MCP server are thin adapters over it.
"""
