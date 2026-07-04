const API = window.location.origin + '/api';

function barraCupos(ocupados, max) {
  const pct = Math.min(100, (ocupados / max) * 100);
  const lleno = ocupados >= max;
  return `<div class="bar"><div class="bar-fill ${lleno ? 'lleno' : ''}" style="width:${pct}%"></div></div>`;
}

async function cargarSlots(containerId, fecha) {
  const el = document.getElementById(containerId);
  el.innerHTML = '<p>Cargando...</p>';
  try {
    const q = fecha ? `?fecha=${fecha}` : '';
    const res = await fetch(`${API}/slots${q}`);
    const data = await res.json();
    if (!data.slots?.length) {
      el.innerHTML = '<p>Sin horarios para esta fecha.</p>';
      return;
    }
    el.innerHTML = data.slots.map(s => {
      const libres = s.cupos_libres;
      const lleno = s.lleno;
      return `<div class="slot ${lleno ? 'lleno' : ''}">
        <div class="hora">${s.hora} — ${s.clase}</div>
        <div>${lleno ? 'LLENO' : `${libres} cupos libres`} (${s.ocupados}/${s.cupos_max})</div>
        ${barraCupos(s.ocupados, s.cupos_max)}
      </div>`;
    }).join('');
  } catch (e) {
    el.innerHTML = '<p>Error al cargar. ¿Está el servidor activo?</p>';
  }
}

async function cargarReservasAdmin(fecha) {
  const tbody = document.getElementById('reservas-body');
  tbody.innerHTML = '<tr><td colspan="8">Cargando...</td></tr>';
  try {
    const q = fecha ? `?fecha=${fecha}` : '';
    const res = await fetch(`${API}/reservas${q}`);
    const data = await res.json();
    if (!data.reservas?.length) {
      tbody.innerHTML = '<tr><td colspan="8">Sin reservas.</td></tr>';
      return;
    }
    tbody.innerHTML = data.reservas.map(r => `
      <tr>
        <td>${r.id}</td>
        <td>${r.cliente}</td>
        <td>${r.telefono}</td>
        <td>${r.fecha}</td>
        <td>${r.hora}</td>
        <td>${r.personas}</td>
        <td class="${r.pago === 'confirmado' ? 'confirmado' : 'pendiente'}">${r.pago}</td>
        <td>${r.pago !== 'confirmado' ? `<button class="small" onclick="confirmarPago(${r.id})">Confirmar</button>` : '—'}</td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="8">Error al cargar.</td></tr>';
  }
}

async function confirmarPago(id) {
  if (!confirm(`¿Confirmar pago de reserva #${id}?`)) return;
  const res = await fetch(`${API}/reservas/${id}/confirmar-pago`, { method: 'POST' });
  if (res.ok) {
    alert('Pago confirmado. Cliente notificado por WhatsApp.');
    cargarReservasAdmin(document.getElementById('fecha').value);
  } else {
    const err = await res.json();
    alert(err.detail || 'Error');
  }
}
