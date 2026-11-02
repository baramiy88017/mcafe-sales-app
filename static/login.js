const form = document.getElementById('login-form');
const error = document.getElementById('login-error');
const button = document.getElementById('login-button');
let csrf;
async function initialize() {
  const response = await fetch('/api/session');
  if (!response.ok) throw new Error('接続できませんでした。画面を再読み込みしてください。');
  const state = await response.json();
  if (state.authenticated) { location.replace('/'); return; }
  csrf = state.csrf;
  button.disabled = false;
  button.textContent = 'ログイン';
}
initialize().catch(err => { error.textContent = err.message; error.hidden = false; });
form.addEventListener('submit', async event => {
  event.preventDefault();
  button.disabled = true;
  button.textContent = 'ログイン中…';
  error.hidden = true;
  try {
    const response = await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify({username:form.username.value,password:form.password.value})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'ログインできませんでした。');
    location.replace('/');
  } catch(err) {
    error.textContent = err.message === 'Failed to fetch' ? '接続できませんでした。もう一度お試しください。' : err.message;
    error.hidden = false;
    form.password.value = '';
    form.password.focus();
  } finally { button.disabled = false; button.textContent = 'ログイン'; }
});
