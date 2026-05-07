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
          <h3>1) 上传 Excel</h3>
          <el-upload :show-file-list="true" :auto-upload="false" :limit="1" :on-change="onFileChange" :on-exceed="onExceed" accept=".xlsx,.xls">
            <el-button type="primary">选择并上传 Excel</el-button>
          </el-upload>
        </section>

        <section class="section">
          <h3>2) 获取表头并让 LLM 猜测地址字段</h3>
          <el-button type="success" @click="fetchHeadersAndAnalyze" :disabled="!taskId || loadingAnalyze" :loading="loadingAnalyze">获取表头并猜测地址字段</el-button>
          <div class="hint">表头：{{ headers.join('；') || '暂无' }}</div>
        </section>

        <section class="section">
          <h3>3) 确认字段并启动/续跑任务</h3>
          <el-form label-width="140px"><el-form-item label="address_field"><el-input v-model="fields.address_field" placeholder="请确认详细地址字段"/></el-form-item></el-form>
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
        <template #header><strong>运行日志</strong></template>
        <div class="log-wrap">
          <div v-for="(line, idx) in logs" :key="idx" class="log-line">{{ line }}</div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
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
const logs = ref([])
let ws = null
let pollTimer = null


const addLog = (msg, extra = null) => {
  const ts = new Date().toLocaleTimeString()
  logs.value.push(`[${ts}] ${msg}`)
  if (extra) logs.value.push(`  -> ${JSON.stringify(extra)}`)
  if (logs.value.length > 500) logs.value.splice(0, logs.value.length - 500)
}

const statusTagType = (s) => ({ completed: 'success', failed: 'danger', running: 'warning', uploaded: 'info' }[s] || 'info')

const fetchTasks = async () => {
  const r = await api.get('/tasks')
  tasks.value = r.data.tasks || []
  addLog('刷新任务列表', { count: tasks.value.length })
}

const selectTask = async (t) => {
  taskId.value = t.id
  status.value = t.status || 'idle'
  progress.value = Number(t.progress || 0)
  current.value = Number(t.current_row || 0)
  total.value = Number(t.total_rows || 0)
  fields.value.address_field = t.selected_column || fields.value.address_field
  await syncTaskStatus()
  addLog('切换任务', { task_id: t.id, status: status.value })
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
  await fetchTasks()
  ElMessage.success('上传成功')
  addLog('上传成功', r.data)
}

const fetchHeadersAndAnalyze = async () => {
  loadingAnalyze.value = true
  try {
    const hr = await api.get(`/headers/${taskId.value}`)
    headers.value = hr.data.headers || []
    const ar = await api.post('/analyze', { headers: headers.value })
    fields.value.address_field = ar.data.address_field || ''
    addLog('地址字段猜测完成', ar.data)
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
    if (d.text != null || d.result != null) addLog('收到WS进度', { current: d.current, total: d.total, status: d.status })
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
  addLog('任务已停止', { task_id: taskId.value })
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
  await fetchTasks()
  addLog('任务已删除')
}


const run = async () => {
  const wsReady = await connectWebSocket()
  await api.post('/run', { task_id: taskId.value, address_field: fields.value.address_field })
  status.value = 'running'
  await fetchTasks()
  addLog('任务启动/续跑', { task_id: taskId.value, ws: wsReady ? 'connected' : 'fallback_polling' })
  if (!wsReady) startPolling()
}

const download = () => window.open(`${window.APP_CONFIG?.API_BASE_URL || 'http://localhost:8000'}/download/${taskId.value}`)

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
.log-wrap { max-height: 260px; overflow: auto; background: #0b1220; color: #d1fae5; padding: 10px; border-radius: 8px; font-family: monospace; }
.log-line { margin-bottom: 6px; white-space: pre-wrap; }
</style>
