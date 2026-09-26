<template>
  <section class="page" data-module="plan">
    <header class="page-head">
      <div>
        <h2>养护计划管理</h2>
        <p class="page-desc">维护养护计划，覆盖登记编制、提交审批、驳回修改、确认批复与作废重编，预算金额与计划工期会一路保留。</p>
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
      <label class="filter-item">
        <span>计划编号</span>
        <input v-model="keyword" placeholder="按计划编号检索" />
      </label>
      <label class="filter-item">
        <span>计划状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="listError" class="banner error" role="alert">
      <span>{{ listError }}</span>
      <button class="btn small" type="button" @click="reload">重试</button>
    </p>
    <p v-else-if="listInfo" class="banner success">{{ listInfo }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '计划状态'" class="status-badge" :data-status="row.status">{{ row[column] ?? '—' }}</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEntry(row)">
              {{ canEdit(row) ? '继续编制' : '查看详情' }}
            </button>
            <template v-if="canEdit(row)">
              <button class="link" type="button" @click="quickAction('提交审批', row)">提交审批</button>
              <button class="link danger" type="button" @click="quickAction('作废计划', row)">作废计划</button>
            </template>
            <template v-else-if="row.status === '待审批'">
              <button class="link" type="button" @click="quickAction('驳回', row)">驳回</button>
              <button class="link" type="button" @click="quickAction('确认批复', row)">确认批复</button>
            </template>
          </td>
        </tr>
        <FeedbackState
          :colspan="columns.length + 1"
          :loading="listLoading"
          :error="listError"
          :empty="!rows.length"
          empty-text="暂无养护计划数据，可先登记养护计划"
          @retry="reload"
        >
          <button class="btn primary small" type="button" @click="openCreate">登记养护计划</button>
        </FeedbackState>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条养护计划记录</span>
      <span v-if="listLoading" class="muted-text">加载中…</span>
    </footer>

    <div v-if="modalOpen" class="modal-mask" @click.self="closeModal">
      <section class="modal" role="dialog" aria-modal="true" aria-label="养护计划表单">
        <header class="modal-head">
          <h3>{{ modalTitle }}</h3>
          <button class="modal-close" type="button" aria-label="关闭" @click="closeModal">×</button>
        </header>

        <div v-if="detailLoading" class="modal-feedback">
          <p class="muted-text">计划详情加载中…</p>
        </div>
        <div v-else-if="detailError" class="modal-feedback">
          <p class="banner error"><span>{{ detailError }}</span></p>
          <button class="btn" type="button" @click="loadDetail(modalId!)">重试</button>
        </div>

        <template v-else>
          <p v-if="modalMode !== 'create'" class="banner" :class="entryStatus === '已驳回' ? 'warn' : 'info'">
            当前状态：<strong>{{ entryStatus }}</strong>
            <template v-if="entryStatus === '已驳回'">
              ，表单已回到驳回前的编制档，原预算金额与计划工期已带出，改完请重新提交审批。
            </template>
            <template v-else-if="entryStatus === '已作废'">
              ，原填报内容已保留，可在此基础上修改后重新提交审批。
            </template>
          </p>
          <p v-if="form.last_reject_reason" class="banner warn">
            上次驳回意见：{{ form.last_reject_reason }}
          </p>
          <p v-if="formError" class="banner error" role="alert">
            {{ formError }}
          </p>
          <p v-else-if="formInfo" class="banner success">{{ formInfo }}</p>

          <ol class="step-bar">
            <li
              v-for="(step, index) in steps"
              :key="step.key"
              class="step-item"
              :class="{ active: modalMode === 'view' ? true : stepIndex === index, done: modalMode !== 'view' && stepIndex > index }"
            >
              <span class="step-no">{{ index + 1 }}</span>
              <span class="step-label">{{ step.label }}</span>
            </li>
          </ol>

          <form class="plan-form" @submit.prevent>
            <fieldset :disabled="readonly || formSaving">
              <div v-show="modalMode === 'view' || stepIndex === 0" class="form-grid">
                <label class="form-item">
                  <span>计划编号 <em>*</em></span>
                  <input v-model="form['计划编号']" placeholder="如 PLAN-2026-006" />
                </label>
                <label class="form-item">
                  <span>养护类型 <em>*</em></span>
                  <select v-model="form['养护类型']">
                    <option value="">请选择</option>
                    <option v-for="type in planTypes" :key="type" :value="type">{{ type }}</option>
                  </select>
                </label>
                <label class="form-item">
                  <span>养护对象 <em>*</em></span>
                  <input v-model="form['养护对象']" placeholder="如 海河大桥" />
                </label>
                <label class="form-item">
                  <span>编制人员</span>
                  <input v-model="form['编制人员']" placeholder="填报人姓名" />
                </label>
              </div>

              <div v-show="modalMode === 'view' || stepIndex === 1" class="form-grid">
                <label class="form-item">
                  <span>计划工期（开工 ~ 完工）<em>*</em></span>
                  <span class="date-range">
                    <input v-model="periodStart" type="date" />
                    <span class="date-sep">至</span>
                    <input v-model="periodEnd" type="date" />
                  </span>
                  <small v-if="periodRaw" class="field-hint">原工期文本「{{ periodRaw }}」无法识别为日期区间，请重新选择起止日期。</small>
                </label>
                <label class="form-item">
                  <span>预算金额（元）<em>*</em></span>
                  <input v-model="amountInput" type="number" min="0" step="0.01" placeholder="如 500000" />
                </label>
                <label class="form-item">
                  <span>审批人员</span>
                  <input :value="form['审批人员'] ?? '批复后由审批人填写'" disabled />
                </label>
              </div>
            </fieldset>
          </form>

          <footer class="modal-foot">
            <button class="btn ghost" type="button" @click="closeModal">{{ readonly ? '关闭' : '取消' }}</button>
            <template v-if="!readonly">
              <template v-if="stepIndex === 0">
                <button class="btn primary" type="button" :disabled="formSaving" @click="goStep(1)">
                  下一步：金额与工期
                </button>
              </template>
              <template v-else>
                <button class="btn" type="button" :disabled="formSaving" @click="goStep(0)">上一步</button>
                <button class="btn" type="button" :disabled="formSaving" @click="saveDraft">暂存内容</button>
                <button class="btn primary" type="button" :disabled="formSaving" @click="saveAndSubmit">
                  {{ formSaving ? '提交中…' : '保存并提交审批' }}
                </button>
              </template>
            </template>
          </footer>
        </template>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import FeedbackState from '@/components/FeedbackState.vue'
import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

interface PlanForm {
  计划编号: string
  养护类型: string
  养护对象: string
  编制人员: string
  审批人员: string | null
  计划工期: string
  预算金额: string
  last_reject_reason: string | null
  [key: string]: string | null
}

interface ActionBody {
  ok: boolean
  message: string
  code?: string | null
  entry?: Row | null
}

const ENDPOINT = '/api/plan'
const columns = ['计划编号', '养护类型', '养护对象', '计划工期', '预算金额', '编制人员', '审批人员', '计划状态']
const statuses = ['待编制', '待审批', '已批复', '已驳回', '已作废']
const planTypes = ['日常养护', '专项养护', '应急养护']
const steps = [
  { key: 'base', label: '基础信息' },
  { key: 'budget', label: '预算金额与计划工期' },
]

const rows = ref<Row[]>([])
const total = ref(0)
const listLoading = ref(false)
const listError = ref('')
const listInfo = ref('')
const keyword = ref('')
const statusFilter = ref('')

const stats = computed(() => {
  const pending = rows.value.filter((row) => row.status === '待审批').length
  const approved = rows.value.filter((row) => row.status === '已批复').length
  const amount = rows.value
    .filter((row) => row.status !== '已作废' && typeof row['预算金额'] === 'number')
    .reduce((sum, row) => sum + Number(row['预算金额']), 0)
  return [
    { label: '待审批计划', value: pending },
    { label: '已批复计划', value: approved },
    { label: '在列计划金额（元）', value: amount.toLocaleString('zh-CN') },
  ]
})

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

// ---- 列表读取：失败时保留旧列表并给可重试的空态，成功后用服务端数据整体对齐 ----
async function reload() {
  listLoading.value = true
  listError.value = ''
  listInfo.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('养护计划列表读取失败，请稍后重试')
    const payload = await response.json()
    rows.value = Array.isArray(payload.items) ? payload.items : []
    total.value = typeof payload.total === 'number' ? payload.total : rows.value.length
  } catch (error) {
    listError.value = error instanceof Error ? error.message : '养护计划列表读取失败'
  } finally {
    listLoading.value = false
  }
}

