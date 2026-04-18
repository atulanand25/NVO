"""
mcp_network_server.py
---------------------
MCP server that exposes simulated network operations as tools the LLM
can call. Uses the FastMCP decorator-based API from the official
Anthropic-published `mcp` Python SDK.

Run directly:
    python mcp_network_server.py

but in normal usage the MCP *client* (mcp_client.py) launches this file
as a subprocess and speaks to it over stdio.
"""

from __future__ import annotations

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

import network_data as nd


mcp = FastMCP("network-operations")


# --- helpers ---------------------------------------------------------------

def _ok(payload: dict) -> str:
    return json.dumps(payload, indent=2, default=str)


def _err(exc: Exception) -> str:
    return json.dumps({"error": str(exc), "error_type": type(exc).__name__}, indent=2)


# --- tools -----------------------------------------------------------------

@mcp.tool()
def list_devices() -> str:
    """List all network devices available in the managed topology.

    Returns a JSON array of device hostnames. Useful as a first step when
    the user does not specify a device.
    """
    return _ok({"devices": nd.list_devices()})


@mcp.tool()
def get_interfaces(device_name: str) -> str:
    """Get interface status for a network device.

    Returns each interface's name, description, IPv4 address, admin and
    operational status, speed, and error counters (input errors, output
    errors, CRC errors). Use this to spot physical or link-layer problems.

    Args:
        device_name: hostname of the device (e.g. 'core-rtr-01').
    """
    try:
        return _ok(nd.get_interfaces(device_name))
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_bgp_neighbors(device_name: str) -> str:
    """Get the BGP neighbor table for a device.

    Returns each peer's IP, local/remote ASN, session state (Established,
    Idle, Active, etc.), uptime, and prefixes sent/received. Any state
    other than 'Established' is a problem.

    Args:
        device_name: hostname of the device.
    """
    try:
        return _ok(nd.get_bgp_neighbors(device_name))
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_route_table(device_name: str, vrf: str = "default") -> str:
    """Get the IP routing table for a device (optionally a specific VRF).

    Returns destinations, next-hops, protocol source (connected, static,
    OSPF, BGP, etc.), metric, and administrative distance.

    Args:
        device_name: hostname of the device.
        vrf: VRF name. Defaults to 'default' (global routing table).
    """
    try:
        return _ok(nd.get_route_table(device_name, vrf))
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_device_health(device_name: str) -> str:
    """Get device-level health metrics: CPU utilization, memory utilization,
    uptime, OS version, and hardware model.

    Args:
        device_name: hostname of the device.
    """
    try:
        return _ok(nd.get_device_health(device_name))
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_logs(device_name: str, severity: Optional[str] = None) -> str:
    """Get recent syslog entries for a device, optionally filtered by severity.

    Args:
        device_name: hostname of the device.
        severity: one of 'emergency', 'alert', 'critical', 'error',
                  'warning', 'notice', 'info', 'debug'. Omit for all entries.
    """
    try:
        return _ok(nd.get_logs(device_name, severity))
    except Exception as e:
        return _err(e)


@mcp.tool()
def ping_device(source: str, destination: str, count: int = 5) -> str:
    """Simulate an ICMP echo (ping) from one device to another.

    Args:
        source: hostname of the originating device.
        destination: hostname OR IP of the target. If it does not resolve
                     to a device in the managed topology, the result is
                     reported as unreachable.
        count: number of echo requests. Informational only in this
               simulation.
    """
    try:
        return _ok(nd.ping_device(source, destination, count))
    except Exception as e:
        return _err(e)


if __name__ == "__main__":
    # stdio transport -> the client talks to us via our stdin/stdout.
    mcp.run(transport="stdio")
