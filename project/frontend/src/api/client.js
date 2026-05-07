import axios from 'axios'

const baseURL = window.APP_CONFIG?.API_BASE_URL || 'http://localhost:8000'
const api = axios.create({ baseURL })
export default api
