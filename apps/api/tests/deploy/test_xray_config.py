from __future__ import annotations

import base64
import importlib.util
import json
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location(
    "xray_config",
    ROOT / "deploy" / "xray-config.py",
)
assert SPEC is not None and SPEC.loader is not None
xray_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(xray_config)


def encode(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def valid_config() -> dict[str, object]:
    return {
        "inbounds": [
            {
                "tag": "mixed",
                "listen": "127.0.0.1",
                "port": 10808,
                "protocol": "mixed",
            },
        ],
        "outbounds": [
            {"tag": "proxy", "protocol": "vless", "settings": {"address": "example.invalid"}},
            {"tag": "direct", "protocol": "freedom"},
        ],
    }


def test_load_config_accepts_raw_json() -> None:
    _, proxy_url = xray_config.load_config(json.dumps(valid_config()))

    assert proxy_url == "http://127.0.0.1:10808"


def test_load_config_extracts_loopback_proxy_url() -> None:
    config, proxy_url = xray_config.load_config(encode(json.dumps(valid_config())))

    assert proxy_url == "http://127.0.0.1:10808"
    assert config["outbounds"][0]["protocol"] == "vless"


def test_public_listen_is_rejected() -> None:
    config = valid_config()
    config["inbounds"][0]["listen"] = "0.0.0.0"  # type: ignore[index]

    with pytest.raises(xray_config.ConfigError, match="loopback"):
        xray_config.load_config(encode(json.dumps(config)))


def test_any_public_inbound_is_rejected() -> None:
    config = valid_config()
    inbounds = config["inbounds"]
    assert isinstance(inbounds, list)
    inbounds.append({"tag": "extra", "listen": "0.0.0.0", "port": 1081, "protocol": "socks"})

    with pytest.raises(xray_config.ConfigError, match="every inbound"):
        xray_config.load_config(encode(json.dumps(config)))


def test_ipv6_loopback_inbound_keeps_its_host() -> None:
    config = valid_config()
    config["inbounds"][0]["listen"] = "::1"  # type: ignore[index]

    _, proxy_url = xray_config.load_config(encode(json.dumps(config)))

    assert proxy_url == "http://[::1]:10808"


def test_socks_only_inbound_is_rejected() -> None:
    config = valid_config()
    config["inbounds"][0]["protocol"] = "socks"  # type: ignore[index]

    with pytest.raises(xray_config.ConfigError, match="mixed or http"):
        xray_config.load_config(encode(json.dumps(config)))


def test_missing_vless_outbound_is_rejected() -> None:
    config = valid_config()
    config["outbounds"] = [{"protocol": "freedom"}]

    with pytest.raises(xray_config.ConfigError, match="vless"):
        xray_config.load_config(encode(json.dumps(config)))


@pytest.mark.parametrize("payload", ["not-base64!", encode("not-json"), encode("[]")])
def test_invalid_payloads_are_rejected(payload: str) -> None:
    with pytest.raises(xray_config.ConfigError):
        xray_config.load_config(payload)


def test_write_config_is_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "proxy" / "config.json"
    xray_config.write_config(valid_config(), str(path))

    assert json.loads(path.read_text(encoding="utf-8"))["inbounds"][0]["port"] == 10808
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_main_extract_prints_proxy_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _stdin(encode(json.dumps(valid_config()))))
    target = tmp_path / "config.json"
    assert xray_config.main(["--extract", "--path", str(target)]) == 0
    assert not target.exists()


def test_main_writes_config_and_remove_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "config.json"
    monkeypatch.setattr("sys.stdin", _stdin(encode(json.dumps(valid_config()))))
    assert xray_config.main(["--path", str(target)]) == 0
    assert target.exists()
    assert "proxy_url=http://127.0.0.1:10808" in capsys.readouterr().out

    assert xray_config.main(["--remove", "--path", str(target)]) == 0
    assert not target.exists()


def test_main_returns_invalid_code_for_bad_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", _stdin(encode("{}")))
    assert xray_config.main(["--extract"]) == xray_config.EXIT_INVALID


class _stdin:
    def __init__(self, value: str) -> None:
        self._value = value

    def read(self) -> str:
        return self._value
