import test from 'node:test';
import assert from 'node:assert/strict';
import {aggregate, filterSales, japanToday, sum} from '../static/sales.mjs';
const rows = [
  {date:'2026-11-02',product:'カフェラテ',amount:550},
  {date:'2026-11-02',product:'ケーキ',amount:650},
  {date:'2026-11-01',product:'Coffee',amount:400},
  {date:'2026-10-31',product:'カフェラテ',amount:500},
];
test('daily and monthly totals combine records by calendar date', () => {
  assert.deepEqual(aggregate(rows,'daily'), [['2026-10-31',500],['2026-11-01',400],['2026-11-02',1200]]);
  assert.deepEqual(aggregate(rows,'monthly'), [['2026-10',500],['2026-11',1600]]);
  assert.equal(sum(rows),2100);
  assert.deepEqual(aggregate([],'daily'),[]);
});
test('filters combine product and inclusive date boundaries', () => {
  assert.deepEqual(filterSales(rows,'カフェ','2026-11-02','2026-11-02'),[rows[0]]);
  assert.deepEqual(filterSales(rows,' coffee ','',''),[rows[2]]);
  assert.deepEqual(filterSales(rows,'','2026-11-03','2026-11-01'),[]);
  assert.deepEqual(filterSales(rows,'該当なし','',''),[]);
});
test('edits and deletions update totals', () => {
  const edited = rows.map((row,i) => i === 0 ? {...row,date:'2026-10-31',amount:600} : row);
  assert.deepEqual(aggregate(edited,'monthly'),[['2026-10',1100],['2026-11',1050]]);
  assert.deepEqual(aggregate(edited.filter((_,i) => i !== 0),'monthly'),[['2026-10',500],['2026-11',1050]]);
});
test('today switches at midnight in Japan', () => {
  assert.equal(japanToday(new Date('2026-11-01T14:59:59Z')),'2026-11-01');
  assert.equal(japanToday(new Date('2026-11-01T15:00:00Z')),'2026-11-02');
});
