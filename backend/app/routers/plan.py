"""养护计划接口：维护养护计划，覆盖登记、继续编制、提交审批、驳回、确认批复、作废等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.plan import (
    FLOW_STATUSES,
    PlanService,
)

router = APIRouter(prefix="/api/plan", tags=["养护计划"])

service = PlanService()

LIST_FIELDS = ["计划编号", "养护类型", "养护对象", "计划工期", "预算金额", "编制人员", "审批人员", "计划状态"]
STATUSES = FLOW_STATUSES


# 注意：/export 必须放在 /{entry_id} 之前，否则会被单条明细路由吞成 entry_id="export"。
@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出养护计划清单：返回当前全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "plan", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按计划编号检索"),
    status: str | None = Query(default=None, description="待编制、待审批、已批复、已驳回、已作废"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按计划编号与状态过滤养护计划列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条养护计划明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"养护计划 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条养护计划，缺字段、时段重复时说明原因并给出回执代码，而不是静默丢弃。"""
    entry, message, code = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message, code=code)
    return ActionResult(ok=True, message=message, entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """继续编制：驳回或作废后重新打开表单，保存预算金额、计划工期等修改。"""
    entry, message, code = service.update_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message, code=code)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """执行提交审批、驳回、确认批复、作废计划；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message, code = service.run_action(entry_id, action, payload.remark)
    if entry is None:
        return ActionResult(ok=False, message=message, code=code)
    return ActionResult(ok=True, message=message, entry=entry)
