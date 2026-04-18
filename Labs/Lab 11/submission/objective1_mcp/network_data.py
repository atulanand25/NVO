"""
network_data.py
----------------
Simulated network state for Lab 11, Objective 1 (MCP agentic network ops).

Three devices:
  * core-rtr-01  : healthy, but Gi0/3 has a physical-layer issue (up/down flapping,
                   high CRC/input errors) -> an anomaly the AI should surface.
  * dist-sw-01   : generally healthy, but its BGP peering to edge-fw-01 is stuck in
                   Idle state (authentication mismatch in the logs).
  * edge-fw-01   : CPU pegged at 94% with syslog warnings about a possible SYN flood
                   -> second anomaly. Memory is also elevated.

The structure mirrors what a real NOS (IOS-XE, Junos) would return if its
operational data were normalized to JSON. Each helper below is what the MCP
server calls into.
"""

from __future__ import annotations

from typing import Any


NETWORK_STATE: dict[str, dict[str, Any]] = {
    # ------------------------------------------------------------------
    # core-rtr-01 : ISR-4451 style core router. One flapping interface.
    # ------------------------------------------------------------------
    "core-rtr-01": {
        "health": {
            "cpu_percent": 18,
            "memory_percent": 42,
            "uptime": "87 days, 14:22:06",
            "os_version": "IOS-XE 17.9.4a",
            "hardware": "ISR4451-X/K9",
            "serial": "FOC24100ABC",
        },
        "interfaces": [
            {
                "name": "GigabitEthernet0/0/0",
                "description": "UPLINK to ISP-A",
                "ipv4": "203.0.113.2/30",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "input_errors": 0,
                "output_errors": 0,
                "crc_errors": 0,
            },
            {
                "name": "GigabitEthernet0/0/1",
                "description": "To dist-sw-01 Gi1/0/24",
                "ipv4": "10.10.0.1/30",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "input_errors": 12,
                "output_errors": 0,
                "crc_errors": 0,
            },
            {
                "name": "GigabitEthernet0/0/2",
                "description": "To edge-fw-01 Gi1",
                "ipv4": "10.10.0.5/30",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "input_errors": 3,
                "output_errors": 0,
                "crc_errors": 0,
            },
            {
                "name": "GigabitEthernet0/0/3",
                "description": "SPARE/transit to secondary MDF",
                "ipv4": "10.10.0.9/30",
                "admin_status": "up",
                "oper_status": "down",
                "speed_mbps": 0,
                "input_errors": 4871,
                "output_errors": 29,
                "crc_errors": 4602,
            },
            {
                "name": "Loopback0",
                "description": "Router-ID",
                "ipv4": "10.255.255.1/32",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 8000,
                "input_errors": 0,
                "output_errors": 0,
                "crc_errors": 0,
            },
        ],
        "bgp_neighbors": [
            {
                "peer_ip": "203.0.113.1",
                "remote_asn": 64501,
                "local_asn": 65001,
                "state": "Established",
                "uptime": "30d21h",
                "prefixes_received": 842312,
                "prefixes_sent": 12,
                "description": "ISP-A eBGP",
            },
            {
                "peer_ip": "10.10.0.6",
                "remote_asn": 65003,
                "local_asn": 65001,
                "state": "Established",
                "uptime": "14d02h",
                "prefixes_received": 24,
                "prefixes_sent": 842336,
                "description": "iBGP to edge-fw-01",
            },
        ],
        "routes": {
            "default": [
                {"dest": "0.0.0.0/0", "next_hop": "203.0.113.1", "protocol": "BGP", "metric": 0, "admin_distance": 20},
                {"dest": "10.10.0.0/30", "next_hop": "directly connected", "protocol": "connected", "metric": 0, "admin_distance": 0},
                {"dest": "10.10.0.4/30", "next_hop": "directly connected", "protocol": "connected", "metric": 0, "admin_distance": 0},
                {"dest": "10.10.0.8/30", "next_hop": "directly connected", "protocol": "connected", "metric": 0, "admin_distance": 0},
                {"dest": "10.20.0.0/16", "next_hop": "10.10.0.2", "protocol": "OSPF", "metric": 20, "admin_distance": 110},
                {"dest": "10.255.255.1/32", "next_hop": "directly connected", "protocol": "local", "metric": 0, "admin_distance": 0},
                {"dest": "10.255.255.2/32", "next_hop": "10.10.0.2", "protocol": "OSPF", "metric": 11, "admin_distance": 110},
                {"dest": "10.255.255.3/32", "next_hop": "10.10.0.6", "protocol": "OSPF", "metric": 11, "admin_distance": 110},
            ],
            "MGMT": [
                {"dest": "192.168.99.0/24", "next_hop": "directly connected", "protocol": "connected", "metric": 0, "admin_distance": 0},
            ],
        },
        "logs": [
            {"timestamp": "2026-04-16T22:14:02Z", "severity": "warning", "facility": "LINEPROTO", "message": "Line protocol on Interface GigabitEthernet0/0/3, changed state to down"},
            {"timestamp": "2026-04-16T22:14:12Z", "severity": "error",   "facility": "LINK",       "message": "Interface GigabitEthernet0/0/3, CRC errors exceeding threshold (4602)"},
            {"timestamp": "2026-04-17T03:02:44Z", "severity": "info",    "facility": "BGP",        "message": "neighbor 203.0.113.1 BGP session established"},
            {"timestamp": "2026-04-17T08:41:01Z", "severity": "notice",  "facility": "SYS",        "message": "Configuration saved by user atul via vty0 (10.20.5.12)"},
            {"timestamp": "2026-04-17T11:55:30Z", "severity": "warning", "facility": "LINK",       "message": "Interface GigabitEthernet0/0/3, still receiving CRC errors, suspect bad SFP or patch"},
        ],
    },

    # ------------------------------------------------------------------
    # dist-sw-01 : Catalyst 9300 style distribution switch.
    # ------------------------------------------------------------------
    "dist-sw-01": {
        "health": {
            "cpu_percent": 22,
            "memory_percent": 51,
            "uptime": "152 days, 09:11:55",
            "os_version": "IOS-XE 17.12.3",
            "hardware": "C9300-48P",
            "serial": "FJZ25330XYZ",
        },
        "interfaces": [
            {
                "name": "GigabitEthernet1/0/24",
                "description": "Uplink to core-rtr-01 Gi0/0/1",
                "ipv4": "10.10.0.2/30",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "input_errors": 0,
                "output_errors": 0,
                "crc_errors": 0,
            },
            {
                "name": "GigabitEthernet1/0/1",
                "description": "Access VLAN 10 - Finance",
                "ipv4": None,
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "input_errors": 0,
                "output_errors": 0,
                "crc_errors": 0,
            },
            {
                "name": "GigabitEthernet1/0/2",
                "description": "Access VLAN 20 - Engineering",
                "ipv4": None,
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "input_errors": 0,
                "output_errors": 0,
                "crc_errors": 0,
            },
            {
                "name": "Vlan10",
                "description": "Finance SVI",
                "ipv4": "10.20.10.1/24",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "input_errors": 0,
                "output_errors": 0,
                "crc_errors": 0,
            },
            {
                "name": "Vlan20",
                "description": "Engineering SVI",
                "ipv4": "10.20.20.1/24",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "input_errors": 0,
                "output_errors": 0,
                "crc_errors": 0,
            },
            {
                "name": "Loopback0",
                "description": "Router-ID",
                "ipv4": "10.255.255.2/32",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 8000,
                "input_errors": 0,
                "output_errors": 0,
                "crc_errors": 0,
            },
        ],
        "bgp_neighbors": [
            {
                "peer_ip": "10.10.0.1",
                "remote_asn": 65001,
                "local_asn": 65002,
                "state": "Established",
                "uptime": "14d02h",
                "prefixes_received": 12,
                "prefixes_sent": 6,
                "description": "iBGP to core-rtr-01",
            },
            {
                "peer_ip": "10.10.0.10",
                "remote_asn": 65003,
                "local_asn": 65002,
                "state": "Idle",
                "uptime": "never",
                "prefixes_received": 0,
                "prefixes_sent": 0,
                "description": "iBGP to edge-fw-01 (auth mismatch suspected)",
            },
        ],
        "routes": {
            "default": [
                {"dest": "0.0.0.0/0", "next_hop": "10.10.0.1", "protocol": "BGP", "metric": 0, "admin_distance": 200},
                {"dest": "10.10.0.0/30", "next_hop": "directly connected", "protocol": "connected", "metric": 0, "admin_distance": 0},
                {"dest": "10.20.10.0/24", "next_hop": "directly connected", "protocol": "connected", "metric": 0, "admin_distance": 0},
                {"dest": "10.20.20.0/24", "next_hop": "directly connected", "protocol": "connected", "metric": 0, "admin_distance": 0},
                {"dest": "10.255.255.1/32", "next_hop": "10.10.0.1", "protocol": "OSPF", "metric": 11, "admin_distance": 110},
                {"dest": "10.255.255.3/32", "next_hop": "10.10.0.1", "protocol": "OSPF", "metric": 22, "admin_distance": 110},
            ],
        },
        "logs": [
            {"timestamp": "2026-04-15T09:02:01Z", "severity": "error",   "facility": "BGP",   "message": "Neighbor 10.10.0.10 (AS 65003) -> MD5 authentication failure, session reset"},
            {"timestamp": "2026-04-15T09:02:03Z", "severity": "warning", "facility": "BGP",   "message": "Neighbor 10.10.0.10 (AS 65003) -> entering Idle state"},
            {"timestamp": "2026-04-17T05:30:10Z", "severity": "info",    "facility": "SPAN",  "message": "SPAN session 1 source GigabitEthernet1/0/5 destination Gi1/0/48"},
            {"timestamp": "2026-04-17T12:00:00Z", "severity": "notice",  "facility": "SYS",   "message": "Clock source NTP server 10.20.0.123 (stratum 2) synchronized"},
        ],
    },

    # ------------------------------------------------------------------
    # edge-fw-01 : high-CPU condition (suspected SYN flood), BGP side Idle.
    # ------------------------------------------------------------------
    "edge-fw-01": {
        "health": {
            "cpu_percent": 94,
            "memory_percent": 78,
            "uptime": "41 days, 02:47:19",
            "os_version": "FTDv 7.4.2",
            "hardware": "FPR-1140",
            "serial": "JAD2710PQR",
        },
        "interfaces": [
            {
                "name": "GigabitEthernet1",
                "description": "inside - to core-rtr-01",
                "ipv4": "10.10.0.6/30",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "input_errors": 0,
                "output_errors": 0,
                "crc_errors": 0,
            },
            {
                "name": "GigabitEthernet2",
                "description": "outside - to Internet edge handoff",
                "ipv4": "198.51.100.2/30",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "input_errors": 2104,
                "output_errors": 0,
                "crc_errors": 0,
            },
            {
                "name": "GigabitEthernet3",
                "description": "dmz - to dist-sw-01",
                "ipv4": "10.10.0.10/30",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "input_errors": 0,
                "output_errors": 0,
                "crc_errors": 0,
            },
            {
                "name": "Loopback0",
                "description": "Router-ID",
                "ipv4": "10.255.255.3/32",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 8000,
                "input_errors": 0,
                "output_errors": 0,
                "crc_errors": 0,
            },
        ],
        "bgp_neighbors": [
            {
                "peer_ip": "10.10.0.5",
                "remote_asn": 65001,
                "local_asn": 65003,
                "state": "Established",
                "uptime": "14d02h",
                "prefixes_received": 842336,
                "prefixes_sent": 24,
                "description": "iBGP to core-rtr-01",
            },
            {
                "peer_ip": "10.10.0.9",
                "remote_asn": 65002,
                "local_asn": 65003,
                "state": "Idle",
                "uptime": "never",
                "prefixes_received": 0,
                "prefixes_sent": 0,
                "description": "iBGP to dist-sw-01 (auth mismatch)",
            },
        ],
        "routes": {
            "default": [
                {"dest": "0.0.0.0/0", "next_hop": "198.51.100.1", "protocol": "static", "metric": 0, "admin_distance": 1},
                {"dest": "10.10.0.4/30", "next_hop": "directly connected", "protocol": "connected", "metric": 0, "admin_distance": 0},
                {"dest": "10.10.0.8/30", "next_hop": "directly connected", "protocol": "connected", "metric": 0, "admin_distance": 0},
                {"dest": "10.20.0.0/16", "next_hop": "10.10.0.5", "protocol": "OSPF", "metric": 30, "admin_distance": 110},
                {"dest": "198.51.100.0/30", "next_hop": "directly connected", "protocol": "connected", "metric": 0, "admin_distance": 0},
            ],
            "DMZ": [
                {"dest": "10.30.0.0/24", "next_hop": "directly connected", "protocol": "connected", "metric": 0, "admin_distance": 0},
            ],
        },
        "logs": [
            {"timestamp": "2026-04-17T11:52:10Z", "severity": "critical", "facility": "SYS",      "message": "CPU utilization sustained above 90% for 10 minutes"},
            {"timestamp": "2026-04-17T11:52:15Z", "severity": "warning",  "facility": "THREAT",   "message": "Possible SYN flood detected on outside interface (198.51.100.2) - 120k half-open conns"},
            {"timestamp": "2026-04-17T11:55:02Z", "severity": "warning",  "facility": "MEM",      "message": "Memory utilization above 75%, connection table growth elevated"},
            {"timestamp": "2026-04-17T11:58:44Z", "severity": "error",    "facility": "BGP",      "message": "Neighbor 10.10.0.9 MD5 authentication failed"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Simulated L3 reachability matrix. Used by the ping tool.
# ---------------------------------------------------------------------------
# Keyed by (source_device, destination_device). Destination can also be an
# IP/hostname string outside our managed set (returns reachable if it resolves
# to a directly-connected subnet of *some* device in the topology).

_REACHABILITY: dict[tuple[str, str], dict[str, Any]] = {
    ("core-rtr-01", "dist-sw-01"): {"reachable": True, "rtt_ms": 0.8, "loss_percent": 0},
    ("core-rtr-01", "edge-fw-01"): {"reachable": True, "rtt_ms": 1.2, "loss_percent": 0},
    ("dist-sw-01", "core-rtr-01"): {"reachable": True, "rtt_ms": 0.8, "loss_percent": 0},
    ("dist-sw-01", "edge-fw-01"): {"reachable": False, "rtt_ms": None, "loss_percent": 100},
    ("edge-fw-01", "core-rtr-01"): {"reachable": True, "rtt_ms": 1.2, "loss_percent": 0},
    ("edge-fw-01", "dist-sw-01"): {"reachable": False, "rtt_ms": None, "loss_percent": 100},
}


# ---------------------------------------------------------------------------
# Small helpers. Each raises KeyError with a friendly message on unknown
# device name so the MCP server can turn it into a structured error.
# ---------------------------------------------------------------------------

def _require_device(name: str) -> dict[str, Any]:
    if name not in NETWORK_STATE:
        raise KeyError(
            f"Unknown device '{name}'. Known devices: {', '.join(NETWORK_STATE.keys())}"
        )
    return NETWORK_STATE[name]


def list_devices() -> list[str]:
    return list(NETWORK_STATE.keys())


def get_interfaces(device_name: str) -> dict[str, Any]:
    dev = _require_device(device_name)
    return {"device": device_name, "interfaces": dev["interfaces"]}


def get_bgp_neighbors(device_name: str) -> dict[str, Any]:
    dev = _require_device(device_name)
    return {"device": device_name, "neighbors": dev["bgp_neighbors"]}


def get_route_table(device_name: str, vrf: str = "default") -> dict[str, Any]:
    dev = _require_device(device_name)
    routes = dev["routes"].get(vrf)
    if routes is None:
        raise KeyError(
            f"VRF '{vrf}' not found on {device_name}. Known VRFs: "
            f"{', '.join(dev['routes'].keys())}"
        )
    return {"device": device_name, "vrf": vrf, "routes": routes}


def get_device_health(device_name: str) -> dict[str, Any]:
    dev = _require_device(device_name)
    return {"device": device_name, **dev["health"]}


def get_logs(device_name: str, severity: str | None = None) -> dict[str, Any]:
    dev = _require_device(device_name)
    entries = dev["logs"]
    if severity:
        sev = severity.lower()
        entries = [e for e in entries if e["severity"].lower() == sev]
    return {"device": device_name, "severity_filter": severity, "entries": entries}


def ping_device(source: str, destination: str, count: int = 5) -> dict[str, Any]:
    """Simulated ICMP echo. Source must be a known managed device.
    Destination can be a known device, a loopback IP, or any IPv4 string."""
    _require_device(source)

    # Resolve a destination hostname -> known device
    dest_device = destination if destination in NETWORK_STATE else None
    if dest_device is None:
        # Try matching by loopback IP or any configured interface IP
        for dname, dstate in NETWORK_STATE.items():
            for iface in dstate["interfaces"]:
                if iface.get("ipv4") and iface["ipv4"].split("/")[0] == destination:
                    dest_device = dname
                    break
            if dest_device:
                break

    if dest_device and (source, dest_device) in _REACHABILITY:
        result = _REACHABILITY[(source, dest_device)]
        return {
            "source": source,
            "destination": destination,
            "resolved_device": dest_device,
            "count": count,
            "reachable": result["reachable"],
            "rtt_ms_avg": result["rtt_ms"],
            "loss_percent": result["loss_percent"],
        }

    # Unknown destination: simulate a "host unreachable" response.
    return {
        "source": source,
        "destination": destination,
        "resolved_device": None,
        "count": count,
        "reachable": False,
        "rtt_ms_avg": None,
        "loss_percent": 100,
        "note": "Destination not in simulated topology; treat as unreachable.",
    }
