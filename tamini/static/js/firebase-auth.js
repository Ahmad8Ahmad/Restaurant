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

  var VERIFY_SUCCESS_URL = '/accounts/verification-success/';

  function _actionCodeSettings() {
    return {
      url: window.location.origin + VERIFY_SUCCESS_URL,
      handleCodeInApp: false,
    };
  }

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
    hint.textContent = 'افتح بريدك الإلكتروني واضغط على رابط التأكيد — سيتم إرجاعك تلقائياً إلى موقعنا لإكمال الدخول.';
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
        user.sendEmailVerification(_actionCodeSettings())
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
        return cred.user.sendEmailVerification(_actionCodeSettings()).then(function () { return cred.user; });
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

  /* ════════════════════════════════════════════════════════════════
   *  GOOGLE SIGN-IN
   *  Renders one button; signs in via popup and posts the ID token
   *  to the same backend endpoint used by the other flows.
   *  If the email is already registered with another method, offers
   *  an inline password form to link the Google identity instead of
   *  failing with auth/account-exists-with-different-credential.
   * ════════════════════════════════════════════════════════════════ */

  var GOOGLE_SVG =
    '<svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">' +
    '<path fill="#FFC107" d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z"/>' +
    '<path fill="#FF3D00" d="M6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z"/>' +
    '<path fill="#4CAF50" d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238A11.91 11.91 0 0 1 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z"/>' +
    '<path fill="#1976D2" d="M43.611 20.083H42V20H24v8h11.303a12.04 12.04 0 0 1-4.087 5.571l.003-.002 6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z"/></svg>';

  function _buildPayload(cfg, idToken) {
    var payload = { id_token: idToken };
    if (cfg.getRole) {
      var role = cfg.getRole();
      if (role) payload.role = role;
    }
    if (cfg.getPhone) {
      var phone = cfg.getPhone();
      if (phone) payload.phone = phone;
    }
    return payload;
  }

  function _finishLogin(container, cfg, data) {
    if (data.ok) { window.location.href = data.redirect || cfg.successRedirect; return; }
    if (data.error) { _msg(container, data.error, 'error'); }
  }

  function _postTokenAndFinish(container, cfg, idToken) {
    return _postJSON(cfg.loginUrl, _buildPayload(cfg, idToken))
      .then(function (data) { _finishLogin(container, cfg, data); });
  }

  function _renderLinkPasswordForm(container, cfg, pendingCred, email) {
    var old = document.getElementById('tfa-link-form');
    if (old) old.remove();

    var form = _el('div', { id: 'tfa-link-form', className: 'mt-2' });

    var info = _el('p', { className: 'text-sm text-gray-600 mb-2 text-center' });
    info.textContent = 'البريد ' + email + ' مسجل لدينا بكلمة مرور. أدخل كلمة المرور لربط حساب Google به:';
    form.appendChild(info);

    var input = _el('input', {
      type: 'password',
      className: 'w-full px-4 py-2 border border-orange-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500 mb-2',
      placeholder: 'كلمة المرور', autocomplete: 'current-password',
    });
    form.appendChild(input);

    var linkBtn = _el('button', {
      className: 'w-full py-2 rounded-xl text-white font-bold transition-all',
      style: 'background:#ea580c',
      onClick: function () {
        var pass = input.value || '';
        if (!pass) { _msg(form, 'الرجاء إدخال كلمة المرور', 'error'); return; }
        _setLoading(linkBtn, true);
        auth.signInWithEmailAndPassword(email, pass)
          .then(function (result) { return result.user.linkWithCredential(pendingCred); })
          .then(function (linked) { return linked.user.getIdToken(true); })
          .then(function (idToken) { return _postTokenAndFinish(form, cfg, idToken); })
          .catch(function (e2) {
            console.error('linkWithCredential:', e2);
            var m = e2 && e2.code === 'auth/wrong-password'
              ? 'كلمة المرور غير صحيحة'
              : e2 && e2.code === 'auth/invalid-credential'
                ? 'كلمة المرور غير صحيحة'
                : 'حدث خطأ. يرجى المحاولة مرة أخرى';
            _msg(form, m, 'error');
          })
          .finally(function () { _setLoading(linkBtn, false); });
      },
    });
    linkBtn.textContent = 'ربط الحساب والمتابعة';
    form.appendChild(linkBtn);

    container.appendChild(form);
    input.focus();
  }

  function _handleDifferentCredential(container, cfg, err) {
    var pendingCred = err.credential;
    var email = err.email;
    if (!pendingCred || !email) { _msg(container, 'حدث خطأ. يرجى المحاولة مرة أخرى', 'error'); return; }
    auth.fetchSignInMethodsForEmail(email)
      .then(function (methods) {
        if (methods.indexOf('password') !== -1) {
          _renderLinkPasswordForm(container, cfg, pendingCred, email);
        } else if (methods.indexOf('phone') !== -1) {
          _msg(container, 'هذا البريد مرتبط بحساب هاتف. سجّل الدخول من تبويب «رقم الهاتف».', 'error');
        } else {
          _msg(container, 'حدث خطأ. يرجى المحاولة مرة أخرى', 'error');
        }
      })
      .catch(function (e2) {
        console.error('fetchSignInMethodsForEmail:', e2);
        _msg(container, 'حدث خطأ. يرجى المحاولة مرة أخرى', 'error');
      });
  }

  function googleSignIn(cfg, container) {
    var provider = new firebase.auth.GoogleAuthProvider();
    provider.setCustomParameters({ prompt: 'select_account' });
    auth.signInWithPopup(provider)
      .then(function (result) { return result.user.getIdToken(true); })
      .then(function (idToken) { return _postTokenAndFinish(container, cfg, idToken); })
      .catch(function (err) {
        console.error('googleSignIn:', err);
        if (err.code === 'auth/account-exists-with-different-credential') {
          _handleDifferentCredential(container, cfg, err);
          return;
        }
        var m = err.code === 'auth/popup-closed-by-user' ? 'تم إغلاق النافذة قبل إكمال الدخول'
              : err.code === 'auth/operation-not-allowed' ? 'تسجيل الدخول عبر Google غير مفعّل في لوحة Firebase'
              : err.code === 'auth/unauthorized-domain' ? 'هذا النطاق غير مصرح به في Firebase'
              : err.code === 'auth/popup-blocked' ? 'المتصفح منع النافذة المنبثقة. اسمح بها وحاول مجدداً'
              : 'حدث خطأ. يرجى المحاولة مرة أخرى';
        _msg(container, m, 'error');
      });
  }

  function googleInit(container, opts) {
    var cfg = Object.assign({
      loginUrl: '/accounts/firebase-login/',
      successRedirect: '/',
      buttonText: 'المتابعة عبر Google',
      getRole: null,
      getPhone: null,
    }, opts || {});

    var btn = _el('button', {
      className: 'w-full py-3 rounded-xl font-bold text-lg transition-all flex items-center justify-center gap-3 border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 cursor-pointer',
      onClick: function () { googleSignIn(cfg, container.parentElement || container); },
    });
    btn.type = 'button';
    btn.innerHTML = GOOGLE_SVG;
    var label = document.createElement('span');
    label.textContent = cfg.buttonText;
    btn.appendChild(label);

    container.appendChild(btn);
  }

  window.TaminiGoogleAuth = { init: googleInit };
})();
