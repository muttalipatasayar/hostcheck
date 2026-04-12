import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Tickets
export const ticketsApi = {
  list: (params = {}) => api.get('/tickets/', { params }),
  get: (id) => api.get(`/tickets/${id}`),
  create: (data) => api.post('/tickets/', data),
  update: (id, data) => api.patch(`/tickets/${id}`, data),
  delete: (id) => api.delete(`/tickets/${id}`),
  saveCheckResults: (id, results) => api.patch(`/tickets/${id}/check-results`, results),
  saveAiResponse: (id, response) => api.patch(`/tickets/${id}/ai-response`, { response }),
}

// Checks
export const checksApi = {
  run: (data) => api.post('/checks/run', data),
}

// AI
export const aiApi = {
  generate: (data) => api.post('/ai/generate', data),
}

export default api
