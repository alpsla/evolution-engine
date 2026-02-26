// Evolution Engine — Internationalization (i18n)
// Vanilla JS, no build tools. Loads JSON translation files and applies them
// to elements with data-i18n attributes.

(function () {
  'use strict';

  var SUPPORTED_LANGS = ['en', 'de', 'es'];
  var STORAGE_KEY = 'evo_lang';
  var translations = null;
  var currentLang = 'en';

  // ─── Language detection ───
  function detectLanguage() {
    // 1. Check localStorage
    var stored = localStorage.getItem(STORAGE_KEY);
    if (stored && SUPPORTED_LANGS.indexOf(stored) !== -1) {
      return stored;
    }

    // 2. Auto-detect from browser
    var browserLang = (navigator.language || navigator.userLanguage || 'en').toLowerCase();
    // Check exact match first (e.g. "de"), then prefix (e.g. "de-AT" -> "de")
    for (var i = 0; i < SUPPORTED_LANGS.length; i++) {
      if (browserLang === SUPPORTED_LANGS[i] || browserLang.indexOf(SUPPORTED_LANGS[i] + '-') === 0) {
        return SUPPORTED_LANGS[i];
      }
    }

    // 3. Default to English
    return 'en';
  }

  // ─── Resolve nested key like "hero.title" from translations object ───
  function resolve(obj, keyPath) {
    var keys = keyPath.split('.');
    var val = obj;
    for (var i = 0; i < keys.length; i++) {
      if (val == null || typeof val !== 'object') return null;
      val = val[keys[i]];
    }
    return val != null ? val : null;
  }

  // ─── Apply translations to the DOM ───
  function applyTranslations(t) {
    var elements = document.querySelectorAll('[data-i18n]');
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      var key = el.getAttribute('data-i18n');
      var value = resolve(t, key);
      if (value == null) continue;

      // Determine target attribute
      var attr = el.getAttribute('data-i18n-attr');
      if (attr === 'placeholder') {
        el.placeholder = value;
      } else if (attr === 'aria-label') {
        el.setAttribute('aria-label', value);
      } else if (el.tagName === 'OPTION') {
        // <option> elements: use textContent to avoid HTML parsing issues
        el.textContent = value;
      } else if (el.tagName === 'CODE' && el.parentElement && el.parentElement.tagName === 'PRE') {
        // <code> inside <pre>: use textContent to preserve newlines and whitespace
        el.textContent = value;
      } else {
        // Default: set innerHTML (allows inline <code> tags in translations)
        el.innerHTML = value;
      }
    }

    // Handle "Most Popular" badge on the featured pricing card (CSS ::before content)
    var popularCard = document.querySelector('[data-i18n-popular]');
    if (popularCard) {
      var popularKey = popularCard.getAttribute('data-i18n-popular');
      var popularText = resolve(t, popularKey);
      if (popularText) {
        popularCard.style.setProperty('--popular-text', '"' + popularText + '"');
      }
    }

    // Update the html lang attribute
    document.documentElement.lang = currentLang;

    // Update active state on language selector buttons
    var langBtns = document.querySelectorAll('.lang-btn');
    for (var j = 0; j < langBtns.length; j++) {
      var btn = langBtns[j];
      if (btn.getAttribute('data-lang') === currentLang) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    }
  }

  // ─── Load translations and apply ───
  function loadLanguage(lang) {
    currentLang = lang;
    localStorage.setItem(STORAGE_KEY, lang);

    // Use absolute path so it works from any page context (/, /docs, etc.)
    var basePath = '/i18n/' + lang + '.json';

    fetch(basePath)
      .then(function (res) {
        if (!res.ok) throw new Error('Failed to load ' + basePath);
        return res.json();
      })
      .then(function (t) {
        translations = t;
        // Expose translations globally so script.js _t() helper can use them
        window.__evo_i18n = t;
        applyTranslations(t);
      })
      .catch(function (err) {
        console.warn('[i18n] Could not load translations for "' + lang + '":', err.message);
        // Fallback to English if the requested language fails and it's not already English
        if (lang !== 'en') {
          loadLanguage('en');
        }
      });
  }

  // ─── Switch language (called from language selector buttons) ───
  window.switchLanguage = function (lang) {
    if (SUPPORTED_LANGS.indexOf(lang) === -1) return;
    loadLanguage(lang);
  };

  // ─── Initialize on DOM ready ───
  function init() {
    var lang = detectLanguage();
    loadLanguage(lang);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
