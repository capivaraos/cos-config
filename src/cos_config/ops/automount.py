"""Mount extra disks at boot, through /etc/fstab, without breaking the boot.

Each entry we add is preceded by a marker line, so we only ever touch our
own entries. Safety rules:

* the helper never takes a path or fstype from the caller: it looks the
  partition up by UUID, refuses system partitions and anything fstab
  already handles, and derives the mount point (/mnt/<label>) itself;
* every entry has nofail + x-systemd.device-timeout, so a missing disk
  never stops the boot;
* the new fstab must not have more `findmnt --verify` errors than the old
  one (pre-existing problems are not ours to judge; note findmnt crashes
  on malformed lines, which we never write);
* the disk is mounted right away; if that fails, the old fstab is put back.
"""

import json
import os
import pwd
import re
import subprocess

from . import common

FSTAB = "/etc/fstab"
MNT = "/mnt"
MARKER = "# cos-config: managed"
SUPPORTED = ("ext4", "xfs", "btrfs", "ntfs", "exfat", "vfat")
SYSTEM_TARGETS = ("/", "/boot", "/boot/efi", "/efi", "/home", "/var", "/usr",
                  "/tmp", "/srv", "/opt", "[SWAP]")
SAFE_OPTS = "nofail,x-systemd.device-timeout=10s"
_UUID_RE = re.compile(r"^[0-9A-Fa-f-]{4,36}$")


# ---- fstab -------------------------------------------------------------------
def parse_fstab(text):
    """[(source, target, fstype, managed)] for every entry."""
    entries, managed_next = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == MARKER:
            managed_next = True
            continue
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) >= 3:
            entries.append((fields[0], fields[1], fields[2], managed_next))
        managed_next = False
    return entries


def entry_line(uuid, target, fstype, options):
    for field in (uuid, target, fstype, options):
        if not field or any(c.isspace() for c in field) or field.startswith("#"):
            raise common.ValidationError(f"bad fstab field {field!r}")
    return f"UUID={uuid} {target} {fstype} {options} 0 0"


def with_entry(text, line):
    sep = "" if text.endswith("\n") or not text else "\n"
    return f"{text}{sep}{MARKER}\n{line}\n"


def without_entry(text, uuid):
    """*text* without our managed entry for *uuid* (and its marker)."""
    out, lines, i = [], text.splitlines(keepends=True), 0
    while i < len(lines):
        if lines[i].strip() == MARKER and i + 1 < len(lines) \
                and lines[i + 1].split()[:1] == [f"UUID={uuid}"]:
            i += 2
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)


# ---- what to mount, and how ----------------------------------------------------
def mount_options(fstype, uid, gid):
    """(fstype for fstab, options)."""
    if fstype in ("ext4", "xfs", "btrfs"):
        return fstype, f"defaults,{SAFE_OPTS}"
    if uid is None or gid is None:
        raise common.ValidationError("the owner's uid is needed for this filesystem")
    owner = f"uid={int(uid)},gid={int(gid)},umask=022"
    if fstype == "ntfs":
        return "ntfs3", f"{owner},windows_names,{SAFE_OPTS}"
    if fstype == "exfat":
        return "exfat", f"{owner},{SAFE_OPTS}"
    if fstype == "vfat":
        return "vfat", f"{owner},utf8,{SAFE_OPTS}"
    raise common.ValidationError(f"unsupported filesystem {fstype!r}")


def mount_name(label, uuid, taken):
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", label or "").strip("-.") or f"disk-{uuid[:8]}"
    name, n = base, 2
    while os.path.join(MNT, name) in taken:
        name, n = f"{base}-{n}", n + 1
    return os.path.join(MNT, name)


def _flatten(devices):
    for dev in devices:
        yield dev
        yield from _flatten(dev.get("children") or [])


def partitions(lsblk_json, fstab_text):
    """Partitions with a supported filesystem and their status:
    managed / system / elsewhere / available; plus our entries whose disk
    is not connected (status "missing")."""
    entries = parse_fstab(fstab_text)
    by_uuid = {src[5:]: (tgt, managed) for src, tgt, _fs, managed in entries if src.startswith("UUID=")}
    other_sources = {src for src, _t, _f, managed in entries if not managed}
    system_uuids = {src[5:] for src, tgt, _f, _m in entries
                    if src.startswith("UUID=") and tgt in SYSTEM_TARGETS}
    taken = {tgt for _s, tgt, _f, _m in entries}
    out, seen = [], set()
    for dev in _flatten(json.loads(lsblk_json).get("blockdevices", [])):
        uuid, fstype = dev.get("uuid"), dev.get("fstype")
        if dev.get("type") not in ("part", "disk") or fstype not in SUPPORTED or not uuid:
            continue
        seen.add(uuid)
        mounts = [m for m in (dev.get("mountpoints") or []) if m]
        target, managed = by_uuid.get(uuid, (None, False))
        if managed:
            status = "managed"
        elif uuid in system_uuids or any(m in SYSTEM_TARGETS for m in mounts):
            status = "system"
        elif target or any(s in other_sources for s in
                           (f"PARTUUID={dev.get('partuuid')}", f"LABEL={dev.get('label')}", dev.get("path"))):
            status = "elsewhere"
        else:
            status = "available"
            target = mount_name(dev.get("label"), uuid, taken)
            taken.add(target)
        out.append({
            "uuid": uuid, "path": dev.get("path"), "fstype": fstype,
            "label": dev.get("label") or "", "size": int(dev.get("size") or 0),
            "mounts": mounts, "target": target, "status": status,
        })
    for src, tgt, fs, managed in entries:
        if managed and src.startswith("UUID=") and src[5:] not in seen:
            out.append({"uuid": src[5:], "path": None, "fstype": fs, "label": "", "size": 0,
                        "mounts": [], "target": tgt, "status": "missing"})
    return out


