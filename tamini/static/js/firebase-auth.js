/**
 * Firebase Phone Authentication for Tamini (template frontend).
 *
 * Exposes `window.TaminiPhoneAuth` with:
 *   .init(options)   – bind to a container element
 *   .sendCode()      – send SMS
 *   .verifyCode(code) – verify user-entered code
 *
 * Flow:
 *   1. init() renders phone input + buttons inside the container
 *   2. sendCode() → Firebase sends SMS, shows code input
 *   3. verifyCode() → verifies, POSTs id_token to backend, redirects
 */
(function () {
  'use strict';

  var auth = window.taminiAuth;
  if (!auth) {
    console.warn('TaminiPhoneAuth: firebase auth not initialised.');
    return;
  }

  var confirmationResult = null;
  var recaptchaVerifier = null;
  var config = {};

  /* ── helpers ──────────────────────────────────────────────────── */

  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === 'className') e.className = attrs[k];
      else if (k === 'innerHTML') e.innerHTML = attrs[k];
      else if (k.indexOf('on') === 0) e.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
      else e.setAttribute(k, attrs[k]);
    });
    if (children) children.forEach(function (c) { if (c) e.appendChild(c); });
    return e;
  }

  function msg(text, type) {
    var c = config.container;
    var old = c.querySelector('.tpa-msg');
    if (old) old.remove();
    var cls = type === 'error'
      ? 'tpa-msg text-red-600 bg-red-50 border border-red-200'
      : 'tpa-msg text-green-700 bg-green-50 border border-green-200';
    var d = el('div', { className: cls + ' text-sm p-3 rounded-xl mt-3 text-center' });
    d.textContent = text;
    c.appendChild(d);
  }

  function setLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
      btn.dataset.origText = btn.textContent;
      btn.disabled = true;
      btn.textContent = config.loadingText || '...';
    } else {
      btn.disabled = false;
      btn.textContent = btn.dataset.origText || btn.textContent;
    }
  }

  /* ── public API ───────────────────────────────────────────────── */

  function init(opts) {
    config = Object.assign({
      container: null,
      locale: 'ar',
      loginUrl: '/accounts/firebase-login/',
      successRedirect: '/',
      loadingText: '...',
      sendButtonText: 'إرسال كود التحقق',
      verifyButtonText: 'تسجيل الدخول',
      resendButtonText: 'إعادة الإرسال',
      phonePlaceholder: '+963 9XX XXX XXX',
    }, opts || {});

    if (!config.container) {
      console.error('TaminiPhoneAuth.init: container is required.');
      return;
    }

    var c = config.container;
    c.innerHTML = '';

    // phone input row
    var phoneRow = el('div', { className: 'flex gap-2' }, [
      el('input', {
        type: 'tel',
        id: 'tpa-phone',
        className: 'flex-1 px-4 py-3 border border-orange-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500 text-lg',
        placeholder: config.phonePlaceholder,
        autocomplete: 'tel',
      }),
    ]);
    c.appendChild(phoneRow);

    // send button
    var sendBtn = el('button', {
      id: 'tpa-send',
      className: 'w-full mt-3 py-3 rounded-xl text-white font-bold text-lg transition-all',
      style: 'background:#ea580c',
      onClick: function () { sendCode(); },
    });
    sendBtn.textContent = config.sendButtonText;
    c.appendChild(sendBtn);

    // recaptcha container (invisible)
    var recDiv = el('div', { id: 'tpa-recaptcha' });
    c.appendChild(recDiv);

    // code input (hidden initially)
    var codeWrap = el('div', { id: 'tpa-code-section', className: 'hidden mt-4' }, [
      el('p', { className: 'text-sm text-gray-500 mb-2 text-center', innerHTML: 'تم إرسال الكود إلى هاتفك' }),
      el('input', {
        type: 'tel',
        id: 'tpa-code',
        className: 'w-full px-4 py-3 border border-orange-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500 text-lg text-center tracking-[0.3em]',
        placeholder: 'XXXXXX',
        maxlength: '6',
        inputmode: 'numeric',
        pattern: '[0-9]*',
      }),
    ]);
    c.appendChild(codeWrap);

    // verify button (hidden)
    var verifyBtn = el('button', {
      id: 'tpa-verify',
      className: 'hidden w-full mt-3 py-3 rounded-xl text-white font-bold text-lg transition-all',
      style: 'background:#16a34a',
      onClick: function () { verifyCode(); },
    });
    verifyBtn.textContent = config.verifyButtonText;
    c.appendChild(verifyBtn);

    // resend link (hidden)
    var resendBtn = el('button', {
      id: 'tpa-resend',
      className: 'hidden mt-3 text-sm text-orange-600 hover:text-orange-700 underline text-center w-full bg-transparent border-0 cursor-pointer',
      onClick: function () { sendCode(); },
    });
    resendBtn.textContent = config.resendButtonText;
    c.appendChild(resendBtn);

    // init invisible recaptcha
    recaptchaVerifier = new firebase.auth.RecaptchaVerifier('tpa-recaptcha', {
      size: 'invisible',
    });
  }

  function sendCode() {
    var phone = (document.getElementById('tpa-phone').value || '').trim();
    if (!phone) {
      msg('الرجاء إدخال رقم الهاتف', 'error');
      return;
    }

    var sendBtn = document.getElementById('tpa-send');
    setLoading(sendBtn, true);

    auth.signInWithPhoneNumber(phone, recaptchaVerifier)
      .then(function (result) {
        confirmationResult = result;
        document.getElementById('tpa-code-section').classList.remove('hidden');
        document.getElementById('tpa-verify').classList.remove('hidden');
        document.getElementById('tpa-resend').classList.remove('hidden');
        sendBtn.classList.add('hidden');
        document.getElementById('tpa-code').focus();
        msg('تم إرسال كود التحقق', 'success');
      })
      .catch(function (err) {
        console.error('sendCode error:', err);
        // Reset recaptcha on failure
        if (recaptchaVerifier) {
          recaptchaVerifier.render().then(function (widgetId) {
            if (typeof grecaptcha !== 'undefined') grecaptcha.reset(widgetId);
          }).catch(function() {});
        }
        if (err.code === 'auth/too-many-requests') {
          msg('لقد تجاوزت الحد المسموح. يرجى المحاولة لاحقاً', 'error');
        } else if (err.code === 'auth/invalid-phone-number') {
          msg('رقم الهاتف غير صحيح', 'error');
        } else {
          msg('حدث خطأ. يرجى المحاولة مرة أخرى', 'error');
        }
      })
      .finally(function () {
        setLoading(sendBtn, false);
      });
  }

  function verifyCode() {
    var code = (document.getElementById('tpa-code').value || '').trim();
    if (!code || code.length < 6) {
      msg('الرجاء إدخال كود التحقق المكون من 6 أرقام', 'error');
      return;
    }
    if (!confirmationResult) {
      msg('يرجى إعادة إرسال الكود', 'error');
      return;
    }

    var verifyBtn = document.getElementById('tpa-verify');
    setLoading(verifyBtn, true);

    confirmationResult.confirm(code)
      .then(function (cred) {
        return cred.user.getIdToken();
      })
      .then(function (idToken) {
        return fetch(config.loginUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id_token: idToken }),
        });
      })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (data.error) {
          msg(data.error, 'error');
          return;
        }
        if (data.ok) {
          window.location.href = data.redirect || config.successRedirect;
        }
      })
      .catch(function (err) {
        console.error('verifyCode error:', err);
        msg('كود التحقق غير صحيح', 'error');
      })
      .finally(function () {
        setLoading(verifyBtn, false);
      });
  }

  /* ── expose ───────────────────────────────────────────────────── */

  window.TaminiPhoneAuth = {
    init: init,
    sendCode: sendCode,
    verifyCode: verifyCode,
  };
})();
