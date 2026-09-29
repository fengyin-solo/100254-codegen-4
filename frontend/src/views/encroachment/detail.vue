<template>
  <section class="page encroachment-detail">
    <header class="page-head detail-head">
      <div>
        <h2>侵限位置明细</h2>
        <p class="page-desc">同一外部干扰源、同一区间和里程范围的重复登记已在此处合并展示。</p>
      </div>
      <button class="btn" type="button" @click="goBack">返回台账原位置</button>
    </header>

    <div v-if="errorMessage" class="retry-panel" role="alert">
      <div>
        <strong>单条明细数据未返回</strong>
        <p>{{ errorMessage }}</p>
        <p class="retry-detail">未生效条件：按台账位置 ID「{{ entryId }}」读取合并明细失败；里程/区间筛选将在返回后继续保留。</p>
      </div>
      <button class="btn primary" type="button" @click="reload">重试读取</button>
    </div>

    <template v-else-if="group">
      <div class="detail-summary">
        <article v-for="item in summaryFields" :key="item.label" class="detail-field">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </div>

      <div class="notice">
        该位置共登记 {{ group.merged_record_count }} 次，台账原始 ID：{{ group.merged_ids.join('、') }}。
        <span v-if="group.merged_record_count > 1">已在列表中合并为一个位置。</span>
      </div>

      <h3>重复登记记录</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>台账ID</th>
            <th>侵限编号</th>
            <th>发现日期</th>
            <th>处置期限</th>
            <th>当前状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in group.source_entries" :key="String(entry.id)">
            <td>{{ entry.id }}</td>
            <td>{{ entry.侵限编号 }}</td>
            <td>{{ entry.发现日期 }}</td>
            <td>{{ entry.处置期限 }}</td>
            <td>{{ entry.status }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

defineOptions({ name: 'EncroachmentDetail' })

type SourceEntry = Record<string, string | number | boolean | null>
type Group = {
  id: number
  侵限编号: string
  外部干扰源: string
  区间号: string
  管辖区段: string
  起始里程: string
  结束里程: string
  侵限类型: string
  status: string
  最早发现日期: string
  最晚发现日期: string
  处置期限: string
  merged_record_count: number
  merged_ids: number[]
  source_entries: SourceEntry[]
}

const route = useRoute()
const router = useRouter()
const group = ref<Group | null>(null)
const errorMessage = ref('')

const entryId = computed(() => String(route.params.id ?? ''))
const summaryFields = computed(() => {
  const value = group.value
  if (!value) return []
  return [
    { label: '外部干扰源', value: value.外部干扰源 },
    { label: '区间号', value: value.区间号 },
    { label: '管辖区段', value: value.管辖区段 },
    { label: '里程范围', value: `${value.起始里程} 至 ${value.结束里程}` },
    { label: '侵限类型', value: value.侵限类型 },
    { label: '聚合状态', value: value.status },
    { label: '发现日期', value: value.最早发现日期 === value.最晚发现日期 ? value.最早发现日期 : `${value.最早发现日期} 至 ${value.最晚发现日期}` },
    { label: '最近处置期限', value: value.处置期限 },
  ]
})

function goBack() {
  if (window.history.state?.back) {
    router.back()
    return
  }
  void router.push({ path: '/encroachment', query: route.query })
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`/api/encroachment/groups/${encodeURIComponent(entryId.value)}`)
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as { detail?: string } | null
      throw new Error(body?.detail || `接口返回 ${response.status}`)
    }
    group.value = (await response.json()) as Group
  } catch (error) {
    group.value = null
    errorMessage.value = error instanceof Error ? error.message : '明细读取失败，请稍后重试'
  }
}

onMounted(reload)
</script>
