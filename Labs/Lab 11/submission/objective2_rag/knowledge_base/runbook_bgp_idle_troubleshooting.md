# Runbook: BGP neighbor stuck in Idle

**Applies to:** Cisco IOS-XE and Cisco Firepower FTD peers inside AS 65001
**Severity:** P2 (service-affecting if peer is in the forwarding path)
**Owner:** NetOps on-call
**Last reviewed:** 2026-04-02

## Symptoms

- `show ip bgp summary` on the local peer shows `State/PfxRcd = Idle`
- `show logging | include BGP` shows repeated messages such as
  - `%BGP-5-ADJCHANGE: neighbor x.x.x.x Down BGP Notification sent`
  - `%TCP-6-BADAUTH: No MD5 digest from <ip>:179 to <ip>:179`
- The session has `uptime: never` or oscillates between Idle and
  Connect.

## Root causes (in descending frequency at NextHop)

1. **MD5 authentication password mismatch.** Accounts for ~70% of Idle
   sessions we see. Both peers must carry **identical** `neighbor …
   password` values.
2. TCP reachability between loopbacks broken (IGP flap or missing
   static).
3. Remote-AS mismatch (usually a typo in `remote-as`).
4. ACL on transit interface dropping TCP/179.
5. Peer's BGP process administratively shut.

## Triage

1. On the local peer:
   ```
   show ip bgp neighbor <peer-ip>
   show logging | include BGP|TCP
   ping <peer-loopback> source Loopback0
   ```
2. If ping succeeds but BGP is still Idle, check for MD5 errors in the
   log with `%TCP-6-BADAUTH`. That is the fingerprint of cause #1.
3. Compare the configured password on both ends:
   ```
   show running-config | section router bgp
   ```
4. Validate remote-AS:
   ```
   show running-config | include neighbor <peer-ip>
   ```

## Remediation for cause #1 (password mismatch)

1. On whichever peer has the **stale** password, reconfigure:
   ```
   router bgp <local-asn>
     no neighbor <peer-ip> password
     neighbor <peer-ip> password <correct-shared-secret>
   clear ip bgp <peer-ip>
   ```
2. Confirm the session goes through Idle → Connect → OpenSent →
   OpenConfirm → Established.
3. Remove `%TCP-6-BADAUTH` entries from monitoring filters once they
   stop appearing.

## Known current incident (2026-04-15)

Switch1 ↔ Firewall1 (10.10.0.9 ↔ 10.10.0.10) has been Idle since
2026-04-15 09:02Z. Firewall1 carries password `MD5-SECRET-DIFFERENT`
while Switch1 still carries `MD5-SECRET-ORIGINAL`. Change window is
scheduled for 2026-04-18 at 22:00 local — align the secret on Switch1.
