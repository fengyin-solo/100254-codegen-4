<template>
  <section class="page intrusion-detail" data-module="intrusion-detail">
    <header class="page-head">
      <div>
        <h2>侵限条目明细</h2>
        <p class="page-desc">查看单条沿线侵限登记及其同位置合并记录；返回台账时保留原来的里程定位条件、页码与滚动位置。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回侵限台账</button>
      </div>
    </header>

    <div v-if="errorMessage" class="error-box">
      <div>
        <p class="error-text">{{ errorMessage }}</p>
        <p class="error-detail">单条数据没有返回，可重试读取；或返回台账继续处理其他条目。</p>
      </div>
      <div class="detail-btns">
        <button class="btn primary" type="button" @click="load">重试</button>
        <button class="btn" type="button" @click="goBack">返回台账</button>
      </div>
    </div>

    <template v-else-if="entry">
      <div v-if="excludedHint" class="warn-box">
        ⚠️ 该条目位置填写不完整（{{ excludedHint }}），已从定位结果中剔除，需补录后才能按里程/区间检索。
      </div>

      <article class="detail-card">
        <h3>{{ entry['台账编号'] }} <span class="status-tag" :class="statusClass">{{ entry.status }}</span></h3>
        <dl class="detail-grid">
          <template v-for="f in fields" :key="f">
            <dt>{{ f }}</dt>
            <dd>{{ entry[f] ?? '—' }}</dd>
          </template>
        </dl>
        <div class="detail-actions">
          <button v-if="entry.status === '待处理'" class="btn primary" type="button" @click="runAction('接单核查')">接单核查</button>
          <button v-if="entry.status === '处理中'" class="btn primary" type="button" @click="runAction('处理完成')">处理完成</button>
          <span v-if="actionMessage" class="ok-text">{{ actionMessage }}</span>
        </div>
      </article>

      <section v-if="group" class="merge-card">
        <h3>同位置合并记录（{{ group.member_ids.length }} 条原始登记，位置 {{ group.mileage_label }}）</h3>
        <p class="muted-text">
          这些条目属于同一外部干扰源在同一里程的重复登记，台账列表中合并为一条展示，动作对整组生效。
        </p>
        <table class="data-table">
          <thead>
            <tr><th>台账编号</th><th>发现日期</th><th>侵限尺寸</th><th>现场描述</th><th>状态</th></tr>
          </thead>
          <tbody>
            <tr v-for="m in group.members" :key="String(m.id)">
              <td>{{ m['台账编号'] }}</td>
              <td>{{ m['发现日期'] ?? '—' }}</td>
              <td>{{ m['侵限尺寸'] ?? '—' }}</td>
              <td>{{ m['现场描述'] ?? '—' }}</td>
              <td>{{ m.status }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Entry = Record<string, string | number | boolean | null>
type Member = Entry
type DetailPayload = {
  entry: Entry
  group: {
    representative_id: number
    member_ids: number[]
    merged_from: string[]
    merged_count: number
    mileage_label: string
    members: Member[]
  } | null
}

const route = useRoute()
const router = useRouter()

const fields = ['所属区间', '里程', '侧别', '外部干扰源', '干扰类型', '侵限尺寸', '发现日期', '现场描述']

const entry = ref<Entry | null>(null)
const group = ref<DetailPayload['group'] | null>(null)
const errorMessage = ref('')
const actionMessage = ref('')

const statusClass = computed(() => {
  switch (entry.value?.status) {
    case '待处理': return 'status-pending'
    case '处理中': return 'status-doing'
    case '已处理': return 'status-done'
    default: return ''
  }
})

const excludedHint = computed(() => {
  const e = entry.value
  if (!e) return ''
  const reasons: string[] = []
  if (!String(e['所属区间'] ?? '').trim()) reasons.push('所属区间缺失')
  const mileage = String(e['里程'] ?? '').trim()
  if (!mileage) reasons.push('里程缺失')
  else if (!/^\s*[Kk]?\d+(\+\d{1,3})?\s*$/.test(mileage)) reasons.push(`里程「${mileage}」无法识别`)
  return reasons.join('；')
})

function goBack() {
  void router.push({ path: '/intrusion' })
}

async function load() {
  errorMessage.value = ''
  const id = route.params.id
  try {
    const response = await request(`/api/intrusion/${id}`)
    if (!response.ok) {
      throw new Error(`接口返回 ${response.status}，明细数据未返回`)
    }
    const data = (await response.json()) as DetailPayload
    entry.value = data.entry
    group.value = data.group
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '侵限明细读取失败'
  }
}

async function runAction(action: string) {
  if (!entry.value) return
  actionMessage.value = ''
  try {
    const response = await request(`/api/intrusion/${entry.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const data = (await response.json()) as { ok: boolean; message: string; entry?: Entry }
    if (!response.ok || !data.ok) {
      throw new Error(data.message || '侵限动作未生效，请稍后重试')
    }
    entry.value = data.entry ?? entry.value
    actionMessage.value = data.message
    await load()
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '侵限条目操作失败'
  }
}

onMounted(load)
</script>

<style scoped>
.detail-card, .merge-card {
  background: #fff; border: 1px solid var(--border); border-radius: 8px;
  padding: 14px 18px; margin-bottom: 16px;
}
.detail-card h3, .merge-card h3 { margin: 0 0 10px; font-size: 15px; }
.detail-grid { display: grid; grid-template-columns: 110px 1fr 110px 1fr; gap: 8px 14px; margin: 0; }
.detail-grid dt { color: var(--muted); font-size: 13px; }
.detail-grid dd { margin: 0; font-size: 13px; }
.detail-actions { margin-top: 14px; display: flex; gap: 10px; align-items: center; }
.status-tag { padding: 2px 10px; border-radius: 10px; font-size: 12px; font-weight: normal; }
.status-pending { background: #fee2e2; color: #b42318; }
.status-doing { background: #fef3c7; color: #92400e; }
.status-done { background: #dcfce7; color: #047857; }
.warn-box { padding: 8px 12px; border: 1px solid #f59e0b; background: #fffbeb; border-radius: 8px; color: #92400e; font-size: 13px; margin-bottom: 12px; }
.error-box { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 12px 16px; border: 1px solid #fca5a5; background: #fef2f2; border-radius: 8px; }
.error-detail { margin: 4px 0 0; color: var(--muted); font-size: 12px; }
.detail-btns { display: flex; gap: 8px; }
.muted-text { color: var(--muted); font-size: 12px; }
.ok-text { color: #047857; font-size: 13px; }
</style>
