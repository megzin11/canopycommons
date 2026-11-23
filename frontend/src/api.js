async function request(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`API ${res.status}: ${errText}`);
  }
  return res.json();
}

export const api = {
  getCities: () => request('/api/cities'),
  getCityGrid: (city) => request(`/api/cities/${city}/grid`),
  getInterventions: () => request('/api/interventions'),
  simulate: (payload) =>
    request('/api/simulate', { method: 'POST', body: JSON.stringify(payload) }),
  optimize: (payload) =>
    request('/api/optimize', { method: 'POST', body: JSON.stringify(payload) }),
  getFeedback: (city) => request(`/api/feedback/${city}`),
  postFeedback: (payload) =>
    request('/api/feedback', { method: 'POST', body: JSON.stringify(payload) }),
  runDeliberation: (city, useLive = true) =>
    request(`/api/deliberation/${city}?use_live_llm=${useLive}`, { method: 'POST' }),
  exportDossier: (payload) =>
    request('/api/dossier', { method: 'POST', body: JSON.stringify(payload) }),
};