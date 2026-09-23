/* Accès à l'API. Une seule place où l'on parle au backend. */

const API = (() => {
  async function call(path, options) {
    const res = await fetch(path, options);
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const body = await res.json();
        if (body.detail) detail = JSON.stringify(body.detail);
      } catch { /* la réponse n'était pas du JSON : on garde le statut */ }
      throw new Error(detail);
    }
    return res.json();
  }

  const post = (path, body) => call(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  return {
    instance: () => call('/api/instance'),
    solve: (params) => post('/api/solve', params),
    complexity: (params) => post('/api/complexity', params),
  };
})();
