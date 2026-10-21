(() => {
  const field = document.getElementById('guide-search');
  if (!field) return;
  const rows = [...document.querySelectorAll('[data-guide-name]')];
  const status = document.getElementById('filter-status');
  const normalize = value => value.replace(/[\s·\-_]/g, '').toLocaleLowerCase('ko-KR');
  field.addEventListener('input', () => {
    const query = normalize(field.value);
    let count = 0;
    rows.forEach(row => { row.hidden = !normalize(row.dataset.guideName).includes(query); if (!row.hidden) count++; });
    document.querySelectorAll('.clinical-index-group').forEach(group => { group.hidden = ![...group.querySelectorAll('[data-guide-name]')].some(row => !row.hidden); });
    status.textContent = count + '개 항목' + (count ? '' : ' · 다른 이름으로 찾아보세요.');
  });
})();
