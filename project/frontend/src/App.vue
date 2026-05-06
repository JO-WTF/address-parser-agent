<template>
  <div style="max-width:900px;margin:30px auto;">
    <h2>Excel处理Agent</h2>
    <el-upload :auto-upload="false" :on-change="onFileChange" :limit="1"><el-button>选择Excel</el-button></el-upload>
    <el-button @click="upload" :disabled="!file">上传</el-button>
    <p>task_id: {{ taskId }}</p>
    <el-button @click="loadHeaders" :disabled="!taskId">获取表头</el-button>
    <pre>{{ headers }}</pre>
    <el-button @click="analyze" :disabled="headers.length===0">LLM猜测详细地址字段</el-button>
    <pre>{{ fields }}</pre>
    <el-form label-width="120px">
      <el-form-item label="address_field"><el-input v-model="fields.address_field"/></el-form-item>
    </el-form>
    <el-button @click="run" :disabled="!fields.address_field">启动任务</el-button>
    <el-progress :percentage="Math.round(progress*100)"/>
    <p>{{ current }}/{{ total }} | {{ status }}</p>
    <el-button @click="download" :disabled="status!=='completed'">下载结果</el-button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import api from './api/client'

const file = ref(null), taskId = ref(''), headers = ref([]), status = ref('idle')
const progress = ref(0), current = ref(0), total = ref(0)
const fields = ref({address_field:''})
let ws = null

const onFileChange = (f)=> file.value=f.raw
const upload = async()=>{ const fd=new FormData(); fd.append('file', file.value); const r=await api.post('/upload', fd); taskId.value=r.data.task_id }
const loadHeaders = async()=>{ const r=await api.get(`/headers/${taskId.value}`); headers.value=r.data.headers }
const analyze = async()=>{ const r=await api.post('/analyze', {headers: headers.value}); fields.value=r.data }
const run = async()=>{
  await api.post('/run', {task_id:taskId.value, address_field:fields.value.address_field})
  status.value='running'
  ws = new WebSocket(`${window.APP_CONFIG?.WS_BASE_URL || 'ws://localhost:8000'}/ws/task/${taskId.value}`)
  ws.onmessage = (e)=>{ const d=JSON.parse(e.data); if(d.progress!=null) progress.value=d.progress; current.value=d.current||current.value; total.value=d.total||total.value; if(d.status) status.value=d.status }
}
const download = ()=> window.open(`${window.APP_CONFIG?.API_BASE_URL || 'http://localhost:8000'}/download/${taskId.value}`)
</script>
