<template>
  <div class="page">
    <el-card class="main-card" shadow="hover">
      <template #header>
        <div class="title-row">
          <h2>Excel 地址解析 Agent</h2>
          <el-tag type="info">Task: {{ taskId || '未创建' }}</el-tag>
        </div>
      </template>

      <section class="section">
        <h3>1) 上传 Excel</h3>
        <el-upload
          :show-file-list="true"
          :auto-upload="false"
          :limit="1"
          :on-change="onFileChange"
          :on-exceed="onExceed"
          accept=".xlsx,.xls"
        >
          <el-button type="primary">选择并上传 Excel</el-button>
        </el-upload>
      </section>

      <section class="section">
        <h3>2) 获取表头并让 LLM 猜测地址字段</h3>
        <el-button type="success" @click="fetchHeadersAndAnalyze" :disabled="!taskId || loadingAnalyze" :loading="loadingAnalyze">
          获取表头并猜测地址字段
        </el-button>
        <div class="hint">表头：{{ headers.join('；') || '暂无' }}</div>
      </section>

      <section class="section">
        <h3>3) 确认字段并启动任务</h3>
        <el-form label-width="140px">
          <el-form-item label="address_field">
            <el-input v-model="fields.address_field" placeholder="请确认详细地址字段"/>
          </el-form-item>
        </el-form>
        <el-button type="warning" @click="run" :disabled="!fields.address_field || !taskId">启动任务</el-button>
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
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from './api/client'

const file = ref(null)
const taskId = ref('')
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
}

const onExceed = () => {
  ElMessage.warning('一次只能上传一个文件')
}

const onFileChange = async (f) => {
  file.value = f.raw
  const fd = new FormData()
  fd.append('file', file.value)
  const reqInfo = { url: '/upload', filename: file.value?.name }
  addLog('开始上传文件', reqInfo)
  try {
    const r = await api.post('/upload', fd)
    taskId.value = r.data.task_id
    addLog('上传成功', r.data)
    ElMessage.success('上传成功')
  } catch (e) {
    addLog('上传失败', { request: reqInfo, response: e?.response?.data || e.message })
    ElMessage.error('上传失败')
  }
}

const fetchHeadersAndAnalyze = async () => {
  loadingAnalyze.value = true
  const headersReq = { url: `/headers/${taskId.value}` }
  try {
    const hr = await api.get(`/headers/${taskId.value}`)
    headers.value = hr.data.headers || []
    addLog(`获取表头成功: ${headers.value.join('; ')}`, hr.data)
  } catch (e) {
    addLog('获取表头失败', { request: headersReq, response: e?.response?.data || e.message })
    ElMessage.error('获取表头失败')
    loadingAnalyze.value = false
    return
  }

  const analyzeReq = { url: '/analyze', body: { headers: headers.value } }
  addLog('开始请求大模型猜测地址字段', analyzeReq)
  try {
    const ar = await api.post('/analyze', { headers: headers.value })
    fields.value.address_field = ar.data.address_field || ''
    addLog('猜测字段成功', ar.data)
    ElMessage.success('猜测字段成功')
  } catch (e) {
    addLog('猜测字段失败', { request: analyzeReq, response: e?.response?.data || e.message })
    ElMessage.error('猜测字段失败')
  } finally {
    loadingAnalyze.value = false
  }
}


const syncTaskStatus = async () => {
  if (!taskId.value) return
  try {
    const r = await api.get(`/task/${taskId.value}`)
    const t = r.data || {}
    progress.value = Number(t.progress || 0)
    current.value = Number(t.current_row || 0)
    total.value = Number(t.total_rows || 0)
    if (t.status) status.value = t.status
  } catch (e) {
    addLog('轮询任务状态失败', { response: e?.response?.data || e.message })
  }
}

const startPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    await syncTaskStatus()
    if (['completed', 'failed'].includes(status.value)) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }, 1000)
}


const connectWebSocket = async () => {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  ws = new WebSocket(`${window.APP_CONFIG?.WS_BASE_URL || 'ws://localhost:8000'}/ws/task/${taskId.value}`)
  ws.onmessage = (e) => {
    const d = JSON.parse(e.data)
    if (d.progress != null) progress.value = d.progress
    if (d.current != null) current.value = d.current
    if (d.total != null) total.value = d.total
    if (d.status) status.value = d.status
    if (d.text != null || d.result != null) {
      addLog('收到解析进度消息', { text: d.text, result: d.result, current: d.current, total: d.total })
    }
  }

  ws.onclose = () => {
    addLog('WebSocket已断开，切换到HTTP轮询')
    if (!['completed', 'failed'].includes(status.value)) {
      startPolling()
    }
  }

  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('WebSocket连接超时')), 5000)
    ws.onopen = () => {
      clearTimeout(timer)
      addLog('WebSocket连接成功')
      resolve(true)
    }
    ws.onerror = () => {
      clearTimeout(timer)
      addLog('WebSocket连接异常')
      reject(new Error('WebSocket连接失败'))
    }
  })
}

const run = async () => {
  const req = { task_id: taskId.value, address_field: fields.value.address_field }
  try {
    await connectWebSocket()
    const runResp = await api.post('/run', req)
    if (runResp?.data?.total != null) {
      total.value = Number(runResp.data.total)
      current.value = 0
      progress.value = 0
    }
    status.value = 'running'
    addLog('任务启动成功', { ...req, total: runResp?.data?.total })
    await syncTaskStatus()
  } catch (e) {
    startPolling()
    addLog('任务启动失败', { request: req, response: e?.response?.data || e.message })
    ElMessage.error('任务启动失败')
  }
}

const download = () => {
  const url = `${window.APP_CONFIG?.API_BASE_URL || 'http://localhost:8000'}/download/${taskId.value}`
  addLog('下载结果文件', { url })
  window.open(url)
}
</script>

<style scoped>
.page { max-width: 960px; margin: 24px auto; display: grid; gap: 16px; }
.main-card { border-radius: 12px; }
.title-row { display: flex; align-items: center; justify-content: space-between; }
.section { margin-bottom: 18px; padding-bottom: 8px; border-bottom: 1px dashed #e5e7eb; }
.section h3 { margin: 0 0 10px; color: #374151; }
.hint { margin-top: 8px; color: #6b7280; }
.status { font-weight: 600; color: #374151; }
.log-card { border-radius: 12px; }
.log-wrap { max-height: 260px; overflow: auto; background: #0b1220; color: #d1fae5; padding: 10px; border-radius: 8px; font-family: monospace; }
.log-line { margin-bottom: 6px; white-space: pre-wrap; }
</style>