// ---- 动作 ----
async function quickAction(action: string, row: Row) {
  listError.value = ''
  listInfo.value = ''
  let remark: string | undefined
  if (action === '驳回') {
    remark = window.prompt('请填写驳回意见，填报人重新打开时会看到该说明：') ?? undefined
    if (remark === undefined) return
  }
  try {
    const result = await postAction(Number(row.id), action, remark)
    if (result.ok) {
      listInfo.value = result.message
      await reload()
    } else {
      listError.value = result.message
    }
  } catch (error) {
    listError.value = error instanceof Error ? error.message : '养护计划操作失败'
  }
}

async function postAction(id: number, action: string, remark?: string): Promise<ActionBody> {
  const response = await request(`${ENDPOINT}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values: { action }, remark: remark ?? null }),
  })
  if (!response.ok) throw new Error(`请求失败（${response.status}），请稍后重试`)
  return (await response.json()) as ActionBody
}

// ---- 弹窗表单 ----
const modalOpen = ref(false)
const modalMode = ref<'create' | 'edit' | 'view'>('create')
const modalId = ref<number | null>(null)
const stepIndex = ref(0)
const detailLoading = ref(false)
const detailError = ref('')
const formSaving = ref(false)
const formError = ref('')
const formInfo = ref('')
const periodStart = ref('')
const periodEnd = ref('')
const amountInput = ref('')
const periodRaw = ref('')

function emptyForm(): PlanForm {
  return {
    计划编号: '',
    养护类型: '',
    养护对象: '',
    编制人员: '',
    审批人员: null,
    计划工期: '',
    预算金额: '',
    last_reject_reason: null,
  }
}

const form = reactive<PlanForm>(emptyForm())
const readonly = computed(() => modalMode.value === 'view')
const entryStatus = computed(() => String(form['计划状态'] || ''))
const modalTitle = computed(() => {
  if (modalMode.value === 'create') return '登记养护计划'
  return readonly.value ? '养护计划详情' : `继续编制养护计划（${entryStatus.value}）`
})

function canEdit(row: Row): boolean {
  return row.status === '待编制' || row.status === '已驳回' || row.status === '已作废'
}

function openCreate() {
  Object.assign(form, emptyForm())
  periodStart.value = ''
  periodEnd.value = ''
  amountInput.value = ''
  periodRaw.value = ''
  stepIndex.value = 0
  modalMode.value = 'create'
  modalId.value = null
  detailError.value = ''
  formError.value = ''
  formInfo.value = ''
  modalOpen.value = true
}

function openEntry(row: Row) {
  const id = Number(row.id)
  modalMode.value = canEdit(row) ? 'edit' : 'view'
  modalId.value = id
  stepIndex.value = 0
  formError.value = ''
  formInfo.value = ''
  modalOpen.value = true
  void loadDetail(id)
}

function closeModal() {
  if (formSaving.value) return
  modalOpen.value = false
  modalId.value = null
  detailError.value = ''
  formError.value = ''
  formInfo.value = ''
}

// 详情每次都从服务端拉取，保证列表状态与详情页对得上、不错位。
async function loadDetail(id: number) {
  detailLoading.value = true
  detailError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail ?? `养护计划 ${id} 详情读取失败（${response.status}）`)
    }
    const entry = (await response.json()) as Row
    Object.assign(form, emptyForm())
    for (const key of ['计划编号', '养护类型', '养护对象', '编制人员', '计划工期']) {
      form[key] = entry[key] == null ? '' : String(entry[key])
    }
    form['审批人员'] = entry['审批人员'] == null ? null : String(entry['审批人员'])
    form['计划状态'] = entry['计划状态'] == null ? String(entry.status ?? '') : String(entry['计划状态'])
    form.last_reject_reason = entry.last_reject_reason == null ? null : String(entry.last_reject_reason)
    amountInput.value = entry['预算金额'] == null ? '' : String(entry['预算金额'])

    // 驳回/作废后重新打开：已有金额与工期就回到第二档继续改，没有才从第一档开始。
    const parsed = splitPeriod(form['计划工期'])
    if (parsed) {
      periodStart.value = parsed[0]
      periodEnd.value = parsed[1]
      periodRaw.value = ''
    } else {
      periodStart.value = ''
      periodEnd.value = ''
      periodRaw.value = form['计划工期']
    }
    const hasBudget = amountInput.value.trim() !== ''
    const hasPeriod = Boolean(parsed)
    stepIndex.value = hasBudget && hasPeriod ? 1 : 0
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : '养护计划详情读取失败'
  } finally {
    detailLoading.value = false
  }
}

function splitPeriod(text: string): [string, string] | null {
  const match = /(\d{4}-\d{1,2}-\d{1,2})\s*[~～\-—–至到]\s*(\d{4}-\d{1,2}-\d{1,2})/.exec(text.trim())
  if (!match) return null
  const start = normalizeDate(match[1])
  const end = normalizeDate(match[2])
  return start && end ? [start, end] : null
}

function normalizeDate(value: string): string {
  const [year, month, day] = value.split('-')
  return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`
}

function goStep(target: number) {
  formError.value = ''
  if (target === 1) {
    const missing = ['计划编号', '养护类型', '养护对象'].filter((key) => !(form[key] ?? '').trim())
    if (missing.length) {
      formError.value = `先补齐基础信息：${missing.join('、')} 不能为空`
      return
    }
  }
  stepIndex.value = target
}

function collectValues() {
  const period = periodStart.value && periodEnd.value ? `${periodStart.value}~${periodEnd.value}` : ''
  return {
    计划编号: form['计划编号'].trim(),
    养护类型: form['养护类型'].trim(),
    养护对象: form['养护对象'].trim(),
    编制人员: form['编制人员'].trim(),
    计划工期: period,
    预算金额: amountInput.value.trim(),
  }
}

function saveDraft() {
  void persist(false)
}

function saveAndSubmit() {
  void persist(true)
}

async function persist(submit: boolean) {
  formError.value = ''
  formInfo.value = ''
  const values = collectValues()
  const missingBase = ['计划编号', '养护类型', '养护对象'].filter(
    (key) => !values[key as keyof typeof values],
  )
  // 提交时把缺的是金额还是工期讲清楚，不让流程一路走到批复。
  const missingTail: string[] = []
  if (submit) {
    if (!values['计划工期']) missingTail.push('计划工期（开工与完工日期）')
    if (!values['预算金额']) missingTail.push('预算金额')
  }
  if (missingBase.length || missingTail.length) {
    const parts = [...missingBase.map((name) => name), ...missingTail]
    formError.value = `${submit ? '提交审批被拦住' : '保存失败'}：还缺 ${parts.join('、')}`
    if (!missingBase.length) stepIndex.value = 1
    return
  }

  formSaving.value = true
  try {
    let result: ActionBody
    if (modalMode.value === 'create') {
      const response = await request(ENDPOINT, {
        method: 'POST',
        body: JSON.stringify({ values }),
      })
      result = (await response.json()) as ActionBody
      if (result.ok && result.entry?.id != null) {
        modalMode.value = 'edit'
        modalId.value = Number(result.entry.id)
      }
    } else if (modalId.value != null) {
      const response = await request(`${ENDPOINT}/${modalId.value}`, {
        method: 'PUT',
        body: JSON.stringify({ values }),
      })
      result = (await response.json()) as ActionBody
    } else {
      result = { ok: false, message: '表单状态异常，请关闭后重新打开' }
    }

    if (!result.ok) {
      formError.value = result.message
      return
    }

    if (!submit) {
      formInfo.value = result.message
      if (modalId.value != null) await loadDetail(modalId.value)
      await reload()
      return
    }

    if (modalId.value == null) {
      formError.value = '登记成功但未能继续提交，请重新打开该计划再提交'
      return
    }
    const actionResult = await postAction(modalId.value, '提交审批')
    if (!actionResult.ok) {
      // 重复提交等回执直接显示后端的可读说明。
      formError.value = actionResult.message
      await loadDetail(modalId.value)
      await reload()
      return
    }
    modalOpen.value = false
    listInfo.value = actionResult.message
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '保存失败，请稍后重试'
  } finally {
    formSaving.value = false
  }
}

onMounted(reload)
</script>
