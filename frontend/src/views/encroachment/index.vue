<template>
  <section class="page encroachment-page" data-module="encroachment">
    <header class="page-head">
      <div>
        <h2>沿线侵限台账</h2>
        <p class="page-desc">按里程或区间号快速定位临近管辖区段的侵限条目；同位置重复登记自动合并，位置不完整记录先剔除并列明。</p>
      </div>
      <div class="page-actions">
        <button class="btn ghost" type="button" @click="resetFilters">清空定位条件</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card" :class="item.tone">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
        <small v-if="item.note" class="stat-note">{{ item.note }}</small>
      </article>
    </div>

    <form class="filter-bar location-filter" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>单点里程</span>
        <input v-model="filters.mileage" placeholder="如 K12+100" />
      </label>
      <label class="filter-item">
        <span>区间起点</span>
        <input v-model="filters.start_mileage" placeholder="如 K12+000" />
      </label>
      <label class="filter-item">
        <span>区间终点</span>
        <input v-model="filters.end_mileage" placeholder="如 K13+000" />
      </label>
      <label class="filter-item">
        <span>区间号 / 管辖区段</span>
        <input v-model="filters.section" placeholder="如 QJ-03 或 城东" />
      </label>
      <label class="filter-item compact">
        <span>临近距离（米）</span>
        <input v-model="filters.proximity" type="number" min="0" max="5000" placeholder="单点默认 500" />
      </label>
      <button class="btn primary" type="submit">定位查询</button>
      <button class="btn" type="button" @click="resetFilters">重置</button>
    </form>

    <div v-if="errorMessage" class="retry-panel" role="alert">
      <div>
        <strong>台账数据未返回</strong>
        <p>{{ errorMessage }}</p>
        <p class="retry-detail">未生效条件：{{ inactiveConditionText }}</p>
      </div>
      <button class="btn primary" type="button" @click="reload">重试当前条件</button>
    </div>

    <template v-else>
      <div v-if="payload?.retained_pending_count" class="notice warning">
        已额外保留 {{ payload.retained_pending_count }} 个当前里程范围外的待处理外部干扰源，避免未处理隐患因切换范围漏查。
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column.key">{{ column.label }}</th>
            <th>定位 / 保留原因</th>
            <th>明细</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)" :class="{ 'retained-row': row.match_type === 'pending_retained' }">
            <td v-for="column in columns" :key="column.key">
              <span v-if="column.key === 'status'" :class="['status-pill', statusTone(row.status)]">{{ row[column.key] ?? '—' }}</span>
              <span v-else>{{ row[column.key] ?? '—' }}</span>
            </td>
            <td>{{ row.match_reason || '未使用定位条件' }}</td>
            <td>
              <RouterLink class="link" :to="detailHref(row.id)">进入单条</RouterLink>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 2" class="empty-state">当前条件未定位到侵限条目，也没有范围外待处理干扰源</td>
          </tr>
        </tbody>
      </table>

      <footer class="list-pager">
        <button class="btn" type="button" :disabled="page <= 1" @click="changePage(page - 1)">上一页</button>
        <span>第 {{ page }} 页 / 本结果 {{ total }} 个位置</span>
        <button class="btn" type="button" :disabled="page * size >= total" @click="changePage(page + 1)">下一页</button>
      </footer>

      <section class="reconcile-panel">
        <h3>数量对账</h3>
        <p :class="payload?.balance?.matches ? 'ok-text' : 'error-text'">
          台账总数 {{ payload?.ledger_total ?? 0 }} =
          剔除后有效原始 {{ payload?.valid_total ?? 0 }} 条；
          其中合并抵消 {{ payload?.merged_count ?? 0 }} 条，
          合并后位置 {{ payload?.grouped_total ?? 0 }} 个，
          剔除 {{ payload?.excluded_total ?? 0 }} 条。
        </p>
        <p class="formula">
          校验：{{ payload?.grouped_total ?? 0 }} + {{ payload?.merged_count ?? 0 }} + {{ payload?.excluded_total ?? 0 }}
          = {{ payload?.balance?.reconciled_total ?? 0 }}，
          {{ payload?.balance?.matches ? '与台账总数一致' : '与台账总数不一致' }}
        </p>
      </section>

      <section class="excluded-panel">
        <h3>位置填写不完整，已剔除 {{ excluded.length }} 条</h3>
        <table class="data-table subtle">
          <thead>
            <tr>
              <th>台账ID</th>
              <th>侵限编号</th>
              <th>外部干扰源</th>
              <th>区间号</th>
              <th>起始里程</th>
              <th>结束里程</th>
              <th>管辖区段</th>
              <th>剔除原因</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in excluded" :key="String(item.id)">
              <td>{{ item.id }}</td>
              <td>{{ item.侵限编号 }}</td>
              <td>{{ item.外部干扰源 }}</td>
              <td>{{ item.区间号 || '—' }}</td>
              <td>{{ item.起始里程 || '—' }}</td>
              <td>{{ item.结束里程 || '—' }}</td>
              <td>{{ item.管辖区段 || '—' }}</td>
              <td class="error-text">{{ item.reason }}</td>
            </tr>
            <tr v-if="!excluded.length">
              <td colspan="8" class="empty-state">本次台账没有位置不完整记录</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

defineOptions({ name: 'EncroachmentLedger' })

