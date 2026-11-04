# Native-systemd OpenWrt cgroups

> **Units mode.** Since procd 6 / systemd-openwrt 14, `openwrt-procd.service`
> runs `procd --systemd=units` and procd instances are transient
> `openwrt-SERVICE@INSTANCE.service` units in the same per-service slices,
> supervised by systemd; see
> [systemd supervision of OpenWrt services](systemd-native-supervision.md).
> Their ubus records carry `systemd_unit` and `systemd_placement: unit`. The
> scope mechanism below still applies to rc script executions
> (`openwrt-cgroup exec`), to instances that units mode cannot express (vrf,
> trace, OCI bundles, passed descriptors, jail console or setns) and to the
> legacy `--systemd` mode used for rollback.

Procd remains the supervisor for OpenWrt service instances. Original init scripts
retain legacy lifecycle actions, respawn helpers, custom restart locks, UCI
triggers, and rc.d enablement. Systemd owns the scope and slice hierarchy. The
optional systemctl bridge supplies CLI control and live status without creating
proxy service units or per-service observer processes.

## Audit and design decision

The previous arrangement put persistent bridge proxies in service units while
procd launched the actual daemons elsewhere. Unit activity therefore did not
prove daemon membership or apply limits to those daemons. Native procd also
created its traditional root-level `services` hierarchy, and OCI jail code
could create `containers` or walk controller settings through manager-owned
ancestors. Delegating only procd's own service did not authorize these writes.
A second observer per service added persistent processes and cleanup races
without improving lifecycle ownership.

Use one small registration implementation shared by procd and the transient
init-script launcher. Register the original execution, keep one slice per
service for policy, and use a fresh scope for each execution. Keep the optional
central CLI broker for authorization and status. No service mirroring,
PID-scanning migration, controller daemon, or second supervisor is required.

This follows systemd's [cgroup delegation rules](https://systemd.io/CGROUP_DELEGATION/)
and its [manager API](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.systemd1.html).
Runtime evidence and remaining prerequisites are recorded in
[cgroup validation](systemd-cgroups-validation.md).

## Placement and resource policy

`openwrt.slice` contains one slice per service. Service-name components use unit
escaping; for example `my-service` uses `openwrt-my\x2dservice.slice`.
Each execution gets a fresh `openwrt-<random-id>.scope`. Slice limits apply to
all executions and descendants of that service, including concurrent instances.
No restrictive memory or task limits are introduced by default.

Examples:

    systemctl list-units --all 'openwrt*.scope' 'openwrt*.slice'
    systemctl set-property openwrt-dnsmasq.slice MemoryMax=256M TasksMax=128
    systemctl show openwrt-dnsmasq.slice -p ControlGroup -p MemoryCurrent -p TasksCurrent

Procd's ubus instance records expose `systemd_scope` and `systemd_placement`.
The latter is `pending`, `managed`, or `inherited`, independently of daemon
health. The optional bridge displays this metadata and observes processes in
the service slice. It reports unknown aggregate placement when membership
cannot be established; absence of a scope is not proof of service failure.

The scope is a process/resource object, not the service lifecycle interface.
Use `/etc/init.d/NAME ACTION`, LuCI, or supported `systemctl openwrt@NAME` actions.
Stopping a procd execution's scope directly kills processes; procd may respawn
them according to its existing policy. An empty scope is not a failed daemon,
and a populated scope is not proof that the service works.

## Launch and cleanup

Procd registers its original child with PID 1 before execution, privilege
changes, and jail entry. A pidfd identifies that child. Registration uses the
root manager's private socket, so early placement does not depend on system
D-Bus readiness. Successful registration waits for scope activation, including
the interval when a newly queued job still reports an inactive unit.

`rc.common` uses a short-lived helper to place its shell before sourcing the
script. Background jobs, double forks, sessions, and legacy restart monitors
inherit placement. Custom script handlers and their arguments remain intact.
Boot and bridge runners also wrap scripts that do not use rc.common. Arbitrary
standalone programs bypassing these entry points inherit their launcher's
placement; there is no PID-scanning migration mechanism.

Procd keeps its graceful signals, timeouts, watchdogs, and respawn decisions.
It requests scope cleanup through the manager when stopping or replacing an
execution, and after respawning or jailed executions exit. It waits for workers
to drain before replacement. A normal parent exit with respawn disabled retains
daemonized children until an explicit stop or replacement. Scope IDs
are never reused across executions. Legacy scopes remain populated after an
init script exits and disappear when their descendants exit. Original legacy
stop handlers remain authoritative: a handler that leaves a process running
leaves a visible populated scope rather than inviting a generic reaper.

During procd shutdown its event loop continues processing exit and cleanup
callbacks. Scopes are bound to procd and ordered before it, so normal OpenWrt
shutdown scripts and procd shutdown precede final scope teardown. This also
provides manager cleanup after procd failure. Bridge restarts do not stop
workload scopes.

## Delegation and failure behavior

Ordinary scopes are not delegated. Jailed or VRF executions receive explicit
delegation when needed. Systemd owns the scope boundary and its resource
limits. Jail writers manage only their delegated descendants and delegation
interfaces. Supervisory and payload processes occupy separate leaves before
controllers are enabled. Ancestor controller walks stop at the delegation
boundary; code never fabricates systemd cgroup paths from unit names.

On native systemd, OCI cgroup labels are local to the delegated payload subtree.
Systemd-style labels supply the local container identifier; they do not grant
permission to create or alter a host scope by path. Absolute or traversal paths
outside this model are rejected. Standalone OCI jails establish a delegated
scope before manipulating their subtree. Procd recovery retains the original
cgroupfs behavior. Podman/crun retain their own system and user-manager scopes;
OpenWrt does not move their container PIDs back into its service slices.

If registration fails, ordinary launches log degraded placement and continue
in their inherited cgroup. They never fall back to creating host-root cgroups.
Required VRF binding and mandatory jail isolation still fail if they cannot be
satisfied. In degraded placement, per-service limits and descendant cleanup
cannot be guaranteed; status and logs must not claim otherwise.

Do not migrate a live router's existing cgroups in place. Build and validate an
exact image in a disposable VM, including networking and containers, before any
separately authorized physical deployment.
