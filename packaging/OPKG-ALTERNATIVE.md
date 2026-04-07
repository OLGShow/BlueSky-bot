# Alternative: opkg/Entware update channel

This document describes an **optional** opkg-based delivery path
for environments running [Entware](https://github.com/Entware/Entware)
(typically NAS, routers, or embedded Linux systems).

> **The primary channel is APT/.deb** (see README).
> Use this path only if your target system has `opkg` and NOT `apt`.

## Prerequisites

- Working Entware runtime with `opkg`
- Python 3.10+ available (usually `opkg install python3`)
- Internet access for feed index + pip dependencies

## One-time setup

```sh
# Add custom feed
echo "src/gz bluesky-bot https://olgshow.github.io/BlueSky-bot/opkg" \
  >> /opt/etc/opkg.conf

opkg update
opkg install bluesky-bot
```

## Update

```sh
opkg update && opkg upgrade bluesky-bot
```

## Package layout (ipk)

If you want to build `.ipk` manually:

```
packaging/opkg/
  control        # Package metadata (fields similar to deb/control)
  postinst       # pip install + service enable
  prerm          # service stop
```

Build with:

```sh
# Requires opkg-utils (opkg-make-index, ipkg-build)
ipkg-build packaging/opkg/
```

## Limitations

- Entware paths differ (`/opt/` prefix, `/opt/etc/init.d/` for services).
- No systemd — use procd or S-scripts for process management.
- This track is NOT tested in CI. Use at your own risk.
- GPG signing for the opkg feed is not implemented.

## Current status

**Not actively maintained.** The APT/.deb path is the supported delivery mechanism.
If you need opkg support, please open an issue describing your target platform.
