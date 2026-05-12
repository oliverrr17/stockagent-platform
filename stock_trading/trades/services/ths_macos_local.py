from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import json
import os
import plistlib
import re
import sqlite3
import subprocess
from typing import Any


@dataclass(frozen=True)
class PayloadCandidate:
    source: str
    key: str
    payload: Any
    priority: int


class NSKeyedArchiveDecoder:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.objects = payload.get("$objects", [])

    def decode(self) -> Any:
        top = self.payload.get("$top", {})
        if "root" not in top:
            return self.payload
        return self._decode_value(top["root"])

    def _decode_value(self, value: Any) -> Any:
        if isinstance(value, plistlib.UID):
            index = self._uid_value(value)
            if index >= len(self.objects):
                return None
            return self._decode_value(self.objects[index])

        if isinstance(value, list):
            return [self._decode_value(item) for item in value]

        if not isinstance(value, dict):
            return value

        class_name = self._class_name(value.get("$class"))
        if "NS.keys" in value and "NS.objects" in value:
            keys = [self._decode_value(item) for item in value["NS.keys"]]
            objects = [self._decode_value(item) for item in value["NS.objects"]]
            return {
                key: obj
                for key, obj in zip(keys, objects, strict=False)
                if key is not None
            }

        if "NS.objects" in value:
            return [self._decode_value(item) for item in value["NS.objects"]]

        if class_name == "NSNull":
            return None

        return {
            key: self._decode_value(obj)
            for key, obj in value.items()
            if key != "$class"
        }

    def _class_name(self, class_uid: Any) -> str:
        if not isinstance(class_uid, plistlib.UID):
            return ""
        index = self._uid_value(class_uid)
        if index >= len(self.objects):
            return ""
        candidate = self.objects[index]
        if isinstance(candidate, dict):
            return str(candidate.get("$classname", ""))
        return ""

    @staticmethod
    def _uid_value(value: plistlib.UID) -> int:
        return int(getattr(value, "data", value))


