(() => {
  const nativeFetch = window.fetch.bind(window);
  let redirecting = false;

  window.fetch = async (input, options) => {
    const response = await nativeFetch(input, options);
    const url = new URL(
      typeof input === 'string' ? input : input.url,
      window.location.href,
    );

    if (
      response.status === 401 &&
      url.pathname.startsWith('/api/') &&
      !url.pathname.startsWith('/api/auth/') &&
      !redirecting
    ) {
      redirecting = true;
      window.location.replace('/login.html');
    }

    return response;
  };

  const logoutButton = document.getElementById('logout-button');
  logoutButton?.addEventListener('click', async () => {
    logoutButton.disabled = true;
    try {
      const response = await window.fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
      });
      if (!response.ok) {
        throw new Error('Logout request failed.');
      }
      window.location.replace('/login.html');
    } catch {
      logoutButton.disabled = false;
      if (typeof toast === 'function') {
        toast('Could not log out. Please try again.');
      }
    }
  });

  window.addEventListener('pageshow', event => {
    if (!event.persisted) {
      return;
    }

    document.body.hidden = true;
    nativeFetch('/api/auth/session', {credentials: 'same-origin'}).then(response => {
      if (response.ok) {
        document.body.hidden = false;
      } else {
        window.location.replace('/login.html');
      }
    }).catch(() => {
      window.location.replace('/login.html');
    });
  });
})();
