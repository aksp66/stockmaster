const API_BASE = '/api/v1';
let token = localStorage.getItem('access_token');

async function apiCall(endpoint, method, body) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const resp = await fetch(`${API_BASE}${endpoint}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (resp.status === 401) window.location = '/comptes/connexion/';
  return resp.json();
}
window.StockMasterAPI = { apiCall };