class THSMacosLocalBackend:
    DEFAULT_APP_PATH = Path("/Applications/同花顺.app")
    DEFAULT_CONTAINER_PATH = Path.home() / "Library/Containers/cn.com.10jqka.macstock"
    DEFAULT_FILE_GLOBS = (
        "Data/Documents/cifox_trade*.log",
        "Data/Library/Caches/HXLogger/TradeRelativeLog/*.log",
    )

    def __init__(
        self,
        config: dict[str, Any],
        trade_normalizer,
        position_normalizer,
    ):
        self.config = config
        self.trade_normalizer = trade_normalizer
        self.position_normalizer = position_normalizer
        self.trade_date = config.get("trade_date")
        self.app_path = self._resolve_path(
            config.get("ths_mac_app_path") or os.getenv("THS_MAC_APP_PATH", ""),
            self.DEFAULT_APP_PATH,
        )
        self.container_path = self._resolve_path(
            config.get("ths_mac_container_path") or os.getenv("THS_MAC_CONTAINER_PATH", ""),
            self.DEFAULT_CONTAINER_PATH,
        )
        self.require_app_running = self._resolve_bool(
            config.get("ths_mac_require_app_running"),
            os.getenv("THS_MAC_REQUIRE_APP_RUNNING", "False"),
        )
        self.file_globs = self._resolve_globs(
            config.get("ths_mac_log_glob") or os.getenv("THS_MAC_LOG_GLOB", "")
        )
        self.app_running_checker = config.get("ths_mac_app_running_checker")

    def is_configured(self) -> bool:
        return self.unavailable_reason() is None

    def unavailable_reason(self) -> str | None:
        if not self.app_path.exists():
            return f"THS macOS app not found: {self.app_path}"
        if not self.container_path.exists():
            return f"THS macOS container not found: {self.container_path}"
        if self.require_app_running and not self._is_app_running():
            return "THS macOS app is not running."
        if not self._has_candidate_sources():
            return f"No THS macOS local data sources found under {self.container_path}"
        return None

    def test_connection(self) -> bool:
        return self.is_configured()

    def fetch_today_trades(self) -> list[dict]:
        normalized: list[dict] = []
        for candidate in self._iter_payload_candidates():
            for row in self._extract_trade_rows(candidate):
                try:
                    normalized.append(self.trade_normalizer(row))
                except Exception:
                    continue
        deduped = self._dedupe_trades(normalized)
        if self.trade_date is None:
            return deduped
        return [row for row in deduped if row["trade_time"].date() == self.trade_date]

    def fetch_positions(self) -> list[dict]:
        normalized: list[dict] = []
        for candidate in self._iter_payload_candidates():
            for row in self._extract_position_rows(candidate):
                try:
                    normalized.append(self.position_normalizer(row))
                except Exception:
                    continue
        deduped = self._dedupe_positions(normalized)
        if deduped:
            return deduped

        trade_candidates = self._iter_xcs_trade_file_payloads()
        if not trade_candidates:
            return []
        reconstructed = self._reconstruct_positions_from_trade_file(trade_candidates[0].payload)
        return self._dedupe_positions(reconstructed)

    def inspect_cache(self, limit: int = 100, related_only: bool = False) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "app_path": str(self.app_path),
            "container_path": str(self.container_path),
            "manifest_path": str(self._manifest_path()),
            "cfurl_cache_path": str(self._cfurl_cache_path()),
            "available": self.is_configured(),
            "unavailable_reason": self.unavailable_reason(),
            "recent_manifest_keys": self._recent_manifest_keys(limit=limit),
            "candidate_payloads": [],
        }

        for candidate in self._iter_payload_candidates():
            if related_only and not self._looks_trade_or_position_related(candidate):
                continue
            payload_summary = {
                "source": candidate.source,
                "key": candidate.key,
                "priority": candidate.priority,
                "trade_rows": len(self._extract_trade_rows(candidate)),
                "position_rows": len(self._extract_position_rows(candidate)),
                "payload_shape": self._summarize_payload_shape(candidate.payload),
            }
            summary["candidate_payloads"].append(payload_summary)

        return summary

    def _has_candidate_sources(self) -> bool:
        if self._manifest_path().exists():
            return True
        if self._cfurl_cache_path().exists():
            return True
        return any(self._iter_candidate_files())

    def _iter_payload_candidates(self) -> list[PayloadCandidate]:
        candidates: list[PayloadCandidate] = []
        candidates.extend(self._iter_xcs_trade_file_payloads())
        candidates.extend(self._iter_manifest_cache_payloads())
        candidates.extend(self._iter_cfurl_cache_payloads())
        candidates.extend(self._iter_file_payloads())
        return sorted(candidates, key=lambda item: item.priority)

    def _iter_xcs_trade_file_payloads(self) -> list[PayloadCandidate]:
        xcs_dir = self.container_path / "Data/Documents/XcsFold"
        if not xcs_dir.exists():
            return []

        candidates: list[PayloadCandidate] = []
        for path in sorted(xcs_dir.glob("XcsLscjDataFile_*"), key=lambda item: item.stat().st_mtime, reverse=True):
            payload = self._load_json(path.read_bytes())
            if not isinstance(payload, dict):
                continue
            candidates.append(
                PayloadCandidate(
                    source="xcs_trade_file",
                    key=str(path),
                    payload=payload,
                    priority=-1,
                )
            )
        return candidates

    def _recent_manifest_keys(self, limit: int) -> list[str]:
        path = self._manifest_path()
        if not path.exists():
            return []
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute(
                "select key from manifest order by last_access_time desc limit ?",
                (int(limit),),
            ).fetchall()
        finally:
            conn.close()
        return [str(key) for (key,) in rows]

    def _iter_manifest_cache_payloads(self) -> list[PayloadCandidate]:
        path = self._manifest_path()
        if not path.exists():
            return []

        candidates: list[PayloadCandidate] = []
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute(
                "select key, filename, inline_data from manifest order by last_access_time desc"
            ).fetchall()
        finally:
            conn.close()

        for key, filename, inline_data in rows:
            blob = bytes(inline_data or b"")
            if filename:
                file_path = self._resolve_manifest_data_file(path.parent / "data", filename)
                if file_path is not None and file_path.exists():
                    blob = file_path.read_bytes()
            payload = self._deserialize_blob(blob)
            if payload is None:
                continue
            candidates.append(
                PayloadCandidate(
                    source="manifest_cache",
                    key=str(key),
                    payload=payload,
                    priority=0,
                )
            )
        return candidates

    def _iter_cfurl_cache_payloads(self) -> list[PayloadCandidate]:
        path = self._cfurl_cache_path()
        if not path.exists():
            return []

        candidates: list[PayloadCandidate] = []
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute(
                """
                select r.request_key, d.receiver_data
                from cfurl_cache_response as r
                join cfurl_cache_receiver_data as d on r.entry_ID = d.entry_ID
                order by r.time_stamp desc
                """
            ).fetchall()
        finally:
            conn.close()

        for key, blob in rows:
            normalized_blob = blob if isinstance(blob, (bytes, bytearray)) else str(blob or "").encode("utf-8")
            payload = self._deserialize_blob(bytes(normalized_blob))
            if payload is None:
                payload = self._load_cfurl_fs_cached_payload(path.parent / "fsCachedData", normalized_blob)
            if payload is None:
                continue
            candidates.append(
                PayloadCandidate(
                    source="cfurl_cache",
                    key=str(key),
                    payload=payload,
                    priority=1,
                )
            )
        return candidates

    def _iter_file_payloads(self) -> list[PayloadCandidate]:
        candidates: list[PayloadCandidate] = []
        for path in self._iter_candidate_files():
            payload = self._deserialize_blob(path.read_bytes(), allow_text=True)
            if payload is None:
                continue
            candidates.append(
                PayloadCandidate(
                    source="file",
                    key=str(path),
                    payload=payload,
                    priority=2,
                )
            )
        return candidates

    def _iter_candidate_files(self):
        seen: set[Path] = set()
        for pattern in self.file_globs:
            for path in self.container_path.glob(pattern):
                if path.is_file() and path not in seen:
                    seen.add(path)
                    yield path

    def _deserialize_blob(self, blob: bytes, allow_text: bool = False) -> Any:
        if not blob:
            return None

        for loader in (self._load_keyed_archive, self._load_plist, self._load_json):
            payload = loader(blob)
            if payload is not None:
                return payload

        if allow_text:
            return self._extract_json_from_text(blob)
        return None

    def _load_keyed_archive(self, blob: bytes) -> Any:
        try:
            raw = plistlib.loads(blob)
        except Exception:
            return None
        if not isinstance(raw, dict) or raw.get("$archiver") != "NSKeyedArchiver":
            return None
        return NSKeyedArchiveDecoder(raw).decode()

    def _load_plist(self, blob: bytes) -> Any:
        try:
            return plistlib.loads(blob)
        except Exception:
            return None

    def _load_json(self, blob: bytes) -> Any:
        try:
            return json.loads(blob.decode("utf-8"))
        except Exception:
            return None

    def _load_cfurl_fs_cached_payload(self, fs_cache_dir: Path, token_blob: bytes) -> Any:
        token = token_blob.decode("utf-8", errors="ignore").strip()
        if not token:
            return None
        if len(token) > 128 or any(marker in token for marker in ("<", ">", "<?xml", "{", "[")):
            return {"_cfurl_inline_text_preview": token[:4000]}
        path = fs_cache_dir / token
        if not path.exists():
            return None

        file_blob = path.read_bytes()
        for loader in (self._load_keyed_archive, self._load_plist, self._load_json):
            payload = loader(file_blob)
            if payload is not None:
                return payload

        text = file_blob.decode("utf-8", errors="ignore")
        if text:
            return {
                "_cfurl_fs_cached_token": token,
                "_cfurl_fs_cached_text_preview": text[:4000],
            }
        return None

    def _extract_json_from_text(self, blob: bytes) -> Any:
        text = blob.decode("utf-8", errors="ignore")
        for match in re.finditer(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL):
            candidate = match.group(1).strip()
            try:
                return json.loads(candidate)
            except Exception:
                continue
        return None

    def _extract_trade_rows(self, candidate: PayloadCandidate) -> list[dict]:
        payload = candidate.payload
        key_lower = candidate.key.lower()
        if candidate.source == "xcs_trade_file":
            return self._extract_trade_rows_from_xcs_file(payload)
        if isinstance(payload, dict) and "today_order" in key_lower:
            return [self._normalize_trade_aliases(row) for row in self._coerce_row_list(payload.get("data"), kind="trade")]
        return [self._normalize_trade_aliases(row) for row in self._scan_payload_for_rows(payload, kind="trade")]

    def _extract_position_rows(self, candidate: PayloadCandidate) -> list[dict]:
        payload = candidate.payload
        key_lower = candidate.key.lower()
        if isinstance(payload, dict) and any(
            token in key_lower for token in ("position", "holding", "asset", "balance")
        ):
            return [self._normalize_position_aliases(row) for row in self._coerce_row_list(payload.get("data"), kind="position")]
        return [self._normalize_position_aliases(row) for row in self._scan_payload_for_rows(payload, kind="position")]

    def _scan_payload_for_rows(self, payload: Any, kind: str) -> list[dict]:
        matches: list[dict] = []
        if isinstance(payload, list):
            rows = self._coerce_row_list(payload, kind=kind)
            if rows:
                matches.extend(rows)
            for item in payload:
                matches.extend(self._scan_payload_for_rows(item, kind=kind))
            return matches

        if isinstance(payload, dict):
            for value in payload.values():
                matches.extend(self._scan_payload_for_rows(value, kind=kind))
        return matches

    def _coerce_row_list(self, value: Any, kind: str) -> list[dict]:
        if not isinstance(value, list):
            return []
        rows = [item for item in value if isinstance(item, dict)]
        if not rows:
            return []
        looks_like = self._looks_like_trade_row if kind == "trade" else self._looks_like_position_row
        return [item for item in rows if looks_like(item)]

    def _looks_like_trade_row(self, row: dict) -> bool:
        keys = {str(key) for key in row}
        required_key_sets = (
            {"stock_code", "stock_name"},
            {"证券代码", "证券名称"},
        )
        time_keys = {"business_time", "trade_time", "成交时间", "成交日期", "business_date", "deal_time"}
        quantity_keys = {"business_amount", "amount", "成交数量", "成交股数", "quantity", "deal_amount"}
        price_keys = {"business_price", "business_avg_price", "price", "成交价格", "成交均价", "deal_price"}
        direction_keys = {"entrust_bs", "operation", "操作", "买卖标志", "direction", "business_name"}

        return (
            any(required <= keys for required in required_key_sets)
            and bool(keys & time_keys)
            and bool(keys & quantity_keys)
            and bool(keys & price_keys)
            and bool(keys & direction_keys)
        )

    def _looks_like_position_row(self, row: dict) -> bool:
        keys = {str(key) for key in row}
        required_key_sets = (
            {"stock_code", "stock_name"},
            {"证券代码", "证券名称"},
        )
        quantity_keys = {"current_amount", "quantity", "当前数量", "当前拥股数", "股份余额", "持仓数量"}
        cost_keys = {"cost_price", "price", "weighted_avg_cost", "成本价", "摊薄成本价"}

        return any(required <= keys for required in required_key_sets) and bool(keys & quantity_keys) and bool(
            keys & cost_keys
        )

    def _dedupe_trades(self, rows: list[dict]) -> list[dict]:
        deduped: list[dict] = []
        seen = set()
        for row in rows:
            key = (
                row["stock_code"],
                row["direction"],
                int(row["quantity"]),
                row["trade_time"].isoformat(),
                str(row["price"]),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    def _extract_trade_rows_from_xcs_file(self, payload: dict[str, Any]) -> list[dict]:
        rows: list[dict] = []
        for stock_code, trade_dates in payload.items():
            if stock_code in {"startdate", "enddate"} or not isinstance(trade_dates, dict):
                continue
            for trade_date, trade_rows in trade_dates.items():
                if not isinstance(trade_rows, list):
                    continue
                for row in trade_rows:
                    if not isinstance(row, dict):
                        continue
                    normalized = dict(row)
                    normalized.setdefault("stock_code", row.get("zqdm", stock_code))
                    normalized.setdefault("stock_name", row.get("zqmc", ""))
                    normalized.setdefault("business_price", row.get("cjjg"))
                    normalized.setdefault("business_amount", row.get("cjsl"))
                    normalized.setdefault("operation", row.get("czmc"))
                    if row.get("cjrq") and row.get("cjsj"):
                        normalized.setdefault(
                            "business_time",
                            f"{row['cjrq'][:4]}-{row['cjrq'][4:6]}-{row['cjrq'][6:8]}T{row['cjsj']}",
                        )
                    rows.append(normalized)
        return rows

    def _reconstruct_positions_from_trade_file(self, payload: dict[str, Any]) -> list[dict]:
        positions: dict[str, dict[str, Any]] = {}
        for row in sorted(
            self._extract_trade_rows_from_xcs_file(payload),
            key=lambda item: item["business_time"],
        ):
            stock_code = str(row.get("stock_code", "")).strip().upper()
            if not stock_code:
                continue
            quantity = int(Decimal(str(row["business_amount"])))
            price = Decimal(str(row["business_price"]))
            direction = str(row.get("operation") or row.get("czmc") or "").strip()
            position = positions.setdefault(
                stock_code,
                {
                    "stock_code": stock_code,
                    "stock_name": str(row.get("stock_name") or stock_code).strip() or stock_code,
                    "market": "上海" if stock_code.startswith(("5", "6", "9")) else "深圳",
                    "quantity": 0,
                    "cost_price": Decimal("0"),
                    "weighted_avg_cost": Decimal("0"),
                    "total_invested": Decimal("0"),
                    "realized_pnl": Decimal("0"),
                    "status": "CLEARED",
                },
            )

            if "买" in direction:
                current_qty = int(position["quantity"])
                current_cost = Decimal(str(position["weighted_avg_cost"]))
                new_qty = current_qty + quantity
                total_cost = current_cost * Decimal(current_qty) + price * Decimal(quantity)
                position["quantity"] = new_qty
                position["weighted_avg_cost"] = (total_cost / Decimal(new_qty)) if new_qty > 0 else Decimal("0")
            elif "卖" in direction:
                position["quantity"] = max(0, int(position["quantity"]) - quantity)

            current_qty = int(position["quantity"])
            weighted = Decimal(str(position["weighted_avg_cost"]))
            position["cost_price"] = weighted
            position["total_invested"] = weighted * Decimal(current_qty)
            position["status"] = "ACTIVE" if current_qty > 0 else "CLEARED"

        return [item for item in positions.values() if int(item["quantity"]) > 0]

    def _dedupe_positions(self, rows: list[dict]) -> list[dict]:
        latest_by_code: dict[tuple[str, str], dict] = {}
        for row in rows:
            key = (row["stock_code"], row["market"])
            latest_by_code[key] = row
        return list(latest_by_code.values())

    def _looks_trade_or_position_related(self, candidate: PayloadCandidate) -> bool:
        key = candidate.key.lower()
        if any(token in key for token in ("order", "trade", "position", "holding", "asset", "balance", "deal")):
            return True
        text = json.dumps(candidate.payload, ensure_ascii=False, default=str)
        return any(
            token in text
            for token in (
                "stock_code",
                "证券代码",
                "当前拥股数",
                "成交时间",
                "成交数量",
                "持仓",
                "成交",
                "资金",
            )
        )

    def _summarize_payload_shape(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            summary: dict[str, Any] = {
                "type": "dict",
                "keys": list(payload.keys())[:20],
            }
            data = payload.get("data")
            if isinstance(data, list):
                summary["data_length"] = len(data)
                if data and isinstance(data[0], dict):
                    summary["data_keys"] = list(data[0].keys())[:20]
            return summary
        if isinstance(payload, list):
            summary = {
                "type": "list",
                "length": len(payload),
            }
            if payload and isinstance(payload[0], dict):
                summary["item_keys"] = list(payload[0].keys())[:20]
            return summary
        return {"type": type(payload).__name__}

    @staticmethod
    def _normalize_trade_aliases(row: dict) -> dict:
        normalized = dict(row)
        alias_pairs = (
            ("操作", "operation"),
            ("成交均价", "business_avg_price"),
            ("成交价格", "business_price"),
            ("成交数量", "business_amount"),
            ("成交时间", "business_time"),
            ("证券代码", "stock_code"),
            ("证券名称", "stock_name"),
            ("买卖标志", "entrust_bs"),
        )
        for source, target in alias_pairs:
            if source in normalized and target not in normalized:
                normalized[target] = normalized[source]
        return normalized

    @staticmethod
    def _normalize_position_aliases(row: dict) -> dict:
        normalized = dict(row)
        alias_pairs = (
            ("证券代码", "stock_code"),
            ("证券名称", "stock_name"),
            ("当前拥股数", "current_amount"),
            ("当前数量", "current_amount"),
            ("股份余额", "current_amount"),
            ("成本价", "cost_price"),
            ("摊薄成本价", "cost_price"),
            ("交易市场", "market"),
        )
        for source, target in alias_pairs:
            if source in normalized and target not in normalized:
                normalized[target] = normalized[source]
        return normalized

    def _is_app_running(self) -> bool:
        checker = self.app_running_checker
        if callable(checker):
            return bool(checker())

        process_patterns = [
            str(self.app_path / "Contents/MacOS/同花顺"),
            "cn.com.10jqka.macstock",
            "同花顺",
        ]
        for pattern in process_patterns:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True,
                check=False,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        return False

    def _manifest_path(self) -> Path:
        return self.container_path / "Data/Library/Caches/kPPNetworkResponseCache/manifest.sqlite"

    def _cfurl_cache_path(self) -> Path:
        return self.container_path / "Data/Library/Caches/cn.com.10jqka.macstock/Cache.db"

    @staticmethod
    def _resolve_path(value: Any, default: Path) -> Path:
        if not value:
            return default
        return Path(str(value)).expanduser()

    @classmethod
    def _resolve_globs(cls, raw_value: Any) -> tuple[str, ...]:
        if isinstance(raw_value, (list, tuple)):
            values = [str(item).strip() for item in raw_value if str(item).strip()]
            return tuple(values) or cls.DEFAULT_FILE_GLOBS
        text = str(raw_value or "").strip()
        if not text:
            return cls.DEFAULT_FILE_GLOBS
        return tuple(part.strip() for part in text.split(",") if part.strip())

    @staticmethod
    def _resolve_bool(config_value: Any, env_value: str) -> bool:
        if isinstance(config_value, bool):
            return config_value
        if config_value in (None, ""):
            return str(env_value).strip().lower() == "true"
        return str(config_value).strip().lower() == "true"

    @staticmethod
    def _resolve_manifest_data_file(data_dir: Path, filename: str) -> Path | None:
        direct_path = data_dir / filename
        if direct_path.exists():
            return direct_path

        nested_path = data_dir / filename[:2] / filename
        if nested_path.exists():
            return nested_path
        return None
