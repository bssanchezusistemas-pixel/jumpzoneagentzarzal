const API = window.location.origin + '/api';
const TOKEN_KEY = 'jf_admin_token';

function $(id) { return document.getElementById(id); }

function getToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function apiFetch(url, options = {}) {
  const headers = { ...authHeaders(), ...(options.headers || {}) };
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    mostrarLogin();
    throw new Error('Sesión expirada');
  }
  return res;
}

function mostrarLogin() {
  $('vista-login')?.classList.remove('hidden');
  $('vista-panel')?.classList.add('hidden');
  if (window.JFMotion) JFMotion.initLogin();
}

function mostrarPanel() {
  $('vista-login')?.classList.add('hidden');
  $('vista-panel')?.classList.remove('hidden');
  cargarPendientes();
}

$('form-login')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const errEl = $('login-error');
  errEl.classList.add('hidden');
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  btn.textContent = 'Entrando...';
  try {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        usuario: fd.get('usuario'),
        password: fd.get('password'),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errEl.textContent = data.detail || 'Usuario o contraseña incorrectos';
      errEl.classList.remove('hidden');
      if (window.JFMotion) JFMotion.shakeLoginError();
      return;
    }
    setToken(data.token);
    mostrarPanel();
  } catch {
    errEl.textContent = 'No se pudo conectar con el servidor';
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Entrar';
  }
});

$('btn-logout')?.addEventListener('click', () => {
  clearToken();
  mostrarLogin();
});

document.querySelectorAll('.tab').forEach(tab => {
  tab.onclick = () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('activo'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('activo'));
    tab.classList.add('activo');
    $(`tab-${tab.dataset.tab}`).classList.add('activo');
  };
});

async function cargarPendientes() {
  const el = $('lista-pendientes');
  el.innerHTML = '<p class="hint">Cargando...</p>';
  try {
    const res = await apiFetch(`${API}/admin/pendientes`);
    const data = await res.json();
    if (!data.pendientes?.length) {
      el.innerHTML = '<p class="hint">No hay pagos pendientes.</p>';
      return;
    }
    el.innerHTML = data.pendientes.map(p => {
      const comp = p.comprobante;
      const ia = comp?.monto_ia
        ? `<p class="ia-sugerencia">IA detectó: $${comp.monto_ia.toLocaleString('es-CO')}${comp.notas_ia ? ' — ' + comp.notas_ia : ''}</p>`
        : '';
      return `<article class="admin-card">
        <h3>${p.cliente}</h3>
        <p class="tel">${p.telefono}</p>
        <p><strong>${p.plan}</strong> — $${p.total.toLocaleString('es-CO')}</p>
        <p>Pago: ${p.metodo} · ${p.pago}</p>
        <p class="clases">${p.clases.join(' · ')}</p>
        ${ia}
        <button type="button" class="btn-confirmar" data-pkg="${p.package_id}">
          ✓ Confirmar pago
        </button>
      </article>`;
    }).join('');
    el.querySelectorAll('.btn-confirmar').forEach(btn => {
      btn.onclick = () => confirmar(Number(btn.dataset.pkg));
    });
    if (window.JFMotion) JFMotion.staggerAdminCards(el);
  } catch (err) {
    if (err.message !== 'Sesión expirada') {
      el.innerHTML = '<p class="hint">Error al cargar.</p>';
    }
  }
}

async function confirmar(packageId) {
  if (!confirm('¿Confirmar que recibiste el pago? El cliente será notificado por WhatsApp.')) return;
  try {
    const res = await apiFetch(`${API}/packages/${packageId}/confirmar-pago`, { method: 'POST' });
    if (res.ok) {
      alert('Pago confirmado.');
      cargarPendientes();
    } else {
      const e = await res.json();
      alert(e.detail || 'Error');
    }
  } catch (err) {
    if (err.message !== 'Sesión expirada') alert('Error al confirmar');
  }
}

async function cargarHoy() {
  const fecha = $('fecha-hoy').value;
  const el = $('lista-hoy');
  el.innerHTML = '<p class="hint">Cargando...</p>';
  try {
    const res = await apiFetch(`${API}/reservas?fecha=${fecha}`);
    const data = await res.json();
    if (!data.reservas?.length) {
      el.innerHTML = '<p class="hint">Sin clases este día.</p>';
      return;
    }
    el.innerHTML = data.reservas.map(r => `
      <article class="admin-card ${r.pago === 'confirmado' ? 'confirmada' : ''}">
        <h3>${r.cliente}</h3>
        <p>${r.hora} · ${r.personas} persona(s)</p>
        <p>Pago: ${r.pago}</p>
      </article>
    `).join('');
    if (window.JFMotion) JFMotion.staggerAdminCards(el);
  } catch (err) {
    if (err.message !== 'Sesión expirada') {
      el.innerHTML = '<p class="hint">Error.</p>';
    }
  }
}

$('btn-recargar')?.addEventListener('click', cargarPendientes);
$('btn-hoy')?.addEventListener('click', cargarHoy);
if ($('fecha-hoy')) $('fecha-hoy').valueAsDate = new Date();

if (getToken()) {
  mostrarPanel();
} else {
  mostrarLogin();
}
