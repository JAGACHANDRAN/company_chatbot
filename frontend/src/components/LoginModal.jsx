import React, { useState } from 'react';
import { loginApi } from '../api';

export default function LoginModal({ isOpen, onClose, onLoginSuccess, initialError = '' }) {
  const [mode, setMode] = useState('signup'); // 'signup' | 'login'
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(initialError || '');
  const [infoMessage, setInfoMessage] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError('Please enter your work email and password.');
      return;
    }

    if (mode === 'signup' && !name.trim()) {
      setError('Please enter your full name.');
      return;
    }

    setLoading(true);
    setError('');
    setInfoMessage('');

    try {
      const response = await loginApi(email.trim(), password);
      if (response?.user) {
        onLoginSuccess(response.user);
      }
    } catch (err) {
      setError(err.message || (mode === 'signup' ? 'Sign up failed.' : 'Invalid email or password.'));
    } finally {
      setLoading(false);
    }
  };

  const handleOAuthClick = (provider) => {
    if (provider === 'Google') {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      window.location.href = `${apiUrl}/auth/google/login`;
      return;
    }
    setInfoMessage(`Signing in with ${provider}... Please use company credentials or your work email.`);
  };



  return (
    <div className="fixed inset-0 z-[100] flex flex-col items-center justify-start bg-[#f8fafc] calispec-blueprint-canvas px-3 sm:px-4 pt-4 sm:pt-8 pb-8 overflow-y-auto select-none animate-fadeIn min-h-screen">
      {/* Background Blueprint Canvas and Radar Rings */}
      <div className="pointer-events-none fixed inset-0 z-0 flex items-center justify-center overflow-hidden">
        <div className="absolute w-[360px] h-[360px] rounded-full border border-sky-400/20 top-12" />
        <div className="absolute w-[520px] h-[520px] rounded-full border border-sky-400/10 top-[-20px]" />
        <div className="absolute w-[680px] h-[680px] rounded-full border border-sky-400/5 top-[-100px]" />
      </div>

      {/* Close Button at Top Right of Screen */}
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          className="fixed top-4 right-4 sm:top-5 sm:right-5 z-40 w-10 h-10 rounded-full bg-white border border-sky-200 shadow-md text-[#00639b] hover:text-white hover:bg-[#00639b] hover:border-[#00639b] flex items-center justify-center transition-all duration-200 cursor-pointer group"
          title="Close"
        >
          <span className="material-symbols-outlined text-xl font-bold text-[#00639b] group-hover:text-white transition-colors">close</span>
        </button>
      )}

      <div className="relative z-10 w-full max-w-[390px] mx-auto my-0 flex flex-col items-center pb-6">
        {/* Calispec Official Logo Above Card (Always fully visible with safe margins) */}
        <div className="mb-4 flex items-center justify-center shrink-0">
          <img
            alt="Calispec Logo"
            className="h-11 sm:h-12 w-auto object-contain drop-shadow-sm select-none"
            src="/calispec-logo-transparent.png"
            onError={(e) => {
              e.currentTarget.src =
                'https://lh3.googleusercontent.com/aida-public/AB6AXuCxMyBsabNLCY7YA-RJY06bQr5UKmKRlngx9e2GXFaUV-c2MiX0CQSes2IscnOU9oceEHxIodZRgT8yUzRJDk2fz-Z9CRpvi0DDtAUWfR3OZZHwHItMRgY6dF0r-iwVJm0v2QjFHrDkBMbEJ_3OgSZnXB7MCCgjlsnjJiT6hE6DzWELyHhn80s6FmTzH7aE-8C6m43_6F3ElgHWpSHWeMfXNpQXacjBjlpNLKj2-GHfg_KJkAkeRh9U5CBCowRiDde7BA';
            }}
          />
        </div>

        {/* Primary Authentication Container Card */}
        <div className="w-full bg-white rounded-3xl shadow-[0_20px_50px_rgba(2,132,199,0.08),0_2px_8px_rgba(15,23,42,0.04)] border border-slate-100 p-5 sm:p-6 relative z-10">
          {/* Top Interactive Mode Switcher (Log In / Sign Up) */}
          <div
            className="grid grid-cols-2 p-1 bg-[#edf2fb] rounded-full mb-4 sm:mb-5 relative"
            role="tablist"
          >
            <button
              aria-selected={mode === 'login'}
              className={`flex items-center justify-center py-2.5 px-4 rounded-full text-sm transition-all duration-200 ${
                mode === 'login'
                  ? 'bg-[#00639b] text-white font-bold shadow-md shadow-[#00639b]/25'
                  : 'bg-transparent text-[#5e6978] font-semibold hover:text-[#00639b]'
              }`}
              id="tab-login"
              onClick={() => {
                setMode('login');
                setError('');
                setInfoMessage('');
              }}
              type="button"
            >
              Log In
            </button>
            <button
              aria-selected={mode === 'signup'}
              className={`flex items-center justify-center py-2.5 px-4 rounded-full text-sm transition-all duration-200 ${
                mode === 'signup'
                  ? 'bg-[#00639b] text-white font-bold shadow-md shadow-[#00639b]/25'
                  : 'bg-transparent text-[#5e6978] font-semibold hover:text-[#00639b]'
              }`}
              id="tab-signup"
              onClick={() => {
                setMode('signup');
                setError('');
                setInfoMessage('');
              }}
              type="button"
            >
              Sign Up
            </button>
          </div>

          {/* Feedback Alerts */}
          {error && (
            <div className="mb-4 flex items-start gap-2 p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-medium animate-shake">
              <span className="material-symbols-outlined text-sm flex-shrink-0 mt-0.5">error</span>
              <span className="flex-1 leading-snug">{error}</span>
            </div>
          )}

          {infoMessage && (
            <div className="mb-4 flex items-start gap-2 p-2.5 rounded-xl bg-sky-50 border border-sky-200 text-sky-700 text-xs font-medium">
              <span className="material-symbols-outlined text-sm flex-shrink-0 mt-0.5">info</span>
              <span className="flex-1 leading-snug">{infoMessage}</span>
            </div>
          )}

          {/* Credential Entry Form */}
          <form className="flex flex-col space-y-3.5" onSubmit={handleSubmit}>
            {/* SIGN UP ONLY: Full Name */}
            {mode === 'signup' && (
              <div className="space-y-1 animate-fadeIn">
                <label className="block text-xs font-bold text-slate-700 pl-3">
                  Full Name
                </label>
                <div className="relative flex items-center">
                  <span className="material-symbols-outlined absolute left-4 text-[#00639b] text-[19px] pointer-events-none">
                    person
                  </span>
                  <input
                    className="w-full h-[48px] pl-11 pr-4 rounded-full bg-[#f0f4fc] border-0 text-slate-800 placeholder:text-slate-400 font-medium text-sm focus:outline-none focus:bg-white focus:ring-2 focus:ring-[#00639b]/20 shadow-inner transition-all"
                    placeholder="e.g. Sarah Jenkins"
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required={mode === 'signup'}
                  />
                </div>
              </div>
            )}

            {/* Work Email Address */}
            <div className="space-y-1">
              <label className="block text-xs font-bold text-slate-700 pl-3">
                Work Email Address
              </label>
              <div className="relative flex items-center">
                <span className="material-symbols-outlined absolute left-4 text-[#00639b] text-[19px] pointer-events-none">
                  mail
                </span>
                <input
                  className="w-full h-[48px] pl-11 pr-4 rounded-full bg-[#f0f4fc] border-0 text-slate-800 placeholder:text-slate-400 font-medium text-sm focus:outline-none focus:bg-white focus:ring-2 focus:ring-[#00639b]/20 shadow-inner transition-all"
                  placeholder="name@company.com"
                  required
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
            </div>

            {/* Password / Create Password */}
            <div className="space-y-1">
              <div className="flex items-center justify-between px-3">
                <label className="text-xs font-bold text-slate-700">
                  {mode === 'signup' ? 'Create Password' : 'Password'}
                </label>
                {mode === 'login' && (
                  <button
                    type="button"
                    onClick={() =>
                      setInfoMessage('For password recovery, please contact your Enterprise Administrator.')
                    }
                    className="text-xs font-semibold text-[#00639b] hover:text-[#004e7a] transition-colors"
                  >
                    Forgot password?
                  </button>
                )}
              </div>
              <div className="relative flex items-center">
                <span className="material-symbols-outlined absolute left-4 text-[#00639b] text-[19px] pointer-events-none">
                  lock
                </span>
                <input
                  className="w-full h-[48px] pl-11 pr-12 rounded-full bg-[#f0f4fc] border-0 text-slate-800 placeholder:text-slate-400 font-medium text-sm focus:outline-none focus:bg-white focus:ring-2 focus:ring-[#00639b]/20 shadow-inner transition-all"
                  placeholder={mode === 'signup' ? 'At least 8 characters' : 'Enter secure password'}
                  required
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  aria-label="Toggle password visibility"
                  className="absolute right-3.5 w-8 h-8 flex items-center justify-center text-[#00639b]/70 hover:text-[#00639b] transition-colors"
                  onClick={() => setShowPassword(!showPassword)}
                  type="button"
                >
                  <span className="material-symbols-outlined text-[20px]">
                    {showPassword ? 'visibility_off' : 'visibility'}
                  </span>
                </button>
              </div>

              {/* Requirement Line on Sign Up */}
              {mode === 'signup' && (
                <div className="flex items-center gap-1.5 text-[11px] text-slate-500 pl-3 pt-1">
                  <span className="material-symbols-outlined text-sky-600 text-sm">check_circle</span>
                  <span>Must contain 8+ characters, a number &amp; a symbol</span>
                </div>
              )}
            </div>

            {/* Primary Action Button */}
            <div className="pt-1.5">
              <button
                className="w-full h-[48px] rounded-full bg-[#00639b] hover:bg-[#005282] text-white flex items-center justify-center gap-2 shadow-lg shadow-[#00639b]/25 transition-all duration-200 active:scale-[0.98] font-bold text-base disabled:opacity-60"
                type="submit"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    <span>{mode === 'signup' ? 'Creating Account...' : 'Signing In...'}</span>
                  </>
                ) : (
                  <>
                    <span>{mode === 'signup' ? 'Create Account' : 'Sign In to Calispec'}</span>
                    <span className="font-bold text-lg">→</span>
                  </>
                )}
              </button>
            </div>

            {/* Terms Agreement on Sign Up */}
            {mode === 'signup' && (
              <p className="text-[11px] text-slate-500 text-center leading-relaxed px-2 pt-0.5">
                By creating an account, you agree to our{' '}
                <a href="javascript:void(0)" className="text-[#00639b] font-semibold hover:underline">
                  Terms of Service
                </a>{' '}
                &amp;{' '}
                <a href="javascript:void(0)" className="text-[#00639b] font-semibold hover:underline">
                  Privacy Policy
                </a>
              </p>
            )}
          </form>

          {/* OR CONTINUE WITH Divider */}
          <div className="relative my-3.5 flex items-center justify-center">
            <div className="w-full h-[1px] bg-slate-200/80" />
            <span className="absolute px-3 bg-white text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              OR CONTINUE WITH
            </span>
          </div>

          {/* Social SSO Buttons */}
          <div className="flex flex-col space-y-2">
            <button
              className="w-full h-[46px] px-4 rounded-full bg-white hover:bg-slate-50 text-slate-700 text-sm font-semibold shadow-xs flex items-center justify-center gap-3 transition-colors active:scale-[0.99] border border-slate-200"
              type="button"
              onClick={() => handleOAuthClick('Google')}
            >
              <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 24 24">
                <path
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  fill="#4285F4"
                />
                <path
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  fill="#34A853"
                />
                <path
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                  fill="#FBBC05"
                />
                <path
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                  fill="#EA4335"
                />
              </svg>
              <span>Continue with Google</span>
            </button>

            <button
              className="w-full h-[46px] px-4 rounded-full bg-white hover:bg-slate-50 text-slate-700 text-sm font-semibold shadow-xs flex items-center justify-center gap-3 transition-colors active:scale-[0.99] border border-slate-200"
              type="button"
              onClick={() => handleOAuthClick('Microsoft')}
            >
              <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 21 21">
                <rect fill="#f25022" height="9" width="9" x="1" y="1" />
                <rect fill="#7fba00" height="9" width="9" x="11" y="1" />
                <rect fill="#00a4ef" height="9" width="9" x="11" y="1" />
                <rect fill="#ffb900" height="9" width="9" x="11" y="1" />
              </svg>
              <span>Continue with Microsoft</span>
            </button>
          </div>
        </div>

        {/* Footer Legal Terms */}
        <div className="mt-5 flex items-center justify-center gap-3 text-center text-xs text-slate-500 font-medium">
          <a
            className="hover:text-[#00639b] transition-colors"
            href="javascript:void(0)"
          >
            Privacy Policy
          </a>
          <span className="text-slate-300 text-[10px]">•</span>
          <a
            className="hover:text-[#00639b] transition-colors"
            href="javascript:void(0)"
          >
            Terms of Service
          </a>
          <span className="text-slate-300 text-[10px]">•</span>
          <a
            className="hover:text-[#00639b] transition-colors"
            href="javascript:void(0)"
          >
            Trust Center
          </a>
        </div>
      </div>
    </div>
  );
}
