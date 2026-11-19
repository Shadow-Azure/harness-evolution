"""Validate and install the Xray config delivered by the deploy pipeline.

The workflow reads the GitHub Environment Secret ``XRAY_CONFIG`` and pipes its
base64 form to this script on stdin. ``--extract`` runs on the runner and only
validates the structure, printing the local HTTP proxy URL used for the
post-start probe. The default mode runs on the server and atomically writes
``/opt/harness/shared/proxy/config.json`` with mode 0600.

Only a loopback mixed/http inbound is accepted: the local proxy must never be
reachable from the network. VLESS credentials stay in the config file; the API
receives only ``HE_GIT_PROXY``, a credential-free local address.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
from contextlib import suppress
from typing import Any

DEFAULT_PATH = "/opt/harness/shared/proxy/config.json"
LOOPBACK_LISTEN = {"127.0.0.1", "localhost", "::1"}
EXIT_INVALID = 3


class ConfigError(ValueError):
    """The supplied Xray config is not safe to install."""


def decode_stdin(text: str) -> str:
    """Decode one base64 body from the workflow's stdin."""
    try:
        return base64.b64decode(text.strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ConfigError("config is not valid base64/UTF-8") from exc


def parse_config(text: str) -> dict[str, Any]:
    """Parse the JSON object and reject shapes that would expose a proxy."""
    try:
        config = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config is not valid JSON: {exc.msg}") from exc
    if not isinstance(config, dict):
        raise ConfigError("config must be a JSON object")
    inbounds = config.get("inbounds")
    outbounds = config.get("outbounds")
    if not isinstance(inbounds, list) or not inbounds:
        raise ConfigError("config.inbounds must be a non-empty list")
    if not isinstance(outbounds, list) or not outbounds:
        raise ConfigError("config.outbounds must be a non-empty list")
    if not any(
        isinstance(outbound, dict) and outbound.get("protocol") == "vless"
        for outbound in outbounds
    ):
        raise ConfigError("config.outbounds must include a vless outbound")
    return config


def extract_proxy_url(config: dict[str, Any]) -> str:
    """Return the first loopback mixed/http inbound as an HTTP proxy URL."""
    for inbound in config.get("inbounds", []):
        if not isinstance(inbound, dict):
            continue
        if inbound.get("protocol") not in {"mixed", "http"}:
            continue
        listen = str(inbound.get("listen") or "")
        port = inbound.get("port")
        if listen not in LOOPBACK_LISTEN:
            raise ConfigError(
                f"mixed/http inbound must listen on loopback, got {listen or '<all interfaces>'}",
            )
        if not isinstance(port, int) or not 1 <= port <= 65_535:
            raise ConfigError("mixed/http inbound has an invalid port")
        return f"http://127.0.0.1:{port}"
    raise ConfigError("config needs a loopback mixed or http inbound")


def write_config(config: dict[str, Any], path: str) -> None:
    """Atomically write the config with owner-only permissions."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=".config.", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(temporary)
        raise


def load_config(text: str) -> tuple[dict[str, Any], str]:
    """Parse and validate one base64 config, returning it with its proxy URL."""
    config = parse_config(decode_stdin(text))
    return config, extract_proxy_url(config)


def main(argv: list[str] | None = None) -> int:
    """Validate stdin and either print the proxy URL or install the config."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--extract", action="store_true", help="validate only; print proxy_url")
    parser.add_argument("--remove", action="store_true", help="remove the installed config")
    args = parser.parse_args(argv)

    if args.remove:
        try:
            os.unlink(args.path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"::error::删除代理配置失败：{exc}", file=sys.stderr)
            return 2
        print("removed")
        return 0

    try:
        config, proxy_url = load_config(sys.stdin.read())
    except ConfigError as exc:
        print(f"::warning::XRAY_CONFIG 无效，跳过代理：{exc}", file=sys.stderr)
        return EXIT_INVALID

    if not args.extract:
        try:
            write_config(config, args.path)
        except OSError as exc:
            print(f"::error::写入代理配置失败：{exc}", file=sys.stderr)
            return 2
    print(f"proxy_url={proxy_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
