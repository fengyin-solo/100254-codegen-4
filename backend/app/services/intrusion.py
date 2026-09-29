"""沿线侵限台账业务规则。

口径说明（对应现场诉求）：
- 定位：支持按里程（K30+250 形式或纯数字）、里程区间、区间号过滤；
- 合并：同一外部干扰源在同一里程重复登记的，按位置合并成一条展示，原始记录仍可查；
- 剔除：所属区间或里程缺失、里程无法识别的条目不参与定位与合并，但在结果里逐条列明原因；
- 对账：台账总数 = 有效原始条数 + 剔除条数，合并只压缩展示、不丢数据；
- 范围外待处理：只要还没处理完，即使不在本次里程/区间范围内也一并带出并标注，防止漏办。
"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "intrusion"
REQUIRED_FIELDS = ["台账编号", "所属区间", "里程", "外部干扰源"]
STATUS_ORDER = ["待处理", "处理中", "已处理"]
ACTION_RULES = {"接单核查": "处理中", "处理完成": "已处理"}
NEGATIVE_ACTIONS: list[str] = []

# 里程只认 K30+250 / k30+250 / 30+250 / 30250 这几种完整写法；
# “约K38公里”这类口语化记录无法定位，按位置不完整剔除。
MILEAGE_RE = re.compile(r"^\s*[Kk]?(\d+)(?:\+(\d{1,3}))?\s*$")

FIELD_ORDER = [
    "台账编号", "所属区间", "里程", "侧别", "外部干扰源",
    "干扰类型", "侵限尺寸", "发现日期", "现场描述",
]


def parse_mileage(value: Any) -> int | None:
    """把里程值换算成米；无法识别时返回 None，由调用方决定剔除还是告警。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = MILEAGE_RE.match(text)
    if not match:
        return None
    km = int(match.group(1))
    meters = int(match.group(2) or 0)
    if meters >= 1000:
        return None
    return km * 1000 + meters


def canonical_mileage(total_meters: int) -> str:
    return f"K{total_meters // 1000}+{total_meters % 1000:03d}"


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


