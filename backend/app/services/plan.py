"""养护计划业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "plan"
FORM_FIELDS = ["计划编号", "养护类型", "养护对象", "计划工期", "预算金额", "编制人员", "审批人员"]
REQUIRED_FIELDS = ["计划编号", "养护类型", "养护对象"]
SUBMIT_REQUIRED_FIELDS = ["预算金额", "计划工期"]
STATUS_ORDER = ["待编制", "待审批", "已批复", "已驳回", "已作废"]
ACTION_RULES = {
    "提交审批": "待审批",
    "确认批复": "已批复",
    "驳回计划": "已驳回",
    "作废计划": "已作废",
    "恢复重编": "待编制",
}
ACTION_SOURCES = {
    "提交审批": ["待编制", "已驳回"],
    "确认批复": ["待审批"],
    "驳回计划": ["待审批"],
    "作废计划": ["待编制", "待审批", "已驳回"],
    "恢复重编": ["已作废"],
}
ACTION_MESSAGES = {
    "提交审批": "养护计划已提交审批",
    "确认批复": "养护计划已批复",
    "驳回计划": "养护计划已驳回，已填写的预算金额与计划工期保留，可修改后重新提交",
    "作废计划": "养护计划已作废，重新打开表单可恢复重编，已填写内容不会丢失",
    "恢复重编": "养护计划已恢复为待编制，原预算金额与计划工期已保留",
}
NEGATIVE_ACTIONS = ["作废计划", "驳回计划"]
EDITABLE_STATUSES = ["待编制", "已驳回", "已作废"]
DUPLICATE_CODE = "PLAN_DUPLICATED"


def _is_blank(value: Any) -> bool:
    return not str(value or "").strip()


class PlanService:
    def _sync_status_label(self, row: dict[str, Any]) -> dict[str, Any]:
        """让「计划状态」字段始终跟随真实状态，列表、详情、导出读到的才是同一回事。"""
        row["计划状态"] = str(row.get("status") or STATUS_ORDER[0])
        return row

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("计划编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._sync_status_label(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._sync_status_label(entry)

    def _find_duplicate(self, values: dict[str, Any], exclude_id: int | None = None) -> dict[str, Any] | None:
        """同一养护对象在同一计划工期只允许保留一条未作废的计划。"""
        target_object = str(values.get("养护对象") or "").strip()
        target_period = str(values.get("计划工期") or "").strip()
        if not target_object or not target_period:
            return None
        for row in store.rows(MODULE):
            if exclude_id is not None and int(row.get("id", 0)) == exclude_id:
                continue
            if row.get("status") == "已作废":
                continue
            if (
                str(row.get("养护对象") or "").strip() == target_object
                and str(row.get("计划工期") or "").strip() == target_period
            ):
                return row
        return None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], str, str]:
        missing = [field for field in REQUIRED_FIELDS if _is_blank(values.get(field))]
        if missing:
            return None, missing, "", ""
        duplicate = self._find_duplicate(values)
        if duplicate is not None:
            receipt = (
                f"重复提交已合并：养护对象「{duplicate.get('养护对象')}」在计划工期"
                f"「{duplicate.get('计划工期')}」下已存在计划 {duplicate.get('计划编号')}"
                f"（当前状态：{duplicate.get('status')}），本次未重复登记"
            )
            return self._sync_status_label(duplicate), [], receipt, DUPLICATE_CODE
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in FORM_FIELDS:
            entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._sync_status_label(entry), [], "养护计划已登记", ""

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """驳回或作废后重新打开表单继续修改：已填写的金额与工期保留，作废的保存后恢复为待编制。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"养护计划 {entry_id} 不存在或已归档"
        status = str(entry.get("status") or STATUS_ORDER[0])
        if status not in EDITABLE_STATUSES:
            return None, f"当前状态「{status}」不允许修改，请先驳回或恢复重编"
        merged = {field: values.get(field, entry.get(field)) for field in FORM_FIELDS}
        missing = [field for field in REQUIRED_FIELDS if _is_blank(merged.get(field))]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        duplicate = self._find_duplicate(merged, exclude_id=entry_id)
        if duplicate is not None:
            return None, (
                f"养护对象「{duplicate.get('养护对象')}」在计划工期「{duplicate.get('计划工期')}」"
                f"下已存在计划 {duplicate.get('计划编号')}，请调整后再保存"
            )
        for field in FORM_FIELDS:
            entry[field] = merged[field]
        if status == "已作废":
            entry["status"] = STATUS_ORDER[0]
            entry["pending"] = True
            entry["abnormal"] = False
            return self._sync_status_label(entry), "养护计划已保存并恢复为待编制，原预算金额与计划工期已保留"
        return self._sync_status_label(entry), "养护计划已保存，预算金额与计划工期已保留"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"养护计划 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于养护计划可执行范围"
        current = str(entry.get("status") or STATUS_ORDER[0])
        if current not in ACTION_SOURCES[action]:
            return None, f"当前状态「{current}」不能执行「{action}」"
        if action == "提交审批":
            missing = [field for field in SUBMIT_REQUIRED_FIELDS if _is_blank(entry.get(field))]
            if missing:
                return None, f"提交审批前请先补齐：{'、'.join(missing)}"
        target = ACTION_RULES[action]
        entry["status"] = target
        entry["pending"] = target not in ("已批复", "已作废")
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return self._sync_status_label(entry), ACTION_MESSAGES[action]
