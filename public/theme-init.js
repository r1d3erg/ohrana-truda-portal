// Тема до отрисовки, чтобы не было вспышки светлого/тёмного фона (см. src/theme.js)
(function () {
  var pref = 'system'
  try { pref = localStorage.getItem('ot-theme') || 'system' } catch (e) {}
  var light = pref === 'light' || (pref === 'system' && window.matchMedia && matchMedia('(prefers-color-scheme: light)').matches)
  document.documentElement.dataset.theme = light ? 'light' : 'dark'
})()