class IntrusionService:
    # ---- 数据分层：有效 / 剔除 ---------------------------------------------

    def _classify(
        self, rows: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """位置完整才能参与定位；剔除项带上逐条原因，绝不静默丢弃。"""
        valid: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for row in rows:
            section = str(row.get("所属区间") or "").strip()
            raw_mileage = str(row.get("里程") or "").strip()
            reasons: list[str] = []
            if not section:
                reasons.append("所属区间缺失")
            if not raw_mileage:
                reasons.append("里程缺失")
            elif parse_mileage(raw_mileage) is None:
                reasons.append(f"里程「{raw_mileage}」无法识别（应为 K30+250 形式）")
            if reasons:
                item = {key: row.get(key) for key in FIELD_ORDER}
                item["id"] = row.get("id")
                item["status"] = row.get("status")
                item["exclude_reasons"] = reasons
                excluded.append(item)
            else:
                item = dict(row)
                item["_mileage"] = parse_mileage(raw_mileage)
                valid.append(item)
        return valid, excluded

    def _merge(self, valid: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """同一外部干扰源 + 同一里程视为重复登记，按位置合并，保留全部成员。"""
        buckets: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for row in sorted(valid, key=lambda r: int(r.get("id", 0))):
            key = (int(row["_mileage"]), normalize_text(row.get("外部干扰源")))
            buckets.setdefault(key, []).append(row)

        groups: list[dict[str, Any]] = []
        for members in buckets.values():
            primary = dict(members[0])
            indices = [
                STATUS_ORDER.index(str(m.get("status")))
                for m in members
                if m.get("status") in STATUS_ORDER
            ]
            primary["status"] = STATUS_ORDER[min(indices, default=0)]
            primary["pending"] = any(m.get("pending") for m in members)
            primary["member_ids"] = [m.get("id") for m in members]
            primary["merged_from"] = [str(m.get("台账编号") or m.get("id")) for m in members]
            primary["merged_count"] = len(members) - 1
            primary["members"] = [self._public_row(m) for m in members]
            groups.append(primary)
        groups.sort(key=lambda g: int(g.get("id", 0)))
        return groups

    @staticmethod
    def _public_row(row: dict[str, Any]) -> dict[str, Any]:
        item = {key: row.get(key) for key in FIELD_ORDER}
        item["id"] = row.get("id")
        item["status"] = row.get("status")
        item["pending"] = row.get("pending")
        item["abnormal"] = row.get("abnormal")
        return item

    # ---- 列表查询 -----------------------------------------------------------

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        section: str | None = None,
        mileage_from: str | None = None,
        mileage_to: str | None = None,
        anchor_mileage: str | None = None,
        radius: int = 500,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        rows = store.rows(MODULE)
        total = len(rows)
        valid, excluded = self._classify(rows)
        groups = self._merge(valid)

        warnings: list[str] = []
        lo = hi = None
        # 显式里程区间优先；没给时再用“里程定位 + 半径”。
        if mileage_from or mileage_to:
            start = parse_mileage(mileage_from) if mileage_from else None
            end = parse_mileage(mileage_to) if mileage_to else None
            if mileage_from and start is None:
                warnings.append(f"起点里程「{mileage_from}」无法识别（示例：K30+000），该条件未生效")
            if mileage_to and end is None:
                warnings.append(f"终点里程「{mileage_to}」无法识别（示例：K36+000），该条件未生效")
            if start is not None and end is not None and start > end:
                warnings.append("起点里程大于终点里程，里程区间条件未生效")
            else:
                lo, hi = start, end
        elif anchor_mileage:
            anchor = parse_mileage(anchor_mileage)
            if anchor is None:
                warnings.append(
                    f"里程定位「{anchor_mileage}」无法识别（示例：K30+250），定位条件未生效"
                )
            else:
                radius = max(50, min(int(radius), 5000))
                lo, hi = anchor - radius, anchor + radius

        section_key = normalize_text(section)
        scope_active = lo is not None or hi is not None or bool(section_key)

        def in_scope(group: dict[str, Any]) -> bool:
            mileage = int(group["_mileage"])
            if section_key and section_key in normalize_text(group.get("所属区间")):
                return True
            if lo is not None and hi is not None and lo <= mileage <= hi:
                return True
            return False

        kw = (keyword or "").strip()
        out_scope_pending = 0
        filtered: list[dict[str, Any]] = []
        for group in groups:
            if kw and not any(
                kw in str(group.get(field) or "")
                for field in ("台账编号", "外部干扰源", "现场描述", "干扰类型")
            ):
                continue
            if status and group.get("status") != status:
                continue
            if scope_active and not in_scope(group):
                # 还没处理完的外部干扰源不能因为换了里程范围就查不到。
                if group.get("pending"):
                    group["out_of_scope"] = True
                    out_scope_pending += 1
                else:
                    continue
            filtered.append(group)

        start_index = max(page - 1, 0) * size
        page_items = [self._public_group(g) for g in filtered[start_index:start_index + size]]
        valid_count = len(valid)
        excluded_count = len(excluded)
        return {
            "items": page_items,
            "total": total,
            "page": page,
            "size": size,
            "filtered_total": len(filtered),
            "valid_count": valid_count,
            "kept_count": len(groups),
            "merged_count": sum(int(g["merged_count"]) for g in groups),
            "excluded_count": excluded_count,
            "excluded_items": excluded,
            "out_scope_pending": out_scope_pending,
            "reconciled": valid_count + excluded_count == total,
            "filters_applied": {
                "section": section or None,
                "mileage_from": mileage_from or None,
                "mileage_to": mileage_to or None,
                "anchor_mileage": anchor_mileage or None,
                "radius": radius if anchor_mileage and lo is not None else None,
                "status": status or None,
                "keyword": kw or None,
                "scope_lower": canonical_mileage(max(lo, 0)) if lo is not None else None,
                "scope_upper": canonical_mileage(hi) if hi is not None else None,
            },
            "warnings": warnings,
        }

    def _public_group(self, group: dict[str, Any]) -> dict[str, Any]:
        item = self._public_row(group)
        item["mileage_value"] = group.get("_mileage")
        item["mileage_label"] = canonical_mileage(int(group["_mileage"]))
        item["member_ids"] = group.get("member_ids", [])
        item["merged_from"] = group.get("merged_from", [])
        item["merged_count"] = group.get("merged_count", 0)
        item["members"] = group.get("members", [])
        item["out_of_scope"] = group.get("out_of_scope", False)
        return item

    # ---- 单条详情 -----------------------------------------------------------

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        valid, _excluded = self._classify(store.rows(MODULE))
        groups = self._merge(valid)
        for group in groups:
            if entry_id in [int(mid) for mid in group.get("member_ids", [])]:
                return {
                    "entry": self._public_row(row),
                    "group": {
                        "representative_id": group.get("id"),
                        "member_ids": group.get("member_ids"),
                        "merged_from": group.get("merged_from"),
                        "merged_count": group.get("merged_count"),
                        "mileage_label": canonical_mileage(int(group["_mileage"])),
                        "members": group.get("members"),
                    },
                }
        # 位置不完整、被剔除的条目也允许从台账直接点进去查看。
        return {"entry": self._public_row(row), "group": None}

    # ---- 登记与流转 ---------------------------------------------------------

    def create_entry(
        self, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str], list[str]]:
        missing = [f for f in REQUIRED_FIELDS if not str(values.get(f) or "").strip()]
        invalid: list[str] = []
        if not missing and parse_mileage(values.get("里程")) is None:
            invalid.append(f"里程「{values.get('里程')}」无法识别（应为 K30+250 形式）")
        if missing or invalid:
            return None, missing, invalid
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(r.get("id", 0)) for r in rows), default=0) + 1}
        entry.update({f: values.get(f) for f in FIELD_ORDER})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = True
        rows.append(entry)
        return entry, [], []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"侵限台账 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于沿线侵限可执行范围"
        target = ACTION_RULES[action]
        # 同一外部干扰源重复登记的条目按位置合并，动作对整组生效；
        # 匹配口径必须和 _merge 完全一致（里程 + 干扰源 + 区间均有效且相同）。
        affected = [entry]
        mileage = parse_mileage(entry.get("里程"))
        source_key = normalize_text(entry.get("外部干扰源"))
        section_key = normalize_text(entry.get("所属区间"))
        if mileage is not None and source_key and section_key:
            for other in store.rows(MODULE):
                if int(other.get("id", 0)) == entry_id:
                    continue
                if (
                    parse_mileage(other.get("里程")) == mileage
                    and normalize_text(other.get("外部干扰源")) == source_key
                    and normalize_text(other.get("所属区间")) == section_key
                ):
                    affected.append(other)
        for item in affected:
            item["status"] = target
            item["pending"] = target != STATUS_ORDER[-1]
            item["abnormal"] = action in NEGATIVE_ACTIONS or item["pending"]
        note = f"，同位置重复登记的 {len(affected) - 1} 条已一并流转" if len(affected) > 1 else ""
        return entry, f"侵限条目已{action}{note}"
