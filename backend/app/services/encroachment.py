"""沿线侵限台账业务规则：里程定位、重复干扰源合并与位置数据剔除。"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "encroachment"
REQUIRED_LOCATION_FIELDS = ["区间号", "起始里程", "结束里程", "管辖区段"]
DEFAULT_PROXIMITY = 500
MAX_PROXIMITY = 5000


def _text(row: dict[str, Any], field: str) -> str:
    return str(row.get(field) or "").strip()


def parse_mileage(value: str | float | int | None) -> float | None:
    """把 K12+100、12+100、12100 统一换算成米，无法识别时返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().upper().replace("－", "-").replace("—", "-")
    if not text:
        return None
    match = re.fullmatch(r"K?\s*(\d+)\s*\+\s*(\d{1,3})", text)
    if match:
        return int(match.group(1)) * 1000 + int(match.group(2))
    match = re.fullmatch(r"K?\s*(\d+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1))
    return None



def normalize_section(value: str | None) -> str:
    return re.sub(r"[\s\-_－—]+", "", str(value or "").upper())


class EncroachmentService:
    def list_entries(
        self,
        *,
        mileage: str | None = None,
        start_mileage: str | None = None,
        end_mileage: str | None = None,
        section: str | None = None,
        proximity: int | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[dict[str, Any], list[str]]:
        errors: list[str] = []
        point = parse_mileage(mileage) if mileage else None
        start = parse_mileage(start_mileage) if start_mileage else None
        end = parse_mileage(end_mileage) if end_mileage else None

        if mileage and point is None:
            errors.append("里程条件格式无效，未生效，请使用 K12+100 或 12+100")
        if start_mileage and start is None:
            errors.append("起始里程条件格式无效，未生效")
        if end_mileage and end is None:
            errors.append("结束里程条件格式无效，未生效")
        if start is not None and end is not None and start > end:
            errors.append("里程范围条件无效，未生效：起始里程不能大于结束里程")
            start, end = None, None

        proximity_value = 0
        has_proximity_input = proximity is not None
        if has_proximity_input:
            if proximity < 0 or proximity > MAX_PROXIMITY:
                errors.append(f"临近距离条件无效，未生效：请输入 0-{MAX_PROXIMITY} 米")
            else:
                proximity_value = proximity
        elif point is not None:
            proximity_value = DEFAULT_PROXIMITY

        if errors:
            return {}, errors

        rows = store.rows(MODULE)
        valid_rows: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for row in rows:
            missing = [field for field in REQUIRED_LOCATION_FIELDS if not _text(row, field)]
            start_value = parse_mileage(row.get("起始里程")) if not missing else None
            end_value = parse_mileage(row.get("结束里程")) if not missing else None
            invalid_mileage = (
                not missing
                and (start_value is None or end_value is None or start_value > end_value)
            )
            if missing or invalid_mileage:
                reasons = [f"缺少{field}" for field in missing]
                if not missing:
                    if start_value is None:
                        reasons.append("起始里程无法识别")
                    if end_value is None:
                        reasons.append("结束里程无法识别")
                    if start_value is not None and end_value is not None and start_value > end_value:
                        reasons.append("起始里程大于结束里程")
                excluded.append({
                    "id": row.get("id"),
                    "侵限编号": _text(row, "侵限编号") or f"未编号/{row.get('id')}",
                    "外部干扰源": _text(row, "外部干扰源") or "未填写外部干扰源",
                    "区间号": _text(row, "区间号"),
                    "起始里程": _text(row, "起始里程"),
                    "结束里程": _text(row, "结束里程"),
                    "管辖区段": _text(row, "管辖区段"),
                    "missing_fields": missing,
                    "reason": "、".join(reasons),
                })
                continue
            item = dict(row)
            item["_start_m"] = start_value
            item["_end_m"] = end_value
            valid_rows.append(item)

        groups = self._merge_by_location(valid_rows)
        section_query = normalize_section(section) if section else ""
        has_mileage_filter = point is not None or start is not None or end is not None
        has_location_filter = has_mileage_filter or bool(section_query)

        filtered: list[dict[str, Any]] = []
        retained_pending_count = 0
        for group in groups:
            if not has_location_filter:
                group["match_type"] = "all"
                group["match_reason"] = "未使用定位条件，显示位置完整的全部台账"
                group["distance_m"] = None
                filtered.append(group)
                continue
            matched, reason, distance = self._match_location(
                group,
                point=point,
                start=start,
                end=end,
                section_query=section_query,
                proximity=proximity_value,
            )
            if matched:
                group["match_type"] = "location"
                group["match_reason"] = reason
                group["distance_m"] = distance
                filtered.append(group)
            elif has_location_filter and group["pending"]:
                retained = dict(group)
                retained["match_type"] = "pending_retained"
                retained["match_reason"] = "待处理外部干扰源：当前里程/区间定位条件外仍保留"
                retained["distance_m"] = None
                filtered.append(retained)
                retained_pending_count += 1

        if point is not None:
            filtered.sort(key=lambda item: (
                item["match_type"] != "location",
                item["distance_m"] if item["distance_m"] is not None else 10**12,
                item["_start_m"],
                item["id"],
            ))
        else:
            filtered.sort(key=lambda item: (item["match_type"] != "location", item["_start_m"], item["id"]))

        total = len(filtered)
        start_index = max(page - 1, 0) * size
        page_items = [self._public_item(item) for item in filtered[start_index:start_index + size]]

        ledger_total = len(rows)
        valid_total = len(valid_rows)
        grouped_total = len(groups)
        merged_count = valid_total - grouped_total
        excluded_total = len(excluded)
        result = {
            "items": page_items,
            "total": total,
            "page": page,
            "size": size,
            "ledger_total": ledger_total,
            "valid_total": valid_total,
            "grouped_total": grouped_total,
            "merged_count": merged_count,
            "excluded_total": excluded_total,
            "retained_pending_count": retained_pending_count,
            "excluded": excluded,
            "applied_conditions": {
                "mileage": mileage or None,
                "point_m": point,
                "start_mileage": start_mileage or None,
                "end_mileage": end_mileage or None,
                "range_start_m": start,
                "range_end_m": end,
                "section": section or None,
                "proximity_m": proximity_value if has_location_filter else None,
                "has_location_filter": has_location_filter,
            },
            "balance": {
                "ledger_total": ledger_total,
                "grouped_total": grouped_total,
                "merged_count": merged_count,
                "excluded_total": excluded_total,
                "reconciled_total": grouped_total + merged_count + excluded_total,
                "matches": grouped_total + merged_count + excluded_total == ledger_total,
            },
        }
        return result, []

    def get_group(self, entry_id: int) -> dict[str, Any] | None:
        rows = store.rows(MODULE)
        if store.find(MODULE, entry_id) is None:
            return None
        valid_rows: list[dict[str, Any]] = []
        for row in rows:
            parsed = self._validated_row(row)
            if parsed is not None:
                valid_rows.append(parsed)
        for group in self._merge_by_location(valid_rows):
            if entry_id in group["source_ids"]:
                result = self._public_item(group)
                result["source_entries"] = [
                    {key: value for key, value in entry.items() if not key.startswith("_")}
                    for entry in group["source_entries"]
                ]
                return result
        return None

    def _validated_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        if any(not _text(row, field) for field in REQUIRED_LOCATION_FIELDS):
            return None
        start = parse_mileage(row.get("起始里程"))
        end = parse_mileage(row.get("结束里程"))
        if start is None or end is None or start > end:
            return None
        item = dict(row)
        item["_start_m"] = start
        item["_end_m"] = end
        return item

    def _merge_by_location(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in sorted(rows, key=lambda item: int(item.get("id", 0))):
            source = _text(row, "外部干扰源") or f"未命名干扰源/{row.get('id')}"
            key = (
                source,
                normalize_section(_text(row, "区间号")),
                row["_start_m"],
                row["_end_m"],
                _text(row, "管辖区段"),
            )
            if key not in merged:
                merged[key] = {
                    "id": row.get("id"),
                    "group_key": "|".join(str(part) for part in key),
                    "source_ids": [int(row.get("id", 0))],
                    "source_entries": [row],
                    "侵限编号": _text(row, "侵限编号"),
                    "外部干扰源": source,
                    "区间号": _text(row, "区间号"),
                    "管辖区段": _text(row, "管辖区段"),
                    "起始里程": _text(row, "起始里程"),
                    "结束里程": _text(row, "结束里程"),
                    "_start_m": row["_start_m"],
                    "_end_m": row["_end_m"],
                    "侵限类型": _text(row, "侵限类型"),
                    "最早发现日期": _text(row, "发现日期"),
                    "最晚发现日期": _text(row, "发现日期"),
                    "处置期限": _text(row, "处置期限"),
                    "status": _text(row, "status") or "未处理",
                    "pending": bool(row.get("pending")),
                    "abnormal": bool(row.get("abnormal")),
                }
                continue
            group = merged[key]
            group["source_ids"].append(int(row.get("id", 0)))
            group["source_entries"].append(row)
            group["pending"] = group["pending"] or bool(row.get("pending"))
            group["abnormal"] = group["abnormal"] or bool(row.get("abnormal"))
            group["status"] = self._aggregate_status(group["source_entries"])
            discovered = [value for value in [group.get("最早发现日期"), _text(row, "发现日期")] if value]
            group["最早发现日期"] = min(discovered, default="")
            group["最晚发现日期"] = max(discovered, default="")
        groups = list(merged.values())
        for group in groups:
            count = len(group["source_ids"])
            group["merged_record_count"] = count
            group["merged_ids"] = list(group["source_ids"])
            group["登记次数"] = count
            if count > 1:
                numbers = [_text(row, "侵限编号") for row in group["source_entries"]]
                group["侵限编号"] = f"{numbers[0]} 等 {count} 条"
        return sorted(groups, key=lambda item: (item["_start_m"], item["id"]))

    def _aggregate_status(self, entries: list[dict[str, Any]]) -> str:
        statuses = [_text(entry, "status") for entry in entries]
        if any(status == "未处理" for status in statuses):
            return "未处理"
        if any(status == "处理中" for status in statuses):
            return "处理中"
        return "已处理"

    def _match_location(
        self,
        group: dict[str, Any],
        *,
        point: float | None,
        start: float | None,
        end: float | None,
        section_query: str,
        proximity: int,
    ) -> tuple[bool, str, int | None]:
        reasons: list[str] = []
        distance: int | None = None
        mileage_checks: list[bool] = []
        section_matched = True
        if point is not None:
            point_matched = False
            if group["_start_m"] <= point <= group["_end_m"]:
                point_matched = True
                distance = 0
                reasons.append("里程位于侵限范围内")
            else:
                raw_distance = group["_start_m"] - point if point < group["_start_m"] else point - group["_end_m"]
                distance = int(raw_distance)
                if distance <= proximity:
                    point_matched = True
                    reasons.append(f"距查询里程 {distance} 米，在 {proximity} 米临近范围内")
            mileage_checks.append(point_matched)
        if start is not None or end is not None:
            range_matched = False
            range_start = start if start is not None else float("-inf")
            range_end = end if end is not None else float("inf")
            if group["_start_m"] <= range_end and group["_end_m"] >= range_start:
                range_matched = True
                reasons.append("与查询里程区间相交")
            mileage_checks.append(range_matched)
        if section_query:
            section_matched = False
            section_value = normalize_section(group.get("区间号"))
            jurisdiction = str(group.get("管辖区段") or "")
            if section_value == section_query or section_query in section_value or section_query in normalize_section(jurisdiction):
                section_matched = True
                reasons.append("区间号或管辖区段匹配")
        matched = all(mileage_checks) and section_matched
        return matched, "；".join(reasons) if matched else "", distance

    def _public_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in item.items() if not key.startswith("_")}
