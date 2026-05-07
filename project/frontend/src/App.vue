<template>
  <div class="page">
    <el-card class="sidebar" shadow="hover">
      <template #header><strong>任务列表</strong></template>
      <el-button type="primary" size="small" @click="fetchTasks">刷新</el-button>
      <div class="task-list">
        <div
          v-for="t in tasks"
          :key="t.id"
          class="task-item"
          :class="{ active: t.id === taskId }"
          @click="selectTask(t)"
        >
          <div class="task-id">{{ t.id }}</div>
          <div class="task-meta">
            <el-tag size="small" :type="statusTagType(t.status)">{{ t.status }}</el-tag>
            <span>{{ t.current_row || 0 }}/{{ t.total_rows || 0 }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <div>
      <el-card class="main-card" shadow="hover">
        <template #header>
          <div class="title-row">
            <h2>Excel 地址解析 Agent</h2>
            <el-tag type="info">Task: {{ taskId || '未创建' }}</el-tag>
          </div>
        </template>

        <section class="section">
          <h3>1) 上传 Excel（上传后自动获取表头并猜测）</h3>
          <el-upload :show-file-list="true" :auto-upload="false" :limit="1" :on-change="onFileChange" :on-exceed="onExceed" accept=".xlsx,.xls" :disabled="historyLocked">
            <el-button type="primary" :loading="loadingAnalyze" :disabled="historyLocked">选择并上传 Excel</el-button>
          </el-upload>
          <div class="hint">当前文件：{{ uploadedFileName || '暂无' }}</div>
          <div v-if="historyLocked" class="hint">历史任务已锁定：不可更换文件或修改待解析字段</div>
        </section>

        <section class="section">
          <h3>2) 确认字段并启动/续跑任务</h3>
          <el-form label-width="140px"><el-form-item label="待解析字段"><el-input v-model="fields.address_field" placeholder="请确认待解析字段" :disabled="historyLocked"/></el-form-item></el-form>
          <el-space><el-button type="warning" @click="run" :disabled="!fields.address_field || !taskId">启动/续跑</el-button><el-button type="danger" plain @click="stopTask" :disabled="!taskId || status !== 'running'">停止任务</el-button><el-button type="danger" @click="deleteCurrentTask" :disabled="!taskId">删除任务</el-button></el-space>
        </section>

        <section class="section">
          <h3>4) 进度与结果</h3>
          <el-progress :percentage="Math.round(progress * 100)" :stroke-width="18"/>
          <p class="status">{{ current }}/{{ total }} | {{ status }}</p>
          <el-button type="primary" @click="download" :disabled="status !== 'completed'">下载结果</el-button>
        </section>
      </el-card>
      <el-card class="log-card" shadow="never">
        <template #header><div class="log-header"><strong>运行日志</strong><el-switch v-model="autoScroll" size="small" active-text="自动滚动"/></div></template>
        <div class="log-wrap" ref="logWrapRef">
          <div v-for="(line, idx) in logs" :key="idx" class="log-line">{{ line }}</div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api from './api/client'
const file = ref(null)
const taskId = ref('')
const tasks = ref([])
const headers = ref([])
const status = ref('idle')
const progress = ref(0)
const current = ref(0)
const total = ref(0)
const fields = ref({ address_field: '' })
const loadingAnalyze = ref(false)
const uploadedFileName = ref('')
const historyLocked = ref(false)
const logs = ref([])
const autoScroll = ref(true)
const logWrapRef = ref(null)
let ws = null
let pollTimer = null


const formatResultFields = (result = {}) => {
  const rows = [
    `联系人姓名: ${result.name || ''}`,
    `联系人电话: ${result.phone || ''}`,
    `联系人邮箱: ${result.email || ''}`,
    `公司名称: ${result.company_name || ''}`,
    `完整地址: ${result.address || ''}`,
    `省份: ${result.province || ''}`,
    `城市: ${result.city || ''}`,
    `国家: ${result.country || ''}`,
    `邮编: ${result.postcode || ''}`,
    `配送备注: ${result.remark || ''}`,
  ]
  return rows.join(' | ')
}

const addLog = (msg, detail = '') => {
  const ts = new Date().toLocaleTimeString()
  logs.value.push(detail ? `[${ts}] ${msg}\n${detail}` : `[${ts}] ${msg}`)
  if (logs.value.length > 500) logs.value.splice(0, logs.value.length - 500)
}


const getDisplayFileName = (filePath = '') => {
  const base = filePath.split('/').pop() || ''
  const idx = base.indexOf('_')
  return idx > 0 ? base.slice(idx + 1) : base
}

const statusTagType = (s) => ({ completed: 'success', failed: 'danger', running: 'warning', uploaded: 'info' }[s] || 'info')

const fetchTasks = async () => {
  const r = await api.get('/tasks')
  tasks.value = r.data.tasks || []
  addLog('刷新任务列表', `任务数: ${tasks.value.length}`)
}

const selectTask = async (t) => {
  taskId.value = t.id
  status.value = t.status || 'idle'
  progress.value = Number(t.progress || 0)
  current.value = Number(t.current_row || 0)
  total.value = Number(t.total_rows || 0)
  fields.value.address_field = t.selected_column || fields.value.address_field
  uploadedFileName.value = getDisplayFileName(t.file_path || '')
  historyLocked.value = Boolean(t.file_path)
  await syncTaskStatus()
  addLog('切换任务', `task_id=${t.id} | status=${status.value}`)
  if (status.value === 'running') {
    const wsReady = await connectWebSocket()
    if (!wsReady) startPolling()
  }
}

