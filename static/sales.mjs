export const yen = value => new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY', maximumFractionDigits: 0 }).format(value);
export const sum = rows => rows.reduce((total, row) => total + row.amount, 0);
export function aggregate(rows, unit) {
  const totals = new Map();
  for (const row of rows) {
    const key = unit === 'monthly' ? row.date.slice(0, 7) : row.date;
    totals.set(key, (totals.get(key) || 0) + row.amount);
  }
  return [...totals].sort(([a], [b]) => a.localeCompare(b));
}
export function filterSales(rows, query, from, to) {
  if (from && to && from > to) return [];
  return rows.filter(row => row.product.toLocaleLowerCase('ja').includes(query.trim().toLocaleLowerCase('ja')) && (!from || row.date >= from) && (!to || row.date <= to));
}
export function japanToday(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(now);
  const get = type => parts.find(part => part.type === type).value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}
