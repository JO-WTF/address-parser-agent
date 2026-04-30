const { createApp, ref } = Vue

createApp({
  setup() {
    const file = ref(null)
    const job = ref(null)
    const targetColumn = ref("")
    const prefix = ref("parsed")
    const loading = ref(false)

    const upload = async () => {
      if (!file.value) return
      loading.value = true
      const form = new FormData()
      form.append('file', file.value)
      const res = await fetch('http://localhost:8000/api/upload', { method: 'POST', body: form })
      job.value = await res.json()
      targetColumn.value = job.value.suggested_address_columns?.[0] || ''
      loading.value = false
    }

    const confirm = async () => {
      if (!job.value || !targetColumn.value) return
      loading.value = true
      const res = await fetch('http://localhost:8000/api/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: job.value.job_id, target_column: targetColumn.value, output_columns_prefix: prefix.value })
      })
      job.value = await res.json()
      loading.value = false
    }

    return { file, job, targetColumn, prefix, loading, upload, confirm }
  },
  template: `
  <div style="max-width:800px;margin:2rem auto;font-family:Arial">
    <h2>Excel 客户地址提取 Agent</h2>
    <input type="file" accept=".xlsx,.xls" @change="e => file = e.target.files[0]" />
    <button @click="upload" :disabled="loading">上传并分析</button>

    <div v-if="job" style="margin-top:1rem">
      <p><b>任务ID:</b> {{job.job_id}}</p>
      <p><b>状态:</b> {{job.status}} | <b>进度:</b> {{job.progress}}%</p>
      <p><b>字段:</b> {{job.columns.join(', ')}}</p>
      <p><b>猜测地址字段:</b> {{job.suggested_address_columns.join(', ') || '无'}}</p>
      <label>选择待提取字段：</label>
      <input v-model="targetColumn" placeholder="列名" />
      <label>输出前缀：</label>
      <input v-model="prefix" />
      <button @click="confirm" :disabled="loading">确认并提取</button>
      <div v-if="job.status==='completed'">
        <p>处理完成，输出文件：{{job.output_path}}</p>
      </div>
    </div>
  </div>
  `
}).mount('#app')
