const API = window.location.origin + '/api';
const TOKEN_KEY = 'jf_admin_token';

const state = {
  plan: null,
  slotIds: [],
  slotsInfo: [],
  diaActivo: null,
  mesVisible: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  pasoAnterior: 'paso-plan',
};

const MESES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];

const PASO_STEP = {
  'paso-plan': 1,
  'paso-horarios': 2,
  'paso-form': 3,
  'paso-exito': 4,
};

function $(id) { return document.getElementById(id); }

function hoyISO() {
  return toISO(new Date());
}

function toISO(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function parseISO(fecha) {
  const [y, m, d] = fecha.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function formatoDiaLargo(fecha) {
  const d = parseISO(fecha);
  const nombres = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  return `${nombres[d.getDay()]} ${d.getDate()} de ${MESES[d.getMonth()]}`;
}

function actualizarStepper(pasoId) {
  const n = PASO_STEP[pasoId];
  if (n && window.JFMotion) JFMotion.updateStepper(n);
}

function mostrarPaso(id) {
  if (state.pasoAnterior !== id && window.JFMotion) {
    JFMotion.onPasoChange(id);
  }
  state.pasoAnterior = id;
  document.querySelectorAll('.paso').forEach(p => p.classList.remove('activo'));
  $(id).classList.add('activo');
  actualizarStepper(id);
}

function irAReservar() {
  if (window.JFMotion) JFMotion.scrollToReservar();
  else $('reservar')?.scrollIntoView({ behavior: 'smooth' });
}

async function cargarConfigPublica() {
  try {
    const res = await fetch(`${API}/config/public`);
    const c = await res.json();
    if (c.nombre) {
      const el = $('hero-nombre');
      if (el) el.textContent = c.nombre;
      document.title = `${c.nombre} — Reservar clase`;
    }
    if (c.slogan && $('hero-slogan')) $('hero-slogan').textContent = c.slogan;
    if (c.horario && $('chip-horario')) $('chip-horario').textContent = c.horario;
    if (c.ubicacion && $('chip-ubicacion')) $('chip-ubicacion').textContent = c.ubicacion;
    if (c.whatsapp && $('footer-whatsapp')) {
      const tel = c.whatsapp.replace(/\s/g, '');
      $('footer-whatsapp').innerHTML = `¿Dudas? <a href="https://wa.me/${tel.replace('+', '')}" target="_blank" rel="noopener">Escríbenos por WhatsApp</a>`;
    }
    if (c.instagram && $('footer-instagram')) {
      $('footer-instagram').href = c.instagram;
    }
  } catch { /* ignore */ }
}

async function cargarPlanes() {
  const grid = $('planes-grid');
  grid.innerHTML = '<p class="hint">Cargando planes...</p>';
  try {
    const res = await fetch(`${API}/planes`);
    const data = await res.json();
    grid.innerHTML = data.planes.map(p => `
      <button type="button" class="plan-card jf-plan-card" data-codigo="${p.codigo}">
        <strong class="jf-plan-nombre">${p.nombre}</strong>
        <span class="jf-plan-clases">${p.clases} clase(s)</span>
        <span class="precio jf-plan-precio">${p.precio > 0 ? '$' + p.precio.toLocaleString('es-CO') : 'Consultar precio'}</span>
      </button>
    `).join('');
    grid.querySelectorAll('.plan-card').forEach(btn => {
      btn.onclick = () => elegirPlan(btn.dataset.codigo, data.planes, btn);
    });
    if (window.JFMotion) JFMotion.staggerPlanCards();
  } catch {
    grid.innerHTML = '<p class="hint">No se pudo cargar. ¿Está el servidor activo?</p>';
  }
}

function elegirPlan(codigo, planes, btnEl) {
  state.plan = planes.find(p => p.codigo === codigo);
  state.slotIds = [];
  state.slotsInfo = [];
  state.diaActivo = null;
  state.mesVisible = new Date(new Date().getFullYear(), new Date().getMonth(), 1);

  document.querySelectorAll('.plan-card').forEach(b => b.classList.remove('seleccionado'));
  if (btnEl) btnEl.classList.add('seleccionado');

  const n = state.plan.clases;
  $('hint-clases').textContent = n === 1
    ? 'Elige el día y luego la hora de tu clase.'
    : `Elige ${n} día(s) y hora(s). Toca cada día en el calendario y selecciona un horario.`;

  $('slots-panel').classList.add('hidden');
  $('slots-placeholder').classList.remove('hidden');
  $('slots-picker').innerHTML = '';
  renderElegidos();
  renderCalendario();
  $('btn-a-form').disabled = true;
  mostrarPaso('paso-horarios');
}

function diasConSeleccion() {
  const map = {};
  state.slotsInfo.forEach(s => { map[s.fecha] = (map[s.fecha] || 0) + 1; });
  return map;
}

function renderCalendario() {
  const grid = $('cal-grid');
  const titulo = $('cal-titulo');
  const mes = state.mesVisible;
  titulo.textContent = `${MESES[mes.getMonth()]} ${mes.getFullYear()}`;

  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  const primerMes = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
  $('cal-prev').disabled = mes.getTime() <= primerMes.getTime();

  const inicio = new Date(mes.getFullYear(), mes.getMonth(), 1);
  const offset = (inicio.getDay() + 6) % 7;
  const diasMes = new Date(mes.getFullYear(), mes.getMonth() + 1, 0).getDate();
  const seleccionados = diasConSeleccion();

  let html = '';
  for (let i = 0; i < offset; i++) html += '<span class="cal-celda vacia"></span>';

  for (let dia = 1; dia <= diasMes; dia++) {
    const fecha = toISO(new Date(mes.getFullYear(), mes.getMonth(), dia));
    const fechaDate = parseISO(fecha);
    const esDomingo = fechaDate.getDay() === 0;
    const esPasado = fechaDate < hoy;
    const deshabilitado = esDomingo || esPasado;
    const activo = state.diaActivo === fecha;
    const count = seleccionados[fecha] || 0;
    const clases = ['cal-celda', 'cal-dia'];
    if (deshabilitado) clases.push('deshabilitado');
    if (activo) clases.push('activo');
    if (count) clases.push('con-seleccion');
    const label = count > 1 ? `${dia} (${count})` : String(dia);
    html += `<button type="button" class="${clases.join(' ')}" data-fecha="${fecha}"
      ${deshabilitado ? 'disabled' : ''} aria-label="${formatoDiaLargo(fecha)}">${label}</button>`;
  }

  grid.innerHTML = html;
  grid.querySelectorAll('.cal-dia:not(.deshabilitado)').forEach(btn => {
    btn.onclick = () => elegirDia(btn.dataset.fecha);
  });
}

function elegirDia(fecha) {
  state.diaActivo = fecha;
  renderCalendario();
  $('slots-placeholder').classList.add('hidden');
  $('slots-panel').classList.remove('hidden');
  $('slots-dia-titulo').textContent = formatoDiaLargo(fecha);
  cargarSlotsDia(fecha);
}

async function cargarSlotsDia(fecha) {
  const el = $('slots-picker');
  el.innerHTML = '<p class="hint">Cargando horarios...</p>';
  try {
    const res = await fetch(`${API}/slots?fecha=${fecha}`);
    const data = await res.json();
    if (!data.slots?.length) {
      el.innerHTML = '<p class="hint">Sin horarios este día (domingo o sin cupos).</p>';
      return;
    }
    el.innerHTML = data.slots.map(s => {
      const sel = state.slotIds.includes(s.slot_id);
      const cupoAgotado = s.lleno;
      const limitePlan = state.slotIds.length >= state.plan.clases && !sel;
      const disabled = cupoAgotado || limitePlan;
      return `<button type="button" class="slot-btn ${cupoAgotado ? 'lleno' : ''} ${sel ? 'sel' : ''}"
        data-id="${s.slot_id}" data-fecha="${s.fecha}" data-hora="${s.hora}" ${disabled ? 'disabled' : ''}>
        ${s.hora} · ${cupoAgotado ? 'LLENO' : s.cupos_libres + ' cupos'}
      </button>`;
    }).join('');
    el.querySelectorAll('.slot-btn:not(.lleno)').forEach(btn => {
      btn.onclick = () => toggleSlot(Number(btn.dataset.id), btn.dataset.fecha, btn.dataset.hora);
    });
  } catch {
    el.innerHTML = '<p class="hint">Error al cargar horarios.</p>';
  }
}

function toggleSlot(id, fecha, hora) {
  const idx = state.slotIds.indexOf(id);
  if (idx >= 0) {
    state.slotIds.splice(idx, 1);
    state.slotsInfo = state.slotsInfo.filter(s => s.id !== id);
  } else if (state.slotIds.length < state.plan.clases) {
    state.slotIds.push(id);
    state.slotsInfo.push({ id, fecha, hora });
    state.slotsInfo.sort((a, b) => (a.fecha + a.hora).localeCompare(b.fecha + b.hora));
  }
  renderElegidos();
  renderCalendario();
  if (state.diaActivo) cargarSlotsDia(state.diaActivo);
  $('btn-a-form').disabled = state.slotIds.length !== state.plan.clases;
}

function renderElegidos() {
  const el = $('elegidos');
  if (!state.slotsInfo.length) {
    el.innerHTML = '';
    el.classList.add('hidden');
    return;
  }
  el.classList.remove('hidden');
  const total = state.plan.clases;
  const listo = state.slotsInfo.length === total;
  el.innerHTML = `
    <p><strong>${state.slotsInfo.length} de ${total} clase(s)</strong></p>
    <ul class="lista-elegidos">
      ${state.slotsInfo.map(s => `<li>${formatoDiaLargo(s.fecha)} · ${s.hora}</li>`).join('')}
    </ul>
    ${listo ? '<p class="hint listo">¡Listo! Puedes continuar.</p>' : '<p class="hint">Elige otro día en el calendario si te faltan clases.</p>'}
  `;
}

$('cal-prev')?.addEventListener('click', () => {
  state.mesVisible = new Date(state.mesVisible.getFullYear(), state.mesVisible.getMonth() - 1, 1);
  renderCalendario();
});
$('cal-next')?.addEventListener('click', () => {
  state.mesVisible = new Date(state.mesVisible.getFullYear(), state.mesVisible.getMonth() + 1, 1);
  renderCalendario();
});

$('btn-atras-plan')?.addEventListener('click', () => mostrarPaso('paso-plan'));
$('btn-atras-horarios')?.addEventListener('click', () => mostrarPaso('paso-horarios'));
$('btn-a-form')?.addEventListener('click', () => {
  mostrarPaso('paso-form');
  cargarDatosPago();
});

$('btn-ir-reservar')?.addEventListener('click', irAReservar);
$('btn-hero-reservar')?.addEventListener('click', irAReservar);

async function cargarDatosPago() {
  try {
    const res = await fetch(`${API}/config/public`);
    const c = await res.json();
    $('texto-nequi').textContent = 'Nequi: ' + (c.nequi || '');
    $('texto-banco').textContent = c.banco || '';
  } catch { /* ignore */ }
}

document.querySelectorAll('input[name="metodo"]').forEach(r => {
  r.onchange = () => {
    const esTrans = document.querySelector('input[name="metodo"]:checked')?.value === 'transferencia';
    $('datos-pago').classList.toggle('hidden', !esTrans);
  };
});

$('form-reserva')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    nombre: fd.get('nombre'),
    telefono: fd.get('telefono'),
    plan_codigo: state.plan.codigo,
    slot_ids: state.slotIds,
    metodo_pago: document.querySelector('input[name="metodo"]:checked').value,
  };
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  btn.textContent = 'Guardando...';
  try {
    const res = await fetch(`${API}/reservas/web`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const raw = await res.text();
    let data;
    try {
      data = JSON.parse(raw);
    } catch {
      throw new Error(res.ok ? 'Respuesta inválida del servidor' : (raw.slice(0, 120) || 'Error del servidor'));
    }
    if (!res.ok) throw new Error(data.detail || 'Error');

    const file = $('comprobante').files[0];
    if (file && body.metodo_pago === 'transferencia') {
      const cf = new FormData();
      cf.append('telefono', body.telefono);
      cf.append('package_id', data.package_id);
      cf.append('archivo', file);
      await fetch(`${API}/comprobantes`, { method: 'POST', body: cf });
    }

    $('texto-exito').textContent =
      `${body.nombre}, tu plan ${data.plan} quedó registrado. Total: $${Number(data.total_pagar).toLocaleString('es-CO')}.`;
    $('nota-exito').textContent = data.mensaje;
    mostrarPaso('paso-exito');
  } catch (err) {
    alert(err.message || 'No se pudo completar la reserva');
    btn.disabled = false;
    btn.textContent = 'Confirmar reserva';
  }
});

cargarConfigPublica();
cargarPlanes();
actualizarStepper('paso-plan');