type RowValue = string | number | boolean | null | string[] | number[]
type Row = Record<string, RowValue>
type ExcludedRow = {
  id: number
  侵限编号: string
  外部干扰源: string
  区间号: string
  起始里程: string
  结束里程: string
  管辖区段: string
  reason: string
}
type Payload = {
  items: Row[]
  total: number
  page: number
  size: number
  ledger_total: number
  valid_total: number
  grouped_total: number
  merged_count: number
  excluded_total: number
  retained_pending_count: number
  excluded: ExcludedRow[]
  balance?: { reconciled_total: number; matches: boolean }
}

const ENDPOINT = '/api/encroachment'
const route = useRoute()
const router = useRouter()
const size = 20

const columns = [
  { key: '侵限编号', label: '侵限编号' },
  { key: '外部干扰源', label: '外部干扰源' },
  { key: '区间号', label: '区间号' },
  { key: '管辖区段', label: '管辖区段' },
  { key: '起始里程', label: '起始里程' },
  { key: '结束里程', label: '结束里程' },
  { key: '侵限类型', label: '侵限类型' },
  { key: 'status', label: '处理状态' },
  { key: '登记次数', label: '登记次数' },
]

const rows = ref<Row[]>([])
const excluded = ref<ExcludedRow[]>([])
const total = ref(0)
const page = ref(1)
const payload = ref<Payload | null>(null)
const errorMessage = ref('')
const filters = reactive({
  mileage: '',
  start_mileage: '',
  end_mileage: '',
  section: '',
  proximity: '',
})

const stats = computed(() => [
  { label: '台账总数', value: payload.value?.ledger_total ?? 0, note: '含剔除与重复登记', tone: '' },
  { label: '剔除后有效原始', value: payload.value?.valid_total ?? 0, note: '位置完整才可定位', tone: '' },
  { label: '合并后位置', value: payload.value?.grouped_total ?? 0, note: `已抵消 ${payload.value?.merged_count ?? 0} 条重复`, tone: 'primary' },
  { label: '已剔除', value: payload.value?.excluded_total ?? 0, note: '下方列明条目', tone: payload.value?.excluded_total ? 'warning' : '' },
  { label: '范围外待处理保留', value: payload.value?.retained_pending_count ?? 0, note: '切换范围不漏查', tone: payload.value?.retained_pending_count ? 'warning' : '' },
])

const inactiveConditionText = computed(() => {
  const names: string[] = []
  if (filters.mileage) names.push(`单点里程「${filters.mileage}」`)
  if (filters.start_mileage || filters.end_mileage) {
    names.push(`里程区间「${filters.start_mileage || '?'} 至 ${filters.end_mileage || '?'}」`)
  }
  if (filters.section) names.push(`区间号/管辖区段「${filters.section}」`)
  if (filters.proximity) names.push(`临近距离「${filters.proximity} 米」`)
  return names.length ? names.join('、') : '当前未输入定位条件，整表读取未完成'
})

function hydrateFiltersFromRoute() {
  filters.mileage = String(route.query.mileage ?? '')
  filters.start_mileage = String(route.query.start_mileage ?? '')
  filters.end_mileage = String(route.query.end_mileage ?? '')
  filters.section = String(route.query.section ?? '')
  filters.proximity = String(route.query.proximity ?? '')
  page.value = Number(route.query.page ?? 1) || 1
}

function currentQuery(): Record<string, string> {
  const query: Record<string, string> = {}
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim()) query[key] = value.trim()
  }
  if (page.value > 1) query.page = String(page.value)
  return query
}

async function syncRouteQuery() {
  await router.replace({ path: route.path, query: currentQuery() })
}

function applyFilters() {
  page.value = 1
  void syncRouteQuery()
}

function changePage(next: number) {
  page.value = next
  void syncRouteQuery()
}

function resetFilters() {
  Object.keys(filters).forEach((key) => {
    filters[key as keyof typeof filters] = ''
  })
  page.value = 1
  void syncRouteQuery()
}

function detailHref(id: RowValue) {
  return { path: `${ENDPOINT}/groups/${String(id)}`, query: currentQuery() }
}

function statusTone(status: RowValue) {
  if (status === '未处理') return 'danger'
  if (status === '处理中') return 'warning'
  return 'ok'
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(currentQuery()).toString()
  try {
    const response = await request(`${ENDPOINT}${query ? `?${query}` : ''}`)
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as { detail?: string } | null
      throw new Error(body?.detail || `接口返回 ${response.status}，定位结果未生效`)
    }
    const data = (await response.json()) as Payload
    payload.value = data
    rows.value = data.items ?? []
    excluded.value = data.excluded ?? []
    total.value = data.total ?? 0
    page.value = data.page ?? page.value
  } catch (error) {
    payload.value = null
    rows.value = []
    excluded.value = []
    total.value = 0
    const detail = error instanceof Error ? error.message : '未知网络错误'
    errorMessage.value = `${detail}。请检查后端服务或网络后重试；本次未拿到服务端结果，当前里程、区间、临近距离等定位条件均未生效。`
  }
}

watch(
  () => route.fullPath,
  () => {
    hydrateFiltersFromRoute()
    void reload()
  },
  { flush: 'post' },
)

onMounted(() => {
  hydrateFiltersFromRoute()
  void reload()
})
</script>
