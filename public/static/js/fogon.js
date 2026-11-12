/* =====================================================================
   EL FOGÓN BUMANGUÉS — fogon.js · v1.0
   JavaScript nativo, sin dependencias (~11 KB, ~4 KB con gzip). Cargar con defer.
   No toca formularios ni rutas: solo añade/quita clases y muestra avisos.

   API pública (window.FG):
     FG.toast(mensaje, { tipo: 'ok' | 'error' | 'info', duracion: 3500 })
     FG.confirmar(mensaje)            → check animado + aviso
     FG.error(campoOSelector, msg)    → marca .fg-field inválido + sacudida + foco
     FG.limpiarError(campoOSelector)
     FG.sacudir(elemento)
     FG.pulso(elemento)
     FG.contar(elemento, valorFinal, { dur, desde })
     FG.progreso.inicio() / FG.progreso.fin()
     FG.cargando(contenedor, true|false)   → aria-busy para esqueletos
     FG.tema('dark' | 'light' | 'alternar')
     FG.cop(numero) → "$16.000"
   ===================================================================== */
(function () {
  'use strict';
  var FG = window.FG = window.FG || {};
  var doc = document, root = doc.documentElement;

  function reduce() { return !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches); }
  function $(x) { return typeof x === 'string' ? doc.querySelector(x) : x; }
  function store(kind, k, v) {
    try { var s = window[kind]; if (v === undefined) return s.getItem(k); s.setItem(k, v); } catch (e) { return null; }
  }
  function restart(el, a, b) {
    if (!el) return;
    var useB = el.classList.contains(a);
    el.classList.remove(a, b);
    el.classList.add(useB ? b : a);
  }

  /* ---------- Formato de pesos colombianos ---------- */
  FG.cop = function (n) {
    n = Math.round(Number(n) || 0);
    var s = String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return (n < 0 ? '−$' : '$') + s;
  };
  FG.leerCop = function (txt) { var d = String(txt || '').replace(/[^\d-]/g, ''); return d ? parseInt(d, 10) : 0; };

  /* ---------- Tema ---------- */
  FG.tema = function (t) {
    var actual = root.getAttribute('data-theme') || 'dark';
    if (t === 'alternar') t = actual === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', t);
    store('localStorage', 'fg:tema', t);
    var meta = doc.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', t === 'light' ? '#f7f2ea' : '#0f0f0f');
    doc.querySelectorAll('[data-fg-tema]').forEach(function (b) {
      b.setAttribute('aria-label', t === 'light' ? 'Cambiar a modo oscuro' : 'Cambiar a modo claro');
    });
  };

  /* ---------- Pantalla de carga (una vez por sesión) ---------- */
  function splash() {
    var el = doc.querySelector('.fg-splash');
    if (!el) return;
    if (root.classList.contains('fg-no-splash') || reduce()) { el.remove(); return; }
    store('sessionStorage', 'fg:splash', '1');
    var quitar = function () { if (el.parentNode) el.remove(); };
    el.addEventListener('animationend', function (e) { if (e.target === el) quitar(); });
    setTimeout(quitar, 1600); /* respaldo */
  }

  /* ---------- Barra de progreso superior ---------- */
  var bar, barTimer;
  function getBar() {
    if (!bar) { bar = doc.querySelector('.fg-progress'); if (!bar) { bar = doc.createElement('div'); bar.className = 'fg-progress'; bar.setAttribute('aria-hidden', 'true'); doc.body.appendChild(bar); } }
    return bar;
  }
  FG.progreso = {
    inicio: function () { var b = getBar(); clearTimeout(barTimer); b.classList.remove('is-done'); void b.offsetWidth; b.classList.add('is-loading'); },
    fin: function () { var b = getBar(); b.classList.add('is-done'); barTimer = setTimeout(function () { b.classList.remove('is-loading', 'is-done'); }, 400); }
  };
  function enlacesConProgreso() {
    doc.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('a[href]');
      if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (a.target === '_blank' || a.hasAttribute('download') || a.getAttribute('href').charAt(0) === '#') return;
      if (a.origin !== location.origin || a.hasAttribute('data-fg-sin-progreso')) return;
      FG.progreso.inicio();
    });
    doc.addEventListener('submit', function (e) { if (!e.defaultPrevented) FG.progreso.inicio(); });
    window.addEventListener('pageshow', function () { if (bar) FG.progreso.fin(); });
  }

  /* ---------- Avisos (toast) ---------- */
  function caja() {
    var c = doc.querySelector('.fg-toasts');
    if (!c) { c = doc.createElement('div'); c.className = 'fg-toasts'; c.setAttribute('aria-live', 'polite'); doc.body.appendChild(c); }
    return c;
  }
  FG.toast = function (msg, op) {
    op = op || {};
    var tipo = op.tipo || 'info', dur = op.duracion || (tipo === 'error' ? 5000 : 3500);
    var t = doc.createElement('div');
    t.className = 'fg-toast fg-toast--' + tipo;
    t.setAttribute('role', tipo === 'error' ? 'alert' : 'status');
    var ico = doc.createElement('span'); ico.className = 'fg-toast__icon'; ico.setAttribute('aria-hidden', 'true');
    ico.textContent = tipo === 'ok' ? '✓' : (tipo === 'error' ? '!' : 'i');
    var txt = doc.createElement('span'); txt.textContent = msg;
    var x = doc.createElement('button'); x.type = 'button'; x.className = 'fg-btn fg-btn--ghost fg-btn--icon fg-toast__close'; x.setAttribute('aria-label', 'Cerrar aviso'); x.textContent = '×';
    t.append(ico, txt, x);
    caja().appendChild(t);
    var cerrar = function () {
      if (t.classList.contains('is-leaving')) return;
      if (reduce()) { t.remove(); return; }
      t.classList.add('is-leaving');
      t.addEventListener('animationend', function () { t.remove(); }, { once: true });
      setTimeout(function () { t.remove(); }, 400);
    };
    x.addEventListener('click', cerrar);
    var timer = setTimeout(cerrar, dur);
    t.addEventListener('mouseenter', function () { clearTimeout(timer); });
    t.addEventListener('mouseleave', function () { timer = setTimeout(cerrar, 1500); });
    return t;
  };

  /* Mensajes flash de Flask: <div class="fg-flash" data-tipo="ok" hidden>Texto</div> */
  function flashes() {
    doc.querySelectorAll('.fg-flash').forEach(function (f) {
      FG.toast(f.textContent.trim(), { tipo: f.getAttribute('data-tipo') || 'info' });
      f.remove();
    });
  }

  /* ---------- Confirmación con check ---------- */
  FG.confirmar = function (msg) {
    var o = doc.createElement('div');
    o.className = 'fg-confirm'; o.setAttribute('aria-hidden', 'true');
    o.innerHTML = '<div class="fg-confirm__box"><span class="fg-check"></span><span></span></div>';
    o.querySelector('span + span').textContent = msg || 'Listo';
    doc.body.appendChild(o);
    setTimeout(function () { o.classList.add('is-leaving'); setTimeout(function () { o.remove(); }, 200); }, 800);
    FG.toast(msg || 'Listo', { tipo: 'ok' });
  };

  /* ---------- Errores de campo ---------- */
  FG.sacudir = function (el) { el = $(el); if (el && !reduce()) restart(el, 'is-shake', 'is-shake-alt'); };
  FG.pulso = function (el) { el = $(el); if (el && !reduce()) restart(el, 'is-pulse', 'is-pulse-alt'); };

  FG.error = function (campo, msg) {
    var f = $(campo); if (!f) return;
    if (!f.classList.contains('fg-field')) f = f.closest('.fg-field') || f;
    var input = f.querySelector('input, select, textarea');
    var err = f.querySelector('.fg-error');
    if (!err) { err = doc.createElement('p'); err.className = 'fg-error'; f.appendChild(err); }
    if (!err.id) err.id = 'fg-err-' + Math.random().toString(36).slice(2, 8);
    err.textContent = msg || '';
    err.setAttribute('role', 'alert');
    f.classList.add('is-invalid');
    if (input) { input.setAttribute('aria-invalid', 'true'); input.setAttribute('aria-describedby', err.id); input.focus({ preventScroll: false }); }
    FG.sacudir(f);
  };
  FG.limpiarError = function (campo) {
    var f = $(campo); if (!f) return;
    if (!f.classList.contains('fg-field')) f = f.closest('.fg-field') || f;
    f.classList.remove('is-invalid', 'is-shake', 'is-shake-alt');
    var input = f.querySelector('[aria-invalid]'); if (input) input.removeAttribute('aria-invalid');
    var err = f.querySelector('.fg-error'); if (err) err.textContent = '';
  };
  /* Al escribir en un campo marcado, se limpia solo */
  doc.addEventListener('input', function (e) { var f = e.target.closest && e.target.closest('.fg-field.is-invalid'); if (f) FG.limpiarError(f); });

  /* ---------- Conteo animado ---------- */
  FG.contar = function (el, hasta, op) {
    el = $(el); if (!el) return;
    op = op || {};
    var desde = op.desde != null ? op.desde : (el._fgValor != null ? el._fgValor : 0);
    var dur = op.dur != null ? op.dur : 200;
    var fmt = op.formato || FG.cop;
    cancelAnimationFrame(el._fgRaf);
    el._fgValor = hasta;
    if (reduce() || dur <= 0 || desde === hasta) { el.textContent = fmt(hasta); return; }
    var t0 = performance.now();
    var paso = function (t) {
      var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(desde + (hasta - desde) * e);
      if (p < 1) el._fgRaf = requestAnimationFrame(paso);
    };
    el._fgRaf = requestAnimationFrame(paso);
  };
  /* Auto: <span data-fg-count="192500" data-fg-dur="700">$192.500</span> */
  function contadores() {
    doc.querySelectorAll('[data-fg-count]').forEach(function (el) {
      var v = Number(el.getAttribute('data-fg-count'));
      var dur = Number(el.getAttribute('data-fg-dur') || 700);
      var entero = el.hasAttribute('data-fg-entero');
      FG.contar(el, v, { desde: 0, dur: dur, formato: entero ? function (n) { return String(Math.round(n)); } : function (n) { return FG.cop(Math.round(n / 100) * 100); } });
      setTimeout(function () { el.textContent = entero ? String(v) : FG.cop(v); }, dur + 50);
    });
  }

  /* ---------- Esqueletos ---------- */
  FG.cargando = function (cont, si) { cont = $(cont); if (cont) cont.setAttribute('aria-busy', si ? 'true' : 'false'); };

  /* ---------- Hoja inferior de la cuenta (Nueva venta en celular) ---------- */
  function hoja() {
    doc.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('[data-fg-hoja]');
      if (!b) return;
      var t = b.closest('.fg-ticket'); if (!t) return;
      var abierta = t.classList.toggle('is-open');
      b.setAttribute('aria-expanded', abierta ? 'true' : 'false');
    });
  }

  /* ---------- Botón de tema ---------- */
  function botonesTema() {
    doc.addEventListener('click', function (e) { var b = e.target.closest && e.target.closest('[data-fg-tema]'); if (b) FG.tema('alternar'); });
    FG.tema(root.getAttribute('data-theme') || 'dark');
  }

  function init() { splash(); enlacesConProgreso(); hoja(); botonesTema(); flashes(); contadores(); }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', init); else init();
})();