const onExceed = () => ElMessage.warning('一次只能上传一个文件')
const onFileChange = async (f) => {
  file.value = f.raw
  const fd = new FormData(); fd.append('file', file.value)
  const r = await api.post('/upload', fd)
  taskId.value = r.data.task_id
  uploadedFileName.value = file.value?.name || ''
  historyLocked.value = false
  await fetchTasks()
  ElMessage.success('上传成功，开始自动猜测字段')
  addLog('上传成功', `task_id=${r.data.task_id}`)
  await fetchHeadersAndAnalyze()
}

const fetchHeadersAndAnalyze = async () => {
  loadingAnalyze.value = true
  try {
    const hr = await api.get(`/headers/${taskId.value}`)
    headers.value = hr.data.headers || []
    const ar = await api.post('/analyze', { headers: headers.value })
    fields.value.address_field = ar.data.address_field || ''
    addLog('地址字段猜测完成', `address_field=${ar.data.address_field || ''}`)
  } finally { loadingAnalyze.value = false }
}

const syncTaskStatus = async () => {
  if (!taskId.value) return
  const r = await api.get(`/task/${taskId.value}`)
  const t = r.data || {}
  progress.value = Number(t.progress || 0)
  current.value = Number(t.current_row || 0)
  total.value = Number(t.total_rows || 0)
  status.value = t.status || status.value
}

const startPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    await syncTaskStatus(); await fetchTasks()
    if (['completed', 'failed'].includes(status.value)) { clearInterval(pollTimer); pollTimer = null }
  }, 1000)
}

const connectWebSocket = async () => {
  if (ws && ws.readyState === WebSocket.OPEN) return true
  if (ws && ws.readyState === WebSocket.CONNECTING) return true

  ws = new WebSocket(`${window.APP_CONFIG?.WS_BASE_URL || 'ws://localhost:8000'}/ws/task/${taskId.value}`)
  ws.onmessage = (e) => {
    const d = JSON.parse(e.data)
    if (d.progress != null) progress.value = d.progress
    if (d.current != null) current.value = d.current
    if (d.total != null) total.value = d.total
    if (d.status) status.value = d.status
    if (d.text != null || d.result != null) {
      const originalText = `待解析原文: ${d.text || ''}`
      const parsedFields = `解析字段: ${formatResultFields(d.result || {})}`
      addLog(`收到WS进度 ${d.current || ''}/${d.total || ''}`, `${originalText}\n${parsedFields}`)
    }
  }

  return await new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), 5000)
    ws.onopen = () => { clearTimeout(timer); resolve(true) }
    ws.onerror = () => { clearTimeout(timer); resolve(false) }
    ws.onclose = () => {
      if (!['completed', 'failed', 'stopped'].includes(status.value)) startPolling()
    }
  })
}


const stopTask = async () => {
  if (!taskId.value) return
  await api.post(`/task/${taskId.value}/stop`)
  status.value = 'stopped'
  await syncTaskStatus()
  await fetchTasks()
  addLog('任务已停止', `task_id=${taskId.value}`)
}

const deleteCurrentTask = async () => {
  if (!taskId.value) return
  await api.delete(`/task/${taskId.value}`)
  taskId.value = ''
  status.value = 'idle'
  progress.value = 0
  current.value = 0
  total.value = 0
  headers.value = []
  fields.value.address_field = ''
  uploadedFileName.value = ''
  historyLocked.value = false
  await fetchTasks()
  addLog('任务已删除')
}


const run = async () => {
  const wsReady = await connectWebSocket()
  await api.post('/run', { task_id: taskId.value, address_field: fields.value.address_field })
  status.value = 'running'
  await fetchTasks()
  addLog('任务启动/续跑', `task_id=${taskId.value} | ws=${wsReady ? 'connected' : 'fallback_polling'}`)
  if (!wsReady) startPolling()
}

const download = () => window.open(`${window.APP_CONFIG?.API_BASE_URL || 'http://localhost:8000'}/download/${taskId.value}`)

watch(logs, async () => {
  if (!autoScroll.value) return
  await nextTick()
  if (logWrapRef.value) logWrapRef.value.scrollTop = logWrapRef.value.scrollHeight
}, { deep: true })

onMounted(fetchTasks)
</script>

<style scoped>
.page { max-width: 1200px; margin: 24px auto; display: grid; grid-template-columns: 320px 1fr; gap: 16px; }
.sidebar,.main-card { border-radius: 12px; }
.task-list { margin-top: 10px; max-height: 640px; overflow: auto; }
.task-item { border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px; margin-bottom: 8px; cursor: pointer; }
.task-item.active { border-color: #409eff; background: #ecf5ff; }
.task-id { font-size: 12px; color: #6b7280; word-break: break-all; }
.task-meta { margin-top: 6px; display: flex; justify-content: space-between; align-items: center; }
.title-row { display: flex; align-items: center; justify-content: space-between; }
.section { margin-bottom: 18px; padding-bottom: 8px; border-bottom: 1px dashed #e5e7eb; }
.section h3 { margin: 0 0 10px; color: #374151; }
.hint,.status { margin-top: 8px; color: #374151; }
.log-card { margin-top: 16px; border-radius: 12px; }
.log-header { display: flex; align-items: center; justify-content: space-between; }
.log-wrap { max-height: 260px; overflow: auto; background: #0b1220; color: #d1fae5; padding: 10px; border-radius: 8px; font-family: monospace; }
.log-line { margin-bottom: 6px; white-space: pre-wrap; }
</style>
