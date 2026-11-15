#!/bin/sh
# Phase 01 task 0.1 probe (ADR-0006, plan D3): can a container with the planned
# settings give each attempt its own cgroup, command UID and mount view?
# Runs inside the candidate container; prints one JSON line per check.
set -u
report() { printf '{"check":"%s","ok":%s,"detail":"%s"}\n' "$1" "$2" "$3"; }

root=/sys/fs/cgroup
# A private cgroup namespace is mounted read-only; try to remount it writable,
# then move this shell into a leaf (cgroup v2 forbids processes in inner nodes).
mount -o remount,rw "$root" 2>/dev/null && report cgroup_remount true "" || report cgroup_remount false "remount refused"
mkdir -p "$root/launcher" 2>/dev/null && echo $$ > "$root/launcher/cgroup.procs" 2>/dev/null
echo "+freeze" > /dev/null
sed 's/^/+/;s/ / +/g' "$root/cgroup.controllers" > "$root/cgroup.subtree_control" 2>/dev/null || true
if mkdir "$root/probe-attempt" 2>/dev/null; then
  report cgroup_create true "sub-cgroup created"
  sh -c 'sleep 30 & sleep 30' & parent=$!
  sleep 0.2
  echo $parent > "$root/probe-attempt/cgroup.procs" 2>/dev/null && report cgroup_join true "" || report cgroup_join false "cannot move process"
  if echo 1 > "$root/probe-attempt/cgroup.freeze" 2>/dev/null; then
    sleep 0.3; state=$(grep frozen "$root/probe-attempt/cgroup.events" | cut -d' ' -f2)
    report cgroup_freeze "$( [ "$state" = 1 ] && echo true || echo false )" "frozen=$state"
    echo 0 > "$root/probe-attempt/cgroup.freeze"
  else report cgroup_freeze false "cgroup.freeze not writable"; fi
  if [ -f "$root/probe-attempt/cgroup.kill" ]; then
    echo 1 > "$root/probe-attempt/cgroup.kill"; sleep 0.3
    left=$(wc -l < "$root/probe-attempt/cgroup.procs")
    report cgroup_kill "$( [ "$left" = 0 ] && echo true || echo false )" "remaining=$left"
  else report cgroup_kill false "no cgroup.kill"; fi
  rmdir "$root/probe-attempt" 2>/dev/null
else
  report cgroup_create false "cgroup root not writable"
fi

# SIGSTOP fallback on a process group.
setsid sh -c 'sleep 30 & sleep 30' & sleep 0.2
pg=$(cut -d' ' -f5 /proc/$!/stat 2>/dev/null)
if [ -n "$pg" ] && kill -STOP -"$pg" 2>/dev/null; then
  report sigstop_group true "pgid=$pg"; kill -KILL -"$pg" 2>/dev/null
else report sigstop_group false "no process group control"; fi

# Command UID separation.
if command -v setpriv >/dev/null && setpriv --reuid=4242 --regid=4242 --clear-groups id -u >/dev/null 2>&1; then
  report command_uid true "setpriv to 4242"
else report command_uid false "cannot switch uid"; fi

# Per-attempt mount view.
if unshare -m sh -c 'mount -t tmpfs none /mnt && touch /mnt/x' 2>/dev/null; then
  report mount_namespace true "unshare -m"
elif unshare -Urm sh -c 'mount -t tmpfs none /mnt' 2>/dev/null; then
  report mount_namespace true "unshare -Urm (user namespace)"
else report mount_namespace false "no mount namespace"; fi

# Commands must not inherit the launcher's capabilities.
drop="setpriv --reuid=4242 --regid=4242 --clear-groups --inh-caps=-all --bounding-set=-all --no-new-privs"
if [ -d "$root/launcher" ]; then
  $drop sh -c "echo \$\$ > $root/cgroup.procs" 2>/dev/null && report command_cgroup_escape_blocked false "moved itself" || report command_cgroup_escape_blocked true ""
fi
$drop sh -c 'mount -t tmpfs none /mnt' 2>/dev/null && report command_mount_blocked false "mounted" || report command_mount_blocked true ""
$drop sh -c 'unshare -Urm true' 2>/dev/null && report command_userns_blocked false "user namespace allowed" || report command_userns_blocked true ""
$drop sh -c 'grep CapEff /proc/self/status' 2>/dev/null | grep -q '0000000000000000' && report command_caps_empty true "" || report command_caps_empty false "effective caps present"