# ---- machine access ----------------------------------------------------------
LSBLK = ["lsblk", "-J", "-b", "-o",
         "NAME,PATH,UUID,PARTUUID,FSTYPE,LABEL,SIZE,MOUNTPOINTS,TYPE"]


def read_lsblk():
    return subprocess.run(LSBLK, capture_output=True, text=True, timeout=20).stdout


def read_fstab(path=None):
    try:
        with open(path or FSTAB, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""


def parse_verify(returncode, output):
    """Error count from `findmnt --verify`, or None when it cannot be trusted
    (crashed, or the table has parse errors).

    A clean table prints "Success, no errors or warnings detected" and no
    counts; otherwise "N parse errors, N errors, N warnings".
    """
    if returncode < 0 or returncode > 1:
        return None
    match = re.search(r"(\d+) parse errors?, (\d+) errors?", output)
    if match:
        return None if int(match.group(1)) else int(match.group(2))
    return 0 if returncode == 0 else None


def verify_errors(text):
    """Error count `findmnt --verify` reports for *text* (None if it crashed)."""
    path = FSTAB + ".cos-config.check"
    common.atomic_write(path, text)
    try:
        proc = subprocess.run(["findmnt", "--verify", "--tab-file", path],
                              capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    return parse_verify(proc.returncode, proc.stdout + proc.stderr)


def _owner():
    """uid/gid of the user who asked (pkexec sets PKEXEC_UID)."""
    uid = os.environ.get("PKEXEC_UID")
    if not uid or not uid.isdigit():
        return None, None
    try:
        return int(uid), pwd.getpwuid(int(uid)).pw_gid
    except KeyError:
        return None, None


def _find(uuid):
    if not _UUID_RE.match(uuid or ""):
        raise common.ValidationError("bad UUID")
    for part in partitions(read_lsblk(), read_fstab()):
        if part["uuid"] == uuid:
            return part
    raise common.ValidationError("no such partition")


def _write_fstab(text):
    common.backup(FSTAB)
    common.atomic_write(FSTAB, text)
    common.run_cmd(["systemctl", "daemon-reload"])


def _rmdir_if_empty(target):
    if os.path.dirname(target) == MNT and os.path.isdir(target) and not os.listdir(target):
        os.rmdir(target)


def add(uuid):
    part = _find(uuid)
    if part["status"] != "available":
        raise common.ValidationError(f"partition is {part['status']}, not available")
    uid, gid = _owner()
    fstype, opts = mount_options(part["fstype"], uid, gid)
    target = part["target"]
    old = read_fstab()
    new = with_entry(old, entry_line(uuid, target, fstype, opts))
    os.makedirs(target, mode=0o755, exist_ok=True)
    before, after = verify_errors(old), verify_errors(new)
    if after is None or (before is not None and after > before):
        _rmdir_if_empty(target)
        raise RuntimeError("the new /etc/fstab did not pass findmnt --verify; nothing was changed")
    _write_fstab(new)
    try:
        common.run_cmd(["mount", target])
    except RuntimeError as exc:
        _write_fstab(old)
        _rmdir_if_empty(target)
        hint = ""
        if part["fstype"] == "ntfs":
            hint = ("\nIf this disk is used by Windows, turn off Fast Startup there "
                    "and shut Windows down fully, then try again.")
        raise RuntimeError(f"the disk could not be mounted; /etc/fstab was restored.\n{exc}{hint}")


def remove(uuid):
    if not _UUID_RE.match(uuid or ""):
        raise common.ValidationError("bad UUID")
    old = read_fstab()
    target = next((t for s, t, _f, m in parse_fstab(old) if m and s == f"UUID={uuid}"), None)
    if target is None:
        raise common.ValidationError("not a COS Config Center entry")
    if os.path.ismount(target):
        common.run_cmd(["umount", target])
    _write_fstab(without_entry(old, uuid))
    _rmdir_if_empty(target)


def describe(part, uid, gid, adding):
    if adding:
        fstype, opts = mount_options(part["fstype"], uid, gid)
        line = entry_line(part["uuid"], part["target"], fstype, opts)
        return [f"sudo mkdir -p {part['target']}",
                f"echo '{MARKER}' | sudo tee -a /etc/fstab",
                f"echo '{line}' | sudo tee -a /etc/fstab",
                "sudo systemctl daemon-reload",
                f"sudo mount {part['target']}"]
    return [f"sudo umount {part['target']}",
            f"# remove the line UUID={part['uuid']} (and the marker above it) from /etc/fstab",
            "sudo systemctl daemon-reload"]


def helper_main(argv):
    """argv: ["add", UUID] or ["remove", UUID]."""
    if len(argv) == 2 and argv[0] == "add":
        add(argv[1])
    elif len(argv) == 2 and argv[0] == "remove":
        remove(argv[1])
    else:
        raise common.ValidationError("usage: add UUID | remove UUID")
