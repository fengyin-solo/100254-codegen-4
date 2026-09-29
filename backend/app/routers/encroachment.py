"""沿线侵限台账接口：支持里程、区间定位、位置剔除与同位置干扰源合并。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import EncroachmentPage
from app.services.encroachment import MAX_PROXIMITY, EncroachmentService

router = APIRouter(prefix="/api/encroachment", tags=["沿线侵限台账"])
service = EncroachmentService()


@router.get("", response_model=EncroachmentPage)
def list_entries(
    mileage: str | None = Query(default=None, description="单点里程，例如 K12+100；默认向两侧临近 500 米"),
    start_mileage: str | None = Query(default=None, description="里程区间起点"),
    end_mileage: str | None = Query(default=None, description="里程区间终点"),
    section: str | None = Query(default=None, description="区间号或管辖区段关键字"),
    proximity: int | None = Query(default=None, description=f"单点里程两侧临近范围，0-{MAX_PROXIMITY} 米"),
    page: int = 1,
    size: int = 20,
) -> EncroachmentPage:
    """按里程或区间定位侵限；条件无效时明确说明哪个条件未生效。"""
    if page < 1:
        raise HTTPException(status_code=400, detail="页码不能小于 1")
    if size < 1 or size > 200:
        raise HTTPException(status_code=400, detail="每页条数需在 1-200 之间")
    result, errors = service.list_entries(
        mileage=mileage,
        start_mileage=start_mileage,
        end_mileage=end_mileage,
        section=section,
        proximity=proximity,
        page=page,
        size=size,
    )
    if errors:
        raise HTTPException(status_code=400, detail="；".join(errors))
    return EncroachmentPage(**result)


@router.get("/groups/{entry_id}", response_model=dict)
def get_group(entry_id: int) -> dict:
    """读取合并后的侵限位置明细，包含同一外部干扰源下的全部登记记录。"""
    group = service.get_group(entry_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f"侵限位置 {entry_id} 不存在，或该记录因位置信息不完整已被剔除")
    return group
