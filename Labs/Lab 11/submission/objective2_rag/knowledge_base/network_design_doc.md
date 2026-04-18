# NextHop Enterprise Network Design Document

**Owner:** Network Engineering — atul@nexthop.ai
**Revision:** 2.3
**Date:** 2026-03-28

## 1. Summary

This document describes the NextHop HQ + Branch WAN. The topology
consists of three L3 devices at HQ (Router1, Switch1, Firewall1), one
branch router (Router2) with a branch access switch (Switch2), and a
single internet egress via ISP-A.

## 2. Addressing plan

| Range            | Purpose                                    |
|------------------|--------------------------------------------|
| 10.10.0.0/24     | Point-to-point transit links between L3 devices |
| 10.20.0.0/16     | User VLANs (by site)                       |
| 10.30.0.0/24     | DMZ / published services                   |
| 10.255.255.0/24  | Loopbacks / Router-IDs                     |
| 192.168.99.0/24  | Out-of-band management                     |
| 198.51.100.0/30  | ISP-A handoff                              |
| 203.0.113.0/30   | Legacy/secondary ISP handoff on Router1    |

### Point-to-point transit

| Link                               | Subnet            |
|------------------------------------|-------------------|
| Router1 Gi0/0/1 – Switch1 Gi1/0/24 | 10.10.0.0/30      |
| Router1 Gi0/0/2 – Firewall1 Gi1    | 10.10.0.4/30      |
| Router1 Gi0/0/3 – secondary MDF    | 10.10.0.8/30      |
| Switch1 – Firewall1 (DMZ transit)  | 10.10.0.8/30 (shared logical) |
| Router1 – Router2 (MPLS)           | 10.10.0.12/30     |

### VLAN / site IP plan

| VLAN | Name        | Subnet          | SVI owner | Site   |
|------|-------------|-----------------|-----------|--------|
| 10   | FINANCE     | 10.20.10.0/24   | Switch1   | HQ     |
| 20   | ENGINEERING | 10.20.20.0/24   | Switch1   | HQ     |
| 30   | SALES       | 10.20.30.0/24   | Router2   | Branch |
| 40   | VOICE       | 10.20.40.0/24   | Router2   | Branch |
| 50   | DMZ_TRANSIT | 10.30.0.0/24    | Firewall1 | HQ     |
| 99   | MGMT        | 192.168.99.0/24 | Switch1   | Global |

## 3. Routing architecture

### OSPF

- Single OSPF process, process-id `1`.
- Area 0 (backbone): all HQ L3 devices — Router1, Switch1, Firewall1.
- Area 10 (branch): Router2 and its dot1Q subinterfaces. Configured as
  `stub no-summary` to limit LSA types on the low-bandwidth MPLS link.
- All P2P transit links use `ip ospf network point-to-point` to avoid
  DR/BDR election overhead.
- All user VLAN SVIs are `passive-interface` to prevent adjacencies
  forming across access ports.
- Router-IDs are statically assigned from the 10.255.255.0/24 loopback
  range (Router1 .1, Switch1 .2, Firewall1 .3, Router2 .4).

### BGP

- Internal AS: `65001`. iBGP is full-mesh between Router1, Switch1
  (AS 65002 confederation sub-AS), and Firewall1 (AS 65003 confederation
  sub-AS). See §4 for the peering matrix.
- External AS: `64501` (ISP-A), peered only from Router1 over
  203.0.113.0/30.
- All iBGP sessions use `update-source Loopback0` and `next-hop-self`.
- eBGP toward ISP-A is MD5-authenticated (password managed via Ansible
  vault, rotated quarterly).

## 4. Peering matrix (intended state)

| From       | To         | Type | Local AS | Remote AS | Auth                |
|------------|------------|------|----------|-----------|---------------------|
| Router1    | ISP-A      | eBGP | 65001    | 64501     | MD5                 |
| Router1    | Firewall1  | iBGP | 65001    | 65003     | none                |
| Router1    | Router2    | iBGP | 65001    | 65001     | none                |
| Switch1    | Router1    | iBGP | 65002    | 65001     | none                |
| Switch1    | Firewall1  | iBGP | 65002    | 65003     | **MD5 (must match)**|
| Firewall1  | Router1    | iBGP | 65003    | 65001     | none                |
| Firewall1  | Switch1    | iBGP | 65003    | 65002     | **MD5 (must match)**|

> **Operational note (2026-03-18):** the Switch1 ↔ Firewall1 session
> flipped to Idle after a password rotation on Firewall1 that was not
> mirrored on Switch1. Both ends **must** carry the same `neighbor …
> password` value; otherwise the session never leaves Idle.

## 5. Traffic flow reference: VLAN 10 → Internet

1. Client on VLAN 10 (Finance, 10.20.10.0/24) sends traffic to
   default gateway `10.20.10.1` on Switch1.
2. Switch1 forwards via OSPF default route learned from Router1 out
   `Gi1/0/24` → `10.10.0.1`.
3. Router1 forwards the packet via its static default
   `ip route 0.0.0.0 0.0.0.0 203.0.113.1`, BUT for user VLAN traffic
   the policy requires traversal of Firewall1: Router1 has a
   route-map steering `10.20.0.0/16` toward `10.10.0.6` (Firewall1).
4. Firewall1 applies the `inside → outside` policy, NATs the source
   with the `USER_VLANS` object (PAT to interface `outside`), and
   forwards to the ISP via `198.51.100.1`.
5. Return traffic follows the reverse path; stateful inspection is
   performed by Firewall1.

## 6. Security zones

- **outside** (security-level 0) = ISP handoff (198.51.100.0/30)
- **inside** (security-level 100) = HQ user VLANs and transit links
- **dmz** (security-level 50) = published-service servers in 10.30.0.0/24

Inbound policy from outside is defined by ACL `OUTSIDE_IN` on
Firewall1 (see firewall1 running-config for full rules). Only
published services on 198.51.100.10–12 are permitted from the Internet.
