const { createApp, ref, computed } = Vue

createApp({
  setup() {
    const apiBase = 'http://localhost:8000'
    const file = ref(null)
    const job = ref(null)
    const targetColumn = ref('')
    const prefix = ref('parsed')
    const loading = ref(false)
    const ws = ref(null)

    const progressText = computed(() => `${job.value?.progress ?? 0}%`)

    const connectWS = (jobId) => {
      if (ws.value) ws.value.close()
      ws.value = new WebSocket(`ws://localhost:8000/ws/job/${jobId}`)
      ws.value.onopen = () => ws.value.send('subscribe')
      ws.value.onmessage = (e) => {
        const payload = JSON.parse(e.data)
        job.value = payload
      }
    }

    const upload = async () => {
      if (!file.value) return
      loading.value = true
      const form = new FormData()
      form.append('file', file.value)
      const res = await fetch(`${apiBase}/api/upload`, { method: 'POST', body: form })
      job.value = await res.json()
      targetColumn.value = job.value.suggested_address_columns?.[0] || ''
      connectWS(job.value.job_id)
      loading.value = false
    }

    const startProcess = async () => {
      if (!job.value || !targetColumn.value) return
      loading.value = true
      const res = await fetch(`${apiBase}/api/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: job.value.job_id, target_column: targetColumn.value, output_columns_prefix: prefix.value })
      })
      job.value = await res.json()
      loading.value = false
    }

    return { file, job, targetColumn, prefix, loading, progressText, upload, startProcess }
  },
  template: `
  <div class="min-h-screen p-8">
    <div class="max-w-5xl mx-auto bg-white shadow-xl rounded-2xl p-8">
      <h1 class="text-3xl font-bold text-slate-800">Excel 客户与地址提取 Agent</h1>
      <p class="text-slate-500 mt-2">上传表格 → 自动识别字段 → 确认目标列 → 实时进度提取并回写</p>

      <div class="mt-6 p-5 border rounded-xl bg-slate-50">
        <input class="block w-full text-sm text-slate-700" type="file" accept=".xlsx,.xls" @change="e => file = e.target.files[0]" />
        <button class="mt-4 px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50" @click="upload" :disabled="loading">
          {{ loading ? '处理中...' : '上传并分析表头' }}
        </button>
      </div>

      <div v-if="job" class="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="p-5 border rounded-xl">
          <h2 class="text-lg font-semibold">任务信息</h2>
          <div class="mt-3 space-y-2 text-sm text-slate-700">
            <p><span class="font-medium">任务ID：</span>{{ job.job_id }}</p>
            <p><span class="font-medium">状态：</span>{{ job.status }}</p>
            <p><span class="font-medium">进度：</span>{{ progressText }}</p>
          </div>
          <div class="w-full bg-slate-200 rounded-full h-3 mt-4 overflow-hidden">
            <div class="bg-emerald-500 h-3 transition-all duration-300" :style="{ width: (job.progress || 0) + '%' }"></div>
          </div>
        </div>

        <div class="p-5 border rounded-xl">
          <h2 class="text-lg font-semibold">字段确认</h2>
          <p class="text-sm text-slate-500 mt-2">候选地址字段：{{ (job.suggested_address_columns || []).join('、') || '无' }}</p>
          <input class="mt-3 w-full border rounded-lg p-2" v-model="targetColumn" placeholder="输入要提取的列名" />
          <input class="mt-3 w-full border rounded-lg p-2" v-model="prefix" placeholder="输出字段前缀" />
          <button class="mt-4 px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50" @click="startProcess" :disabled="loading || !targetColumn">
            确认并开始提取
          </button>
        </div>
      </div>

      <div v-if="job" class="mt-6 p-5 border rounded-xl">
        <h2 class="text-lg font-semibold">表头字段</h2>
        <div class="mt-3 flex flex-wrap gap-2">
          <span v-for="c in job.columns" :key="c" class="px-3 py-1 text-sm bg-slate-100 rounded-full border">{{ c }}</span>
        </div>
      </div>

      <div v-if="job && job.status === 'completed'" class="mt-6 p-5 rounded-xl bg-emerald-50 border border-emerald-200">
        <p class="font-semibold text-emerald-700">处理完成 ✅</p>
        <p class="text-sm text-emerald-800 mt-1">输出文件：{{ job.output_path }}</p>
      </div>
    </div>
  </div>
  `
}).mount('#app')
