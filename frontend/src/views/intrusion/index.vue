<template>
  <section class="page" data-module="intrusion">
    <header class="page-head">
      <div>
        <h2>沿线侵限台账</h2>
        <p class="page-desc">沿线外部干扰源侵限条目按里程与区间定位：输入里程或区间号即可过滤临近管辖区段，同一干扰源重复登记按位置合并，位置不完整的条目先剔除并列明原因。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出当前定位清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar intrusion-filters" @submit.prevent="reload(1)">
      <label class="filter-item">
        <span>里程定位（如 K33+200）</span>
        <input v-model="filters.mileage" placeholder="K33+200" />
      </label>
      <label class="filter-item">
        <span>临近半径（米）</span>
        <input v-model.number="filters.radius" type="number" min="50" max="5000" step="50" placeholder="500" />
      </label>
      <label class="filter-item">
        <span>区间起（如 K30+000）</span>
        <input v-model="filters.mileage_from" placeholder="K30+000" />
      </label>
      <label class="filter-item">
        <span>区间止（如 K36+000）</span>
        <input v-model="filters.mileage_to" placeholder="K36+000" />
      </label>
      <label class="filter-item">
        <span>区间号</span>
        <input v-model="filters.section" placeholder="如 QJ03" />
      </label>
      <label class="filter-item">
        <span>干扰源关键字</span>
        <input v-model="filters.keyword" placeholder="干扰源 / 台账编号" />
      </label>
      <label class="filter-item">
        <span>处理状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn primary" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>
    <p class="filter-hint">里程定位与区间二选一：同时给出时以里程区间为准；半径默认 500 米（50–5000）。</p>

    <div v-if="warnings.length" class="warn-box">
      <p v-for="(w, i) in warnings" :key="i">⚠️ {{ w }}</p>
    </div>

    <div v-if="scopeNote" class="scope-box">
      当前定位范围：{{ scopeNote }}
      <span v-if="payload?.out_scope_pending">；另有
        <strong>{{ payload.out_scope_pending }}</strong> 条范围外未处理干扰源（黄色标注）一并带出，防止漏办。
      </span>
    </div>

    <div v-if="errorMessage" class="error-box">
      <div>
        <p class="error-text">{{ errorMessage }}</p>
        <p class="error-detail">未生效条件：{{ ineffectiveLabel }}</p>
      </div>
      <button class="btn primary" type="button" @click="reload()">重试</button>
    </div>

    <template v-else>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
            <th>处理状态</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)" :class="{ 'oos-row': row.out_of_scope }">
            <td>
              <RouterLink class="link" :to="`/intrusion/${row.id}`">{{ row['台账编号'] }}</RouterLink>
              <span v-if="row.merged_count" class="badge merge-badge">合并 {{ row.merged_count }} 条</span>
            </td>
            <td>{{ row['所属区间'] ?? '—' }}</td>
            <td>{{ row.mileage_label ?? row['里程'] ?? '—' }}</td>
            <td>{{ row['侧别'] ?? '—' }}</td>
            <td>{{ row['外部干扰源'] ?? '—' }}</td>
            <td>{{ row['干扰类型'] ?? '—' }}</td>
            <td>{{ row['侵限尺寸'] ?? '—' }}</td>
            <td>{{ row['发现日期'] ?? '—' }}</td>
            <td>{{ row.status }}<span v-if="row.out_of_scope" class="badge oos-badge">范围外待处理</span></td>
            <td class="row-actions">
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
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 2" class="empty-state">当前条件下暂无侵限条目（范围外未处理条目也会在此显示）</td>
          </tr>
        </tbody>
      </table>

      <div v-if="payload && payload.filtered_total > pageSize" class="pager">
        <button class="btn" type="button" :disabled="page <= 1" @click="changePage(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ totalPages }} 页</span>
        <button class="btn" type="button" :disabled="page >= totalPages" @click="changePage(page + 1)">下一页</button>
      </div>

      <section class="excluded-box">
        <h3>位置不完整、已剔除的条目（{{ payload?.excluded_count ?? 0 }} 条）</h3>
        <p v-if="!(payload?.excluded_items?.length)" class="muted-text">本次台账无剔除条目。</p>
        <table v-else class="data-table">
          <thead>
            <tr><th>台账编号</th><th>所属区间</th><th>里程</th><th>外部干扰源</th><th>剔除原因</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in payload.excluded_items" :key="String(item.id)">
              <td>
                <RouterLink class="link" :to="`/intrusion/${item.id}`">{{ item['台账编号'] }}</RouterLink>
              </td>
              <td>{{ item['所属区间'] || '—' }}</td>
              <td>{{ item['里程'] || '—' }}</td>
              <td>{{ item['外部干扰源'] || '—' }}</td>
              <td class="error-text">{{ (item.exclude_reasons ?? []).join('；') }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <footer class="page-foot ledger-foot">
        <span>
          台账总数 <strong>{{ payload?.total ?? 0 }}</strong> 条
          ＝ 位置完整原始 {{ payload?.valid_count ?? 0 }} 条
          （合并后展示 {{ payload?.kept_count ?? 0 }} 条、其中重复登记压缩 {{ payload?.merged_count ?? 0 }} 条）
          ＋ 剔除 {{ payload?.excluded_count ?? 0 }} 条
          <span :class="payload?.reconciled ? 'ok-text' : 'error-text'">
            {{ payload?.reconciled ? '✓ 数量对账一致' : '✗ 数量对账不一致，请联系管理员' }}
          </span>
        </span>
        <span v-if="actionMessage" class="ok-text">{{ actionMessage }}</span>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onActivated, onDeactivated, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

defineOptions({ name: 'IntrusionLedger' })

type Row = Record<string, string | number | null> & {
  status: string
  out_of_scope?: boolean
  merged_count?: number
}

type ExcludedItem = Row & { exclude_reasons?: string[] }

type LedgerPayload = {
  items: Row[]
  total: number
  page: number
  size: number
  filtered_total: number
  valid_count: number
  kept_count: number
  merged_count: number
  excluded_count: number
  excluded_items: ExcludedItem[]
  out_scope_pending: number
  reconciled: boolean
  filters_applied: Record<string, string | number | null>
  warnings: string[]
}

const ENDPOINT = '/api/intrusion'
const columns = ['台账编号', '所属区间', '里程', '侧别', '外部干扰源', '干扰类型', '侵限尺寸', '发现日期']
const statuses = ['待处理', '处理中', '已处理']
const pageSize = 10

const rows = ref<Row[]>([])
const payload = ref<LedgerPayload | null>(null)
const errorMessage = ref('')
const actionMessage = ref('')
const page = ref(1)
let scrollY = 0
const hasLoaded = ref(false)

const filters = reactive({
  mileage: '',
  radius: 500,
  mileage_from: '',
  mileage_to: '',
  section: '',
  keyword: '',
  status: '',
})

const warnings = computed(() => payload.value?.warnings ?? [])

const totalPages = computed(() =>
  Math.max(1, Math.ceil((payload.value?.filtered_total ?? 0) / pageSize)),
)

const stats = computed(() => [
  { label: '台账总数', value: payload.value?.total ?? '—' },
  { label: '合并后展示', value: payload.value?.kept_count ?? '—' },
  { label: '范围外未处理带出', value: payload.value?.out_scope_pending ?? 0 },
  { label: '位置不完整已剔除', value: payload.value?.excluded_count ?? 0 },
])

const scopeNote = computed(() => {
  const f = payload.value?.filters_applied
  if (!f) return ''
  const parts: string[] = []
  if (f.scope_lower || f.scope_upper) {
    parts.push(`里程 ${f.scope_lower ?? '起点不限'} ~ ${f.scope_upper ?? '终点不限'}`)
  }
  if (f.section) parts.push(`区间号含「${f.section}」`)
  return parts.join('；')
})

const ineffectiveLabel = computed(() => {
  const names: string[] = []
  if (filters.mileage.trim()) names.push(`里程定位「${filters.mileage.trim()}」`)
  if (filters.mileage_from.trim()) names.push(`里程区间起点「${filters.mileage_from.trim()}」`)
  if (filters.mileage_to.trim()) names.push(`里程区间终点「${filters.mileage_to.trim()}」`)
  if (filters.section.trim()) names.push(`区间号「${filters.section.trim()}」`)
  if (filters.keyword.trim()) names.push(`干扰源关键字「${filters.keyword.trim()}」`)
  if (filters.status) names.push(`处理状态「${filters.status}」`)
  return names.length ? names.join('、') : '（当前没有设置定位条件，可重试列表读取）'
})

function actionsFor(row: Row): string[] {
  if (row.status === '待处理') return ['接单核查']
  if (row.status === '处理中') return ['处理完成']
  return []
}

function resetFilters() {
  filters.mileage = ''
  filters.radius = 500
  filters.mileage_from = ''
  filters.mileage_to = ''
  filters.section = ''
  filters.keyword = ''
  filters.status = ''
  void reload(1)
}

function changePage(next: number) {
  void reload(next)
}

function exportRows() {
  const query = new URLSearchParams()
  Object.entries({
    mileage: filters.mileage,
    mileage_from: filters.mileage_from,
    mileage_to: filters.mileage_to,
    section: filters.section,
    radius: String(filters.radius || 500),
  }).forEach(([k, v]) => {
    if (v) query.set(k, v)
  })
  window.open(`${ENDPOINT}/export?${query.toString()}`, '_blank')
}

async function runAction(action: string, row: Row) {
  actionMessage.value = ''
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const data = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !data.ok) {
      throw new Error(data.message || '侵限动作未生效，请稍后重试')
    }
    actionMessage.value = data.message
    scrollY = window.scrollY
    await reload(page.value, true)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '侵限条目操作失败'
  }
}

