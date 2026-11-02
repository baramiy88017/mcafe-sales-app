import { yen, sum, aggregate, filterSales, japanToday } from './sales.mjs';

const $ = id => document.getElementById(id);
let sales = [], unit = 'daily', editingId = null, deletingId = null, busy = false, toastTimer;
let csrf = '';
const today = japanToday();
$('today').textContent = new Intl.DateTimeFormat('ja-JP', { dateStyle: 'full', timeZone: 'Asia/Tokyo' }).format(new Date());

async function api(path = '/api/sales', options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...options.headers } });
  if (response.status === 401) { location.replace('/login'); throw new Error('ログインしてください。'); }
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || '操作に失敗しました。');
  return body;
}
function notify(message) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 4000);
}
async function load() {
  try {
    sales = await api();
    $('load-error').hidden = true;
    render();
    return true;
  } catch {
    $('load-error').querySelector('span').textContent = '売上を読み込めませんでした。接続を確認して再読み込みしてください。';
    $('load-error').hidden = false;
    return false;
  }
}
function cell(text, className = '') {
  const el = document.createElement('td');
  el.textContent = text;
  el.className = className;
  return el;
}
function render() {
  for (const [key, rows] of [['today', sales.filter(s => s.date === today)], ['month', sales.filter(s => s.date.startsWith(today.slice(0, 7)))], ['all', sales]]) {
    $(`${key}-total`).textContent = yen(sum(rows));
    $(`${key}-count`).textContent = `${rows.length.toLocaleString('ja-JP')}件の売上`;
  }
  renderChart();
  renderList();
}
function renderChart() {
  const buckets = aggregate(sales, unit).slice(-(unit === 'daily' ? 7 : 6));
  $('chart').replaceChildren();
  $('chart-empty').hidden = buckets.length > 0;
  $('chart').hidden = !buckets.length;
  $('summary-note').textContent = unit === 'daily' ? '売上がある日の直近7日分を表示' : '売上がある月の直近6か月分を表示';
  const maximum = Math.max(...buckets.map(([, total]) => total), 1);
  for (const [day, total] of buckets) {
    const row = document.createElement('div');
    row.className = 'chart-row';
    const label = document.createElement('span');
    label.className = 'chart-label';
    label.textContent = unit === 'daily' ? `${Number(day.slice(5, 7))}/${Number(day.slice(8))}` : `${day.slice(0, 4)}/${day.slice(5)}`;
    const meter = document.createElement('meter');
    meter.min = 0; meter.max = maximum; meter.value = total;
    meter.setAttribute('aria-label', `${day} ${yen(total)}`);
    const value = document.createElement('strong'); value.textContent = yen(total);
    row.append(label, meter, value);
    $('chart').append(row);
  }
}
function renderList() {
  const from = $('from').value, to = $('to').value;
  $('filter-error').hidden = !(from && to && from > to);
  const rows = filterSales(sales, $('search').value, from, to);
  $('record-count').textContent = `${rows.length}件`;
  $('filtered-total').textContent = yen(sum(rows));
  $('sales-body').replaceChildren();
  for (const sale of rows) {
    const row = document.createElement('tr');
    const actions = cell('', 'row-actions');
    for (const [text, className, callback] of [['編集', 'edit-button', () => openForm(sale)], ['削除', 'delete-button', () => openDelete(sale)]]) {
      const button = document.createElement('button');
      button.textContent = text;
      button.className = className;
      button.setAttribute('aria-label', `${sale.date} ${sale.product}を${text}`);
      button.addEventListener('click', callback);
      actions.append(button);
    }
    row.append(cell(sale.date.replaceAll('-', '/'), 'date-cell'), cell(sale.product), cell(yen(sale.amount), 'amount'), actions);
    $('sales-body').append(row);
  }
  $('list-empty').hidden = rows.length > 0;
  $('list-empty').querySelector('h3').textContent = sales.length ? '条件に一致する売上がありません' : 'まだ売上がありません';
  $('list-empty').querySelector('p').textContent = sales.length ? '検索条件や期間を変更してみてください。' : '「売上を登録」から、最初の1件を記録しましょう。';
}
function openForm(sale = null) {
  editingId = sale?.id ?? null;
  $('sale-form').reset();
  $('sale-date').value = sale?.date ?? japanToday();
  $('sale-product').value = sale?.product ?? '';
  $('sale-amount').value = sale?.amount ?? '';
  $('dialog-title').textContent = sale ? '売上を編集' : '売上を登録';
  $('save-sale').textContent = sale ? '変更を保存' : '登録する';
  $('form-error').hidden = true;
  $('sale-dialog').showModal();
}
function openDelete(sale) {
  deletingId = sale.id;
  $('delete-description').textContent = `${sale.date.replaceAll('-', '/')} · ${sale.product} · ${yen(sale.amount)}`;
  $('delete-error').hidden = true;
  $('delete-dialog').showModal();
}
function setBusy(value) {
  busy = value;
  for (const dialog of [$('sale-dialog'), $('delete-dialog')]) {
    dialog.querySelectorAll('button, input').forEach(el => { el.disabled = value; });
  }
}
$('sale-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const data = {date: $('sale-date').value, product: $('sale-product').value.trim(), amount: $('sale-amount').value};
  const wasEditing = editingId !== null;
  setBusy(true);
  $('form-error').hidden = true;
  try {
    await api(wasEditing ? `/api/sales/${editingId}` : '/api/sales', {method: wasEditing ? 'PUT' : 'POST', body: JSON.stringify(data)});
    $('sale-dialog').close();
    notify(wasEditing ? '売上を変更しました。' : '売上を登録しました。');
    await load();
  } catch (error) {
    $('form-error').textContent = error.message;
    $('form-error').hidden = false;
  } finally { setBusy(false); }
});
$('delete-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  setBusy(true);
  try {
    await api(`/api/sales/${deletingId}`, {method: 'DELETE'});
    $('delete-dialog').close();
    notify('売上を削除しました。');
    await load();
  } catch (error) {
    $('delete-error').textContent = error.message;
    $('delete-error').hidden = false;
  } finally { setBusy(false); }
});
$('add-sale').addEventListener('click', () => openForm());
for (const id of ['close-dialog', 'cancel-dialog']) $(id).addEventListener('click', () => $('sale-dialog').close());
$('cancel-delete').addEventListener('click', () => $('delete-dialog').close());
for (const id of ['sale-dialog', 'delete-dialog']) $(id).addEventListener('cancel', event => { if (busy) event.preventDefault(); });
for (const id of ['search', 'from', 'to']) $(id).addEventListener('input', renderList);
$('reset-filters').addEventListener('click', () => { for (const id of ['search', 'from', 'to']) $(id).value = ''; renderList(); });
for (const id of ['daily', 'monthly']) $(id).addEventListener('click', () => {
  unit = id;
  $('daily').setAttribute('aria-pressed', String(unit === 'daily'));
  $('monthly').setAttribute('aria-pressed', String(unit === 'monthly'));
  renderChart();
});
$('retry').addEventListener('click', load);
async function initialize() {
  const state = await api('/api/session');
  if (!state.authenticated) { location.replace('/login'); return; }
  csrf = state.csrf;
  $('account-name').textContent = state.username;
  await load();
}
$('logout').addEventListener('click', async () => {
  $('logout').disabled = true;
  try {
    await api('/api/logout', {method: 'POST', body: '{}'});
    location.replace('/login');
  } catch { notify('ログアウトできませんでした。もう一度お試しください。'); }
  finally { $('logout').disabled = false; }
});
initialize().catch(() => {
  $('load-error').querySelector('span').textContent = '接続できませんでした。画面を再読み込みしてください。';
  $('load-error').hidden = false;
});
