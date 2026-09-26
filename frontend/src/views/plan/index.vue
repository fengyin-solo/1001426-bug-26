<template>
  <section class="page" data-module="plan">
    <header class="page-head">
      <div>
        <h2>养护计划管理</h2>
        <p class="page-desc">维护养护计划，围绕计划编号、养护类型、养护对象、计划工期做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记养护计划</button>
        <button class="btn" type="button" @click="exportRows">导出养护计划清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column.key">{{ column.label }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody v-if="loadFailed">
        <tr>
          <td :colspan="columns.length + 1">
            <EmptyState title="养护计划列表读取失败" :description="errorMessage" @retry="reload" />
          </td>
        </tr>
      </tbody>
      <tbody v-else>
        <tr v-for="row in visibleRows" :key="String(row.id)">
          <td v-for="column in columns" :key="column.key">{{ row[column.key] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button v-if="isEditable(row)" class="link" type="button" @click="openEdit(row)">编辑</button>
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!visibleRows.length">
          <td :colspan="columns.length + 1">
            <EmptyState title="暂无养护计划数据" description="可先登记养护计划" :retryable="false" />
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条养护计划记录</span>
      <span v-if="errorMessage && !loadFailed" class="error-text">{{ errorMessage }}</span>
    </footer>

    <aside v-if="detailVisible" class="detail-panel">
      <header class="detail-head">
        <h3>养护计划详情</h3>
        <button class="link" type="button" @click="closeDetail">关闭</button>
      </header>
      <EmptyState
        v-if="detailError"
        title="养护计划详情读取失败"
        :description="detailError"
        @retry="loadDetail"
      />
      <dl v-else-if="detail" class="detail-list">
        <div v-for="field in columns" :key="field.key" class="detail-item">
          <dt>{{ field.label }}</dt>
          <dd>{{ detail[field.key] ?? '—' }}</dd>
        </div>
      </dl>
      <p v-else class="detail-loading">正在读取…</p>
    </aside>

    <div v-if="formVisible" class="dialog-mask">
      <div class="dialog">
        <h3>{{ editingId === null ? '登记养护计划' : '修改养护计划' }}</h3>
        <p v-if="editingStatus" class="dialog-hint">
          当前状态：{{ editingStatus }}。已填写的预算金额与计划工期保留在表单里，可在此基础上继续修改。
        </p>
        <form @submit.prevent="submitForm">
          <label v-for="field in formFields" :key="field.key" class="dialog-field">
            <span>{{ field.label }}<em v-if="field.required" class="required-mark">*</em></span>
            <input
              v-model="form[field.key]"
              :type="field.type ?? 'text'"
              :step="field.type === 'number' ? '0.01' : undefined"
              :placeholder="field.placeholder ?? `请输入${field.label}`"
            />
          </label>
          <p v-if="formError" class="error-text">{{ formError }}</p>
          <footer class="dialog-foot">
            <button class="btn ghost" type="button" @click="closeForm">取消</button>
            <button class="btn primary" type="submit">保存</button>
          </footer>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import EmptyState from '@/components/EmptyState.vue'

type Row = Record<string, string | number | null>
type FormField = {
  key: string
  label: string
  required?: boolean
  type?: string
  placeholder?: string
}

const ENDPOINT = '/api/plan'
const columns = [
  { label: '计划编号', key: '计划编号' },
  { label: '养护类型', key: '养护类型' },
  { label: '养护对象', key: '养护对象' },
  { label: '计划工期', key: '计划工期' },
  { label: '预算金额', key: '预算金额' },
  { label: '编制人员', key: '编制人员' },
  { label: '审批人员', key: '审批人员' },
  { label: '计划状态', key: 'status' },
]
const formFields: FormField[] = [
  { key: '计划编号', label: '计划编号', required: true },
  { key: '养护类型', label: '养护类型', required: true },
  { key: '养护对象', label: '养护对象', required: true },
  { key: '计划工期', label: '计划工期', placeholder: '如 2026-10-01 至 2026-10-31' },
  { key: '预算金额', label: '预算金额（万元）', type: 'number' },
  { key: '编制人员', label: '编制人员' },
  { key: '审批人员', label: '审批人员' },
]
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  待编制: ['提交审批', '作废计划'],
  待审批: ['确认批复', '驳回计划'],
  已驳回: ['提交审批', '作废计划'],
  已作废: ['恢复重编'],
  已批复: [],
}
const EDITABLE_STATUSES = ['待编制', '已驳回', '已作废']
const SUBMIT_REQUIRED_FIELDS = ['预算金额', '计划工期']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const loadFailed = ref(false)
const filters = ref<Record<string, string>>({})
const filterFields = ['计划编号', '养护类型', '养护对象']

const stats = computed(() => [
  { label: '待审批计划', value: rows.value.filter((row) => row.status === '待审批').length },
  { label: '已批复计划', value: rows.value.filter((row) => row.status === '已批复').length },
  {
    label: '计划预算合计（万元）',
    value: rows.value.reduce((sum, row) => sum + (Number(row['预算金额']) || 0), 0).toFixed(1),
  },
])

const visibleRows = computed(() => {
  const typeFilter = (filters.value['养护类型'] ?? '').trim()
  const objectFilter = (filters.value['养护对象'] ?? '').trim()
  return rows.value.filter((row) => {
    if (typeFilter && !String(row['养护类型'] ?? '').includes(typeFilter)) return false
    if (objectFilter && !String(row['养护对象'] ?? '').includes(objectFilter)) return false
    return true
  })
})

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function actionsFor(row: Row): string[] {
  return ACTIONS_BY_STATUS[String(row.status ?? '')] ?? []
}

function isEditable(row: Row): boolean {
  return EDITABLE_STATUSES.includes(String(row.status ?? ''))
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  if (action === '提交审批') {
    const missing = SUBMIT_REQUIRED_FIELDS.filter((field) => !String(row[field] ?? '').trim())
    if (missing.length) {
      errorMessage.value = `提交审批前请先补齐：${missing.join('、')}（点击「编辑」补录后再提交）`
      return
    }
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await response.json()
    if (!response.ok || !result.ok) {
      throw new Error(result?.message ?? result?.detail ?? '养护计划动作未生效，请稍后重试')
    }
    await reload()
    noticeMessage.value = result.message ?? `养护计划已${action}`
    if (detailVisible.value && detail.value && detail.value.id === row.id) {
      await loadDetail()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '养护计划操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  noticeMessage.value = ''
  loadFailed.value = false
  const query = new URLSearchParams()
  const keyword = (filters.value['计划编号'] ?? '').trim()
  if (keyword) {
    query.set('keyword', keyword)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('养护计划列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    rows.value = []
    total.value = 0
    loadFailed.value = true
    errorMessage.value = error instanceof Error ? error.message : '养护计划列表读取失败'
  }
}

const detailVisible = ref(false)
const detail = ref<Row | null>(null)
const detailError = ref('')
const detailId = ref<number | null>(null)

function openDetail(row: Row) {
  detailVisible.value = true
  detailId.value = Number(row.id)
  void loadDetail()
}

function closeDetail() {
  detailVisible.value = false
  detail.value = null
  detailError.value = ''
  detailId.value = null
}

async function loadDetail() {
  if (detailId.value === null) return
  detail.value = null
  detailError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${detailId.value}`)
    if (!response.ok) {
      throw new Error('养护计划详情读取失败')
    }
    detail.value = (await response.json()) as Row
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : '养护计划详情读取失败'
  }
}

const formVisible = ref(false)
const editingId = ref<number | null>(null)
const editingStatus = ref('')
const formError = ref('')
const form = reactive<Record<string, string>>({})

function resetForm(values?: Row) {
  for (const field of formFields) {
    const value = values?.[field.key]
    form[field.key] = value === null || value === undefined ? '' : String(value)
  }
}

function openCreate() {
  editingId.value = null
  editingStatus.value = ''
  formError.value = ''
  noticeMessage.value = ''
  resetForm()
  formVisible.value = true
}

function openEdit(row: Row) {
  editingId.value = Number(row.id)
  editingStatus.value = String(row.status ?? '')
  formError.value = ''
  noticeMessage.value = ''
  resetForm(row)
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
  editingId.value = null
  editingStatus.value = ''
  formError.value = ''
}

async function submitForm() {
  formError.value = ''
  const missing = formFields
    .filter((field) => field.required && !String(form[field.key] ?? '').trim())
    .map((field) => field.label)
  if (missing.length) {
    formError.value = `请先补齐：${missing.join('、')}`
    return
  }
  const values: Row = {}
  for (const field of formFields) {
    const raw = String(form[field.key] ?? '').trim()
    if (field.type === 'number') {
      values[field.key] = raw === '' ? null : Number(raw)
    } else {
      values[field.key] = raw === '' ? null : raw
    }
  }
  const isEdit = editingId.value !== null
  try {
    const response = await request(isEdit ? `${ENDPOINT}/${editingId.value}` : ENDPOINT, {
      method: isEdit ? 'PUT' : 'POST',
      body: JSON.stringify({ values }),
    })
    const result = await response.json()
    if (!response.ok || !result.ok) {
      throw new Error(result?.message ?? result?.detail ?? '养护计划保存失败')
    }
    const duplicatedEntry = result.code === 'PLAN_DUPLICATED' ? (result.entry as Row | null) : null
    closeForm()
    await reload()
    noticeMessage.value = result.message ?? '养护计划已保存'
    if (duplicatedEntry) {
      openDetail(duplicatedEntry)
    }
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '养护计划保存失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.notice-text {
  margin: 0 0 8px;
  font-size: 13px;
  color: #067647;
}
.detail-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 320px;
  padding: 16px;
  background: #fff;
  border-left: 1px solid var(--border);
  box-shadow: -4px 0 12px rgba(15, 23, 42, 0.08);
  overflow-y: auto;
  z-index: 20;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.detail-head h3 {
  margin: 0;
  font-size: 15px;
}
.detail-list {
  margin: 0;
}
.detail-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--border);
  font-size: 13px;
}
.detail-item dt {
  color: var(--muted);
}
.detail-item dd {
  margin: 0;
  text-align: right;
}
.detail-loading {
  color: var(--muted);
  font-size: 13px;
}
.dialog-mask {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.35);
  z-index: 30;
}
.dialog {
  width: 420px;
  max-width: calc(100vw - 32px);
  padding: 16px 20px;
  background: #fff;
  border-radius: 8px;
}
.dialog h3 {
  margin: 0 0 8px;
  font-size: 15px;
}
.dialog-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--muted);
}
.dialog-field {
  display: block;
  margin-bottom: 10px;
}
.dialog-field span {
  display: block;
  margin-bottom: 2px;
  font-size: 12px;
  color: var(--muted);
}
.dialog-field input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}
.required-mark {
  margin-left: 2px;
  color: #b42318;
  font-style: normal;
}
.dialog-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
</style>
