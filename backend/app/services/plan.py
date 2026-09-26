"""养护计划业务规则：状态流转、字段校验、时段去重都收在这里。

状态流转（批复流程保持不变，驳回/作废后回到可继续编制的档位）：

    待编制 ──提交审批──▶ 待审批 ──确认批复──▶ 已批复
      ▲                    │
      └──── 驳回 ◀─────────┘   （已驳回可带着原金额与工期修改后重新提交）

    待编制 / 待审批 / 已驳回 ──作废计划──▶ 已作废（同样可照原内容重新编制、提交）
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.store import store

MODULE = "plan"

# 登记时就要有的基础字段；金额与工期允许先存草稿，提交审批前必须补齐。
BASE_FIELDS = ["计划编号", "养护类型", "养护对象"]
OPTIONAL_FIELDS = ["计划工期", "预算金额", "编制人员"]
EDITABLE_FIELDS = BASE_FIELDS + OPTIONAL_FIELDS
SUBMIT_REQUIRED_FIELDS = BASE_FIELDS + ["计划工期", "预算金额"]

STATUS_DRAFT = "待编制"
STATUS_PENDING = "待审批"
STATUS_APPROVED = "已批复"
STATUS_REJECTED = "已驳回"
STATUS_VOID = "已作废"
FLOW_STATUSES = [STATUS_DRAFT, STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_VOID]
# 只有这三档允许重新打开表单继续改。
EDITABLE_STATUSES = [STATUS_DRAFT, STATUS_REJECTED, STATUS_VOID]
# 作废的计划不参与时段去重，同一对象允许重新立项。
ACTIVE_STATUSES = [STATUS_DRAFT, STATUS_PENDING, STATUS_REJECTED, STATUS_APPROVED]

# 2026-03-01~2026-04-30，兼容 ~ ～ - — – 至 到 等写法。
PERIOD_RE = re.compile(r"(\d{4}-\d{1,2}-\d{1,2})\s*[~～\-—–至到]\s*(\d{4}-\d{1,2}-\d{1,2})")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_period(value: Any) -> tuple[date, date] | None:
    """把工期文本解析成起止日期；识别不了时返回 None，交调用方决定口径。"""
    match = PERIOD_RE.search(_text(value))
    if not match:
        return None
    try:
        start = date.fromisoformat(match.group(1))
        end = date.fromisoformat(match.group(2))
    except ValueError:
        return None
    return start, end


def normalize_period(value: Any) -> str:
    """统一落成 2026-03-01~2026-04-30 的形式；无法解析的保留原文。"""
    parsed = parse_period(value)
    if parsed is None:
        return _text(value)
    start, end = parsed
    return f"{start.isoformat()}~{end.isoformat()}"


def normalize_amount(value: Any) -> tuple[Any, str | None]:
    """预算金额尽量落成两位小数的数字；空值归一成 None，非法值附带错误说明。"""
    text = _text(value)
    if not text:
        return None, None
    try:
        amount = float(text)
    except ValueError:
        return value, "预算金额需要是数字"
    if amount < 0:
        return value, "预算金额不能为负数"
    return round(amount, 2), None


class PlanService:
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
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, str | None]:
        """登记新计划。返回 (记录, 说明, 回执代码)；记录为 None 表示被拦下。"""
        missing = [field for field in BASE_FIELDS if not _text(values.get(field))]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}", "MISSING_FIELDS"

        data, error = self._normalize(values)
        if error:
            return None, error, "INVALID_FIELD"

        rows = store.rows(MODULE)
        conflict = self._find_conflict(rows, data["养护对象"], data["计划工期"], exclude_id=-1)
        if conflict is not None:
            return None, self._conflict_message(conflict), "DUPLICATE_PLAN"

        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in EDITABLE_FIELDS:
            entry[field] = data.get(field)
        entry["审批人员"] = None
        entry["status"] = STATUS_DRAFT
        entry["计划状态"] = STATUS_DRAFT
        entry["pending"] = True
        entry["abnormal"] = False
        entry["last_reject_reason"] = None
        rows.append(entry)
        return entry, "养护计划已登记，可继续补充预算金额与计划工期", None

    def update_entry(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str, str | None]:
        """继续编制：驳回/作废后重新打开表单保存时走这里，原金额与工期都留在记录上。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"养护计划 {entry_id} 不存在或已归档", "NOT_FOUND"
        status = str(entry.get("status") or "")
        if status not in EDITABLE_STATUSES:
            return (
                None,
                f"当前状态「{status}」不允许编辑，仅待编制、已驳回、已作废的计划可继续编制",
                "INVALID_STATUS",
            )

        missing = [field for field in BASE_FIELDS if not _text(values.get(field))]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}", "MISSING_FIELDS"

        data, error = self._normalize(values)
        if error:
            return None, error, "INVALID_FIELD"

        conflict = self._find_conflict(
            store.rows(MODULE), data["养护对象"], data["计划工期"], exclude_id=entry_id
        )
        if conflict is not None:
            return None, self._conflict_message(conflict), "DUPLICATE_PLAN"

        # 状态保持不变：驳回/作废后改完仍是原档位，需要再点一次「提交审批」才回流。
        for field in EDITABLE_FIELDS:
            entry[field] = data.get(field)
        return entry, "养护计划内容已保存", None

    def run_action(
        self, entry_id: int, action: str, remark: str | None = None
    ) -> tuple[dict[str, Any] | None, str, str | None]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"养护计划 {entry_id} 不存在或已归档", "NOT_FOUND"

        status = str(entry.get("status") or "")
        if action == "提交审批":
            return self._submit_for_approval(entry, status)
        if action == "驳回":
            if status != STATUS_PENDING:
                return self._invalid_status(status, action, "只有待审批的计划可以驳回")
            entry["status"] = STATUS_REJECTED
            entry["计划状态"] = STATUS_REJECTED
            entry["pending"] = True
            entry["abnormal"] = True
            entry["last_reject_reason"] = _text(remark) or None
            return entry, "养护计划已驳回，可带着原金额与工期继续修改后重新提交", None
        if action == "确认批复":
            if status != STATUS_PENDING:
                return self._invalid_status(status, action, "只有待审批的计划可以确认批复")
            entry["status"] = STATUS_APPROVED
            entry["计划状态"] = STATUS_APPROVED
            entry["pending"] = False
            entry["abnormal"] = False
            return entry, "养护计划已确认批复", None
        if action == "作废计划":
            if status not in (STATUS_DRAFT, STATUS_PENDING, STATUS_REJECTED):
                return self._invalid_status(status, action, "当前状态的计划不允许作废")
            entry["status"] = STATUS_VOID
            entry["计划状态"] = STATUS_VOID
            entry["pending"] = False
            entry["abnormal"] = True
            return entry, "养护计划已作废，原填报内容已保留，可重新打开继续编制", None
        return None, f"动作「{action}」不属于养护计划可执行范围", "INVALID_ACTION"

    # ---- 内部辅助 -------------------------------------------------------

    def _submit_for_approval(
        self, entry: dict[str, Any], status: str
    ) -> tuple[dict[str, Any] | None, str, str | None]:
        if status not in EDITABLE_STATUSES:
            return self._invalid_status(status, "提交审批", "当前状态的计划不能再次提交审批")

        missing = [field for field in SUBMIT_REQUIRED_FIELDS if not _text(entry.get(field))]
        if missing:
            # 明确告诉填报人卡在哪一头，不许空着金额或工期走到批复。
            return None, f"提交审批被拦住，还缺：{'、'.join(missing)}，请补齐后再提交", "MISSING_FIELDS"

        _, amount_error = normalize_amount(entry.get("预算金额"))
        if amount_error:
            return None, f"提交审批被拦住：{amount_error}", "INVALID_FIELD"

        period = parse_period(entry.get("计划工期"))
        if period is None:
            return (
                None,
                "提交审批被拦住：计划工期需写成 2026-03-01~2026-04-30 这样的起止日期",
                "INVALID_FIELD",
            )
        start, end = period
        if start > end:
            return None, "提交审批被拦住：开工日期不能晚于完工日期", "INVALID_FIELD"

        conflict = self._find_conflict(
            store.rows(MODULE),
            _text(entry.get("养护对象")),
            _text(entry.get("计划工期")),
            exclude_id=int(entry.get("id", 0)),
        )
        if conflict is not None:
            return None, self._conflict_message(conflict), "DUPLICATE_PLAN"

        entry["status"] = STATUS_PENDING
        entry["计划状态"] = STATUS_PENDING
        entry["pending"] = True
        entry["abnormal"] = False
        entry["last_reject_reason"] = None
        return entry, "养护计划已提交审批，等待批复", None

    @staticmethod
    def _invalid_status(
        status: str, action: str, reason: str
    ) -> tuple[dict[str, Any] | None, str, str | None]:
        return None, f"当前状态「{status}」不允许执行「{action}」：{reason}", "INVALID_STATUS"

    @staticmethod
    def _normalize(values: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        data: dict[str, Any] = {}
        for field in BASE_FIELDS + ["编制人员"]:
            data[field] = _text(values.get(field))
        data["计划工期"] = normalize_period(values.get("计划工期"))
        amount, error = normalize_amount(values.get("预算金额"))
        data["预算金额"] = amount
        return data, error

    @staticmethod
    def _find_conflict(
        rows: list[dict[str, Any]], target_object: str, period_text: str, exclude_id: int
    ) -> dict[str, Any] | None:
        """同一养护对象 + 工期区间重叠即视为重复；作废的计划不占位。"""
        target = _text(target_object)
        if not target:
            return None
        target_period = parse_period(period_text)
        raw_period = _text(period_text)
        for row in rows:
            if int(row.get("id", 0)) == exclude_id:
                continue
            if row.get("status") == STATUS_VOID:
                continue
            if _text(row.get("养护对象")) != target:
                continue
            other_period = parse_period(row.get("计划工期"))
            if target_period and other_period:
                start, end = target_period
                other_start, other_end = other_period
                if start <= other_end and other_start <= end:
                    return row
            elif (
                not target_period
                and not other_period
                and raw_period
                and raw_period == _text(row.get("计划工期"))
            ):
                # 双方工期都不是可识别的日期区间时，退化为相同时段文本去重。
                return row
        return None

    @staticmethod
    def _conflict_message(row: dict[str, Any]) -> str:
        period = _text(row.get("计划工期")) or "同一时段"
        return (
            f"重复提交被拦截：养护对象「{_text(row.get('养护对象'))}」在 {period} 内"
            f"已存在计划 {_text(row.get('计划编号'))}（状态：{row.get('status')}），"
            f"同一养护对象在同一时间段只保留一条计划"
        )