async function reload(nextPage?: number, keepScroll = false) {
  if (nextPage) page.value = nextPage
  errorMessage.value = ''
  const query = new URLSearchParams()
  const setIf = (key: string, value: string | number) => {
    if (String(value ?? '').trim()) query.set(key, String(value))
  }
  setIf('mileage', filters.mileage)
  setIf('mileage_from', filters.mileage_from)
  setIf('mileage_to', filters.mileage_to)
  setIf('section', filters.section)
  setIf('keyword', filters.keyword)
  setIf('status', filters.status)
  setIf('radius', filters.radius || 500)
  query.set('page', String(page.value))
  query.set('size', String(pageSize))
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error(`接口返回 ${response.status}，台账数据未更新`)
    }
    const data = (await response.json()) as LedgerPayload
    payload.value = data
    rows.value = data.items ?? []
    hasLoaded.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '侵限台账读取失败'
  }
  if (!keepScroll) {
    window.scrollTo({ top: 0 })
  } else {
    window.scrollTo({ top: scrollY })
  }
}

onMounted(() => {
  if (!hasLoaded.value) void reload(1)
})

onActivated(() => {
  // 从单条详情返回：停在原来的滚动位置，不重新拉取、不丢过滤条件与页码。
  if (hasLoaded.value) window.scrollTo({ top: scrollY })
})

