const form = document.getElementById('auth-form');
const usernameInput = document.getElementById('auth-username');
const passwordInput = document.getElementById('auth-password');
const title = document.getElementById('auth-title');
const hint = document.getElementById('auth-hint');
const error = document.getElementById('auth-error');
const submit = document.getElementById('auth-submit');
const loginTab = document.getElementById('login-tab');
const registerTab = document.getElementById('register-tab');
let mode = 'login';

function setMode(nextMode) {
  mode = nextMode;
  const registering = mode === 'register';
  title.textContent = registering ? 'Create your account' : 'Welcome back';
  hint.textContent = registering
    ? 'Choose a username and a password with at least 12 characters.'
    : 'Sign in to continue with your SAGE workspace.';
  submit.textContent = registering ? 'Create account' : 'Sign in';
  passwordInput.autocomplete = registering ? 'new-password' : 'current-password';
  loginTab.classList.toggle('is-active', !registering);
  registerTab.classList.toggle('is-active', registering);
  loginTab.setAttribute('aria-selected', String(!registering));
  registerTab.setAttribute('aria-selected', String(registering));
  error.hidden = true;
  error.textContent = '';
}

loginTab.onclick = () => setMode('login');
registerTab.onclick = () => setMode('register');

fetch('/api/auth/session', { credentials: 'same-origin' }).then(response => {
  if (response.ok) window.location.replace('/');
}).catch(() => {});

form.onsubmit = async event => {
  event.preventDefault();
  submit.disabled = true;
  error.hidden = true;
  error.textContent = '';
  try {
    const response = await fetch(`/api/auth/${mode}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: usernameInput.value, password: passwordInput.value}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Could not authenticate. Please try again.');
    }
    window.location.replace('/');
  } catch (requestError) {
    error.textContent = requestError.message || 'Could not connect to SAGE. Please try again.';
    error.hidden = false;
  } finally {
    submit.disabled = false;
  }
};
