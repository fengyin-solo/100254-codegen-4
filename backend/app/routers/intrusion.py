"""沿线侵限台账接口：按里程/区间定位、按位置合并、剔除位置不完整条目。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, IntrusionLedgerResult
from app.services.intrusion import IntrusionService

router = APIRouter(prefix="/api/intrusion", tags=["沿线侵限"])

service = IntrusionService()

LIST_FIELDS = ["台账编号", "所属区间", "里程", "侧别", "外部干扰源", "干扰类型", "侵限尺寸", "发现日期", "现场描述"]
STATUSES = ["待处理", "处理中", "已处理"]


@router.get("", response_model=IntrusionLedgerResult)
def list_entries(
    keyword: str | None = Query(default=None, description="按干扰源/编号/描述关键字检索"),
    status: str | None = Query(default=None, description="待处理、处理中、已处理"),
    section: str | None = Query(default=None, description="区间号或区间名，如 QJ03、K33"),
    mileage: str | None = Query(default=None, description="里程定位，如 K33+200，配合 radius 取临近区段"),
    radius: int = Query(default=500, ge=50, le=5000, description="定位半径（米），50-5000"),
    mileage_from: str | None = Query(default=None, description="里程区间起点，如 K30+000"),
    mileage_to: str | None = Query(default=None, description="里程区间终点，如 K36+000"),
    page: int = 1,
    size: int = 20,
) -> IntrusionLedgerResult:
    """按里程与区间过滤临近管辖区段的侵限条目。

    位置不完整的条目不参与过滤，但会在 excluded_items 里逐条写明原因；
    范围外的待处理条目同样带出（out_of_scope=true），避免换了里程范围就漏办。
    """
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    result = service.list_entries(
        keyword=keyword,
        status=status,
        section=section,
        mileage_from=mileage_from,
        mileage_to=mileage_to,
        anchor_mileage=mileage,
        radius=radius,
        page=page,
        size=size,
    )
    return IntrusionLedgerResult(**result)


@router.get("/export")
def export_entries(
    section: str | None = None,
    mileage: str | None = None,
    radius: int = 500,
    mileage_from: str | None = None,
    mileage_to: str | None = None,
) -> dict[str, Any]:
    """导出当前定位条件下的侵限台账（含剔除清单）。"""
    result = service.list_entries(
        section=section,
        mileage_from=mileage_from,
        mileage_to=mileage_to,
        anchor_mileage=mileage,
        radius=radius,
        page=1,
        size=10000,
    )
    return {"module": "intrusion", "total": result["total"], "items": result["items"],
            "excluded_items": result["excluded_items"], "warnings": result["warnings"]}


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict[str, Any]:
    """读取单条侵限明细及其合并组；不存在时给出可读的错误说明。"""
    result = service.get_entry(entry_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"侵限台账 {entry_id} 不存在或已归档")
    return result


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条外部干扰源侵限；位置字段缺失或里程格式不对时直接说明原因。"""
    entry, missing, invalid = service.create_entry(payload.values)
    if missing or invalid:
        messages = []
        if missing:
            messages.append(f"缺少必填字段：{'、'.join(missing)}")
        messages.extend(invalid)
        return ActionResult(ok=False, message="；".join(messages))
    return ActionResult(ok=True, message="侵限条目已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条侵限条目执行接单核查、处理完成；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