onDeactivated(() => {
  scrollY = window.scrollY
})
</script>

<style scoped>
.intrusion-filters { align-items: flex-end; }
.intrusion-filters .filter-item input,
.intrusion-filters .filter-item select {
  min-width: 130px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.filter-hint { margin: -4px 0 10px; font-size: 12px; color: var(--muted); }
.badge { display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 10px; font-size: 11px; line-height: 18px; }
.merge-badge { background: #e0ecff; color: #1d4ed8; }
.oos-badge { background: #fef3c7; color: #92400e; margin-left: 4px; }
.oos-row { background: #fffbeb; }
.warn-box { margin: 0 0 10px; padding: 8px 12px; border: 1px solid #f59e0b; background: #fffbeb; border-radius: 8px; color: #92400e; font-size: 13px; }
.warn-box p { margin: 2px 0; }
.scope-box { margin: 0 0 10px; padding: 8px 12px; background: #eef6ff; border: 1px solid #bfdbfe; border-radius: 8px; font-size: 13px; color: #1e40af; }
.error-box { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 12px 16px; border: 1px solid #fca5a5; background: #fef2f2; border-radius: 8px; margin-bottom: 12px; }
.error-detail { margin: 4px 0 0; color: var(--muted); font-size: 12px; }
.excluded-box { margin-top: 16px; }
.excluded-box h3 { font-size: 14px; margin: 0 0 8px; }
.muted-text { color: var(--muted); font-size: 13px; }
.pager { display: flex; gap: 12px; align-items: center; justify-content: center; margin-top: 10px; font-size: 13px; }
.pager .btn:disabled { opacity: 0.5; cursor: not-allowed; }
.ledger-foot { flex-direction: column; gap: 4px; align-items: flex-start; }
.ok-text { color: #047857; }
</style>
