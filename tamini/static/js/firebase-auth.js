/**
 * Firebase Authentication for Tamini (template frontend).
 *
 * Phone:  TaminiPhoneAuth.init / sendCode / verifyCode
 * Email:  TaminiEmailAuth.initSignup / initLogin
 *
 * Both flows end with POSTing the Firebase ID token to the backend,
 * which creates/logs in the Django user.
 */
(function () {
  'use strict';

  var auth = window.taminiAuth;
  if (!auth) {
    console.warn('TaminiAuth: firebase auth not initialised.');
    return;
  }

  /* ── shared helpers ───────────────────────────────────────────── */

  function _el(tag, attrs, children) {
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

  function _msg(container, text, type) {
    var old = container.querySelector('.tfa-msg');
    if (old) old.remove();
    var cls = type === 'error'
      ? 'tfa-msg text-red-600 bg-red-50 border border-red-200'
      : 'tfa-msg text-green-700 bg-green-50 border border-green-200';
    var d = _el('div', { className: cls + ' text-sm p-3 rounded-xl mt-3 text-center' });
    d.textContent = text;
    container.appendChild(d);
  }

  function _setLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
      btn.dataset.origText = btn.textContent;
      btn.disabled = true;
      btn.textContent = '...';
    } else {
      btn.disabled = false;
      btn.textContent = btn.dataset.origText || btn.textContent;
    }
  }

  function _postJSON(url, data) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).then(function (r) { return r.json(); });
  }

  /* ════════════════════════════════════════════════════════════════
   *  EMAIL VERIFICATION GATE
   *  Hides the form and shows a "check your inbox" panel with
   *  resend + continue buttons.  The backend rejects unverified
   *  email tokens with code 'email_not_verified'.
   * ════════════════════════════════════════════════════════════════ */

  function _showVerifyPanel(container, formId, cfg, extraPayload) {
    var form = document.getElementById(formId);
    if (form) form.classList.add('hidden');

    var old = container.querySelector('.tfa-verify-panel');
    if (old) old.remove();

    var panel = _el('div', { className: 'tfa-verify-panel mt-2' });

    panel.appendChild(_el('div', { className: 'text-center text-4xl mb-3', innerHTML: '&#9993;' }));

    var title = _el('p', { className: 'text-center text-gray-800 font-bold mb-1' });
    title.textContent = 'تم إرسال رابط التأكيد إلى بريدك الإلكتروني';
    panel.appendChild(title);

    var hint = _el('p', { className: 'text-center text-gray-500 text-sm mb-4' });
    hint.textContent = 'افتح بريدك الإلكتروني واضغط على رابط التأكيد، ثم عد هنا واضغط «متابعة».';
    panel.appendChild(hint);

    var continueBtn = _el('button', {
      className: 'w-full py-3 rounded-xl text-white font-bold text-lg transition-all',
      style: 'background:#16a34a',
      onClick: function () {
        var user = auth.currentUser;
        if (!user) { window.location.reload(); return; }
        _setLoading(continueBtn, true);
        user.reload()
          .then(function () { return user.getIdToken(true); })
          .then(function (idToken) {
            var payload = Object.assign({ id_token: idToken }, extraPayload || {});
            return _postJSON(cfg.loginUrl, payload);
          })
          .then(function (data) {
            if (data.ok) { window.location.href = data.redirect || cfg.successRedirect; return; }
            if (data.code === 'email_not_verified') {
              _msg(panel, 'لم يتم تأكيد البريد بعد — اضغط الرابط داخل الرسالة ثم «متابعة».', 'error');
            } else if (data.error) {
              _msg(panel, data.error, 'error');
            }
          })
          .catch(function (err) {
            console.error('verify continue:', err);
            _msg(panel, 'حدث خطأ. يرجى المحاولة مرة أخرى', 'error');
          })
          .finally(function () { _setLoading(continueBtn, false); });
      },
    });
    continueBtn.textContent = 'متابعة';
    panel.appendChild(continueBtn);

    var resendBtn = _el('button', {
      className: 'mt-3 text-sm text-orange-600 hover:text-orange-700 underline w-full bg-transparent border-0 cursor-pointer',
      onClick: function () {
        var user = auth.currentUser;
        if (!user) return;
        user.sendEmailVerification()
          .then(function () { _msg(panel, 'تم إرسال الرابط مرة أخرى إلى بريدك', 'success'); })
          .catch(function (err) {
            console.error('resend verification:', err);
            var m = err && err.code === 'auth/too-many-requests'
              ? 'لقد تجاوزت الحد المسموح. يرجى المحاولة لاحقاً'
              : 'حدث خطأ. يرجى المحاولة مرة أخرى';
            _msg(panel, m, 'error');
          });
      },
    });
    resendBtn.textContent = 'إعادة إرسال الرابط';
    panel.appendChild(resendBtn);

    container.appendChild(panel);
  }

  /* ════════════════════════════════════════════════════════════════
   *  PHONE AUTH
   * ════════════════════════════════════════════════════════════════ */

  var _phoneConfirmation = null;
  var _phoneRecaptcha = null;
  var _phoneConfig = {};

  function phoneInit(opts) {
    _phoneConfig = Object.assign({
      container: null,
      loginUrl: '/accounts/firebase-login/',
      successRedirect: '/',
      sendButtonText: 'إرسال كود التحقق',
      verifyButtonText: 'تسجيل الدخول',
      resendButtonText: 'إعادة الإرسال',
      phonePlaceholder: '+963 9XX XXX XXX',
    }, opts || {});

    var c = _phoneConfig.container;
    c.innerHTML = '';

    c.appendChild(_el('div', { className: 'flex gap-2' }, [
      _el('input', {
        type: 'tel', id: 'tfa-phone',
        className: 'w-full px-4 py-3 border border-orange-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500 text-lg',
        placeholder: _phoneConfig.phonePlaceholder, autocomplete: 'tel',
      }),
    ]));

    var sendBtn = _el('button', {
      id: 'tfa-phone-send', className: 'w-full mt-3 py-3 rounded-xl text-white font-bold text-lg transition-all',
      style: 'background:#ea580c', onClick: function () { phoneSendCode(); },
    });
    sendBtn.textContent = _phoneConfig.sendButtonText;
    c.appendChild(sendBtn);

    c.appendChild(_el('div', { id: 'tfa-phone-recaptcha' }));

    c.appendChild(_el('div', { id: 'tfa-phone-code-wrap', className: 'hidden mt-4' }, [
      _el('p', { className: 'text-sm text-gray-500 mb-2 text-center', innerHTML: 'تم إرسال الكود إلى هاتفك' }),
      _el('input', {
        type: 'tel', id: 'tfa-phone-code',
        className: 'w-full px-4 py-3 border border-orange-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500 text-lg text-center tracking-[0.3em]',
        placeholder: 'XXXXXX', maxlength: '6', inputmode: 'numeric', pattern: '[0-9]*',
      }),
    ]));

    var verifyBtn = _el('button', {
      id: 'tfa-phone-verify', className: 'hidden w-full mt-3 py-3 rounded-xl text-white font-bold text-lg transition-all',
      style: 'background:#16a34a', onClick: function () { phoneVerifyCode(); },
    });
    verifyBtn.textContent = _phoneConfig.verifyButtonText;
    c.appendChild(verifyBtn);

    var resendBtn = _el('button', {
      id: 'tfa-phone-resend', className: 'hidden mt-3 text-sm text-orange-600 hover:text-orange-700 underline text-center w-full bg-transparent border-0 cursor-pointer',
      onClick: function () { phoneSendCode(); },
    });
    resendBtn.textContent = _phoneConfig.resendButtonText;
    c.appendChild(resendBtn);

    _phoneRecaptcha = new firebase.auth.RecaptchaVerifier('tfa-phone-recaptcha', { size: 'invisible' });
  }

  function phoneSendCode() {
    var phone = (document.getElementById('tfa-phone').value || '').trim();
    if (!phone) { _msg(_phoneConfig.container, 'الرجاء إدخال رقم الهاتف', 'error'); return; }
    var btn = document.getElementById('tfa-phone-send');
    _setLoading(btn, true);

    auth.signInWithPhoneNumber(phone, _phoneRecaptcha)
      .then(function (result) {
        _phoneConfirmation = result;
        document.getElementById('tfa-phone-code-wrap').classList.remove('hidden');
        document.getElementById('tfa-phone-verify').classList.remove('hidden');
        document.getElementById('tfa-phone-resend').classList.remove('hidden');
        btn.classList.add('hidden');
        document.getElementById('tfa-phone-code').focus();
        _msg(_phoneConfig.container, 'تم إرسال كود التحقق', 'success');
      })
      .catch(function (err) {
        console.error('phoneSendCode:', err);
        if (_phoneRecaptcha) {
          _phoneRecaptcha.render().then(function (wid) {
            if (typeof grecaptcha !== 'undefined') grecaptcha.reset(wid);
          }).catch(function () {});
        }
        var m = err.code === 'auth/too-many-requests' ? 'لقد تجاوزت الحد المسموح'
               : err.code === 'auth/invalid-phone-number' ? 'رقم الهاتف غير صحيح'
               : 'حدث خطأ. يرجى المحاولة مرة أخرى';
        _msg(_phoneConfig.container, m, 'error');
      })
      .finally(function () { _setLoading(btn, false); });
  }

  function phoneVerifyCode() {
    var code = (document.getElementById('tfa-phone-code').value || '').trim();
    if (!code || code.length < 6) { _msg(_phoneConfig.container, 'الرجاء إدخال كود التحقق المكون من 6 أرقام', 'error'); return; }
    if (!_phoneConfirmation) { _msg(_phoneConfig.container, 'يرجى إعادة إرسال الكود', 'error'); return; }
    var btn = document.getElementById('tfa-phone-verify');
    _setLoading(btn, true);

    _phoneConfirmation.confirm(code)
      .then(function (cred) { return cred.user.getIdToken(); })
      .then(function (idToken) { return _postJSON(_phoneConfig.loginUrl, { id_token: idToken }); })
      .then(function (data) {
        if (data.error) { _msg(_phoneConfig.container, data.error, 'error'); return; }
        if (data.ok) window.location.href = data.redirect || _phoneConfig.successRedirect;
      })
      .catch(function (err) {
        console.error('phoneVerifyCode:', err);
        _msg(_phoneConfig.container, 'كود التحقق غير صحيح', 'error');
      })
      .finally(function () { _setLoading(btn, false); });
  }

  window.TaminiPhoneAuth = { init: phoneInit, sendCode: phoneSendCode, verifyCode: phoneVerifyCode };

  /* ════════════════════════════════════════════════════════════════
   *  EMAIL AUTH  (signup + login via Firebase Email/Password)
   * ════════════════════════════════════════════════════════════════ */

  function emailSignupInit(container, opts) {
    var cfg = Object.assign({
      loginUrl: '/accounts/firebase-login/',
      successRedirect: '/',
      roles: [
        { value: 'customer', label: 'عميل' },
        { value: 'restaurant', label: 'مطعم' },
        { value: 'delivery', label: 'توصيل' },
      ],
    }, opts || {});

    container.innerHTML = '';
    var formWrap = _el('div', { id: 'tfa-signup-form' });

    // email
    formWrap.appendChild(_el('div', { className: 'mb-3' }, [
      _el('label', { className: 'block text-gray-700 text-sm mb-1', innerHTML: 'البريد الإلكتروني' }),
      _el('input', {
        type: 'email', id: 'tfa-email',
        className: 'w-full px-4 py-2 border border-orange-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500',
        placeholder: 'you@example.com', autocomplete: 'email',
      }),
    ]));

    // password
    formWrap.appendChild(_el('div', { className: 'mb-3' }, [
      _el('label', { className: 'block text-gray-700 text-sm mb-1', innerHTML: 'كلمة المرور' }),
      _el('input', {
        type: 'password', id: 'tfa-password',
        className: 'w-full px-4 py-2 border border-orange-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500',
        autocomplete: 'new-password',
      }),
    ]));

    // role select
    var roleSelect = _el('select', {
      id: 'tfa-role',
      className: 'w-full px-4 py-2 border border-orange-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500 mb-3',
    });
    cfg.roles.forEach(function (r) {
      var opt = _el('option', { value: r.value }, []);
      opt.textContent = r.label;
      roleSelect.appendChild(opt);
    });
    formWrap.appendChild(_el('div', { className: 'mb-3' }, [
      _el('label', { className: 'block text-gray-700 text-sm mb-1', innerHTML: 'نوع الحساب' }),
      roleSelect,
    ]));

    // phone (optional)
    formWrap.appendChild(_el('div', { className: 'mb-3' }, [
      _el('label', { className: 'block text-gray-700 text-sm mb-1', innerHTML: 'رقم الهاتف (اختياري)' }),
      _el('input', {
        type: 'tel', id: 'tfa-reg-phone',
        className: 'w-full px-4 py-2 border border-orange-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500',
        placeholder: '+963 9XX XXX XXX',
      }),
    ]));

    var btn = _el('button', {
      id: 'tfa-signup-btn',
      className: 'w-full py-3 rounded-xl text-white font-bold text-lg transition-all',
      style: 'background:#ea580c',
      onClick: function () { emailSignup(cfg); },
    });
    btn.textContent = 'إنشاء حساب';
    formWrap.appendChild(btn);

    container.appendChild(formWrap);
    container.appendChild(_el('div', { id: 'tfa-email-msg' }));
  }

  function emailSignup(cfg) {
    var email = (document.getElementById('tfa-email').value || '').trim();
    var password = document.getElementById('tfa-password').value || '';
    var role = document.getElementById('tfa-role').value;
    var phone = (document.getElementById('tfa-reg-phone').value || '').trim();
    var container = document.getElementById('tfa-email-msg').parentElement;
    var btn = document.getElementById('tfa-signup-btn');

    if (!email || !password) { _msg(container, 'الرجاء ملء جميع الحقول', 'error'); return; }
    if (password.length < 6) { _msg(container, 'كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'error'); return; }

    _setLoading(btn, true);

    auth.createUserWithEmailAndPassword(email, password)
      .then(function (cred) {
        return cred.user.sendEmailVerification().then(function () { return cred.user; });
      })
      .then(function () {
        _showVerifyPanel(container, 'tfa-signup-form', cfg, { role: role, phone: phone });
      })
      .catch(function (err) {
        console.error('emailSignup:', err);
        var m = err.code === 'auth/email-already-in-use' ? 'البريد الإلكتروني مسجل بالفعل'
              : err.code === 'auth/weak-password' ? 'كلمة المرور ضعيفة'
              : err.code === 'auth/invalid-email' ? 'البريد الإلكتروني غير صحيح'
              : 'حدث خطأ. يرجى المحاولة مرة أخرى';
        _msg(container, m, 'error');
      })
      .finally(function () { _setLoading(btn, false); });
  }

  function emailLoginInit(container, opts) {
    var cfg = Object.assign({
      loginUrl: '/accounts/firebase-login/',
      successRedirect: '/',
    }, opts || {});

    container.innerHTML = '';
    var formWrap = _el('div', { id: 'tfa-login-form' });

    formWrap.appendChild(_el('div', { className: 'mb-4' }, [
      _el('label', { className: 'block text-gray-700 text-sm mb-1 font-cairo', innerHTML: 'البريد الإلكتروني' }),
      _el('input', {
        type: 'email', id: 'tfa-login-email',
        className: 'w-full px-4 py-2 border border-orange-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500',
        placeholder: 'you@example.com', inputmode: 'email', autocomplete: 'email',
      }),
    ]));

    formWrap.appendChild(_el('div', { className: 'mb-4' }, [
      _el('label', { className: 'block text-gray-700 text-sm mb-1 font-cairo', innerHTML: 'كلمة المرور' }),
      _el('input', {
        type: 'password', id: 'tfa-login-password',
        className: 'w-full px-4 py-2 border border-orange-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500',
        autocomplete: 'current-password',
      }),
    ]));

    var btn = _el('button', {
      id: 'tfa-login-btn',
      className: 'w-full py-3 rounded-xl text-white font-bold text-lg transition-all font-cairo',
      style: 'background:#ea580c',
      onClick: function () { emailLogin(cfg); },
    });
    btn.textContent = 'دخول';
    formWrap.appendChild(btn);

    container.appendChild(formWrap);
    container.appendChild(_el('div', { id: 'tfa-login-msg' }));
  }

  function emailLogin(cfg) {
    var email = (document.getElementById('tfa-login-email').value || '').trim();
    var password = document.getElementById('tfa-login-password').value || '';
    var container = document.getElementById('tfa-login-msg').parentElement;
    var btn = document.getElementById('tfa-login-btn');

    if (!email || !password) { _msg(container, 'الرجاء إدخال البريد الإلكتروني وكلمة المرور', 'error'); return; }

    _setLoading(btn, true);

    auth.signInWithEmailAndPassword(email, password)
      .then(function (cred) { return cred.user.getIdToken(); })
      .then(function (idToken) { return _postJSON(cfg.loginUrl, { id_token: idToken }); })
      .then(function (data) {
        if (data.ok) { window.location.href = data.redirect || cfg.successRedirect; return; }
        if (data.code === 'email_not_verified') {
          _showVerifyPanel(container, 'tfa-login-form', cfg, {});
          return;
        }
        if (data.error) { _msg(container, data.error, 'error'); }
      })
      .catch(function (err) {
        console.error('emailLogin:', err);
        var m = err.code === 'auth/user-not-found' ? 'الحساب غير موجود'
              : err.code === 'auth/wrong-password' ? 'كلمة المرور غير صحيحة'
              : err.code === 'auth/invalid-email' ? 'البريد الإلكتروني غير صحيح'
              : err.code === 'auth/too-many-requests' ? 'لقد تجاوزت الحد المسموح. يرجى المحاولة لاحقاً'
              : 'حدث خطأ. يرجى المحاولة مرة أخرى';
        _msg(container, m, 'error');
      })
      .finally(function () { _setLoading(btn, false); });
  }

  window.TaminiEmailAuth = {
    initSignup: emailSignupInit,
    initLogin: emailLoginInit,
  };
})();
