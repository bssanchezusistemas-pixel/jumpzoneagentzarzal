/** Demo UI — sin backend. Solo para mostrar en reunión. */

const PRECIO = 35000;
const CUPO_MAX = 15;

// Cupos ficticios por hora (8–20 h) para que se vea realista
const CUPOS_DEMO = {
  8: 12, 9: 10, 10: 7, 11: 0, 12: 14, 13: 15,
  14: 9, 15: 15, 16: 6, 17: 11, 18: 4, 19: 13, 20: 15,
};

let slotSeleccionado = null;

function barraCupos(ocupados, max) {
  const pct = Math.min(100, (ocupados / max) * 100);
  const lleno = ocupados >= max;
  return `<div class="bar"><div class="bar-fill ${lleno ? 'lleno' : ''}" style="width:${pct}%"></div></div>`;
}

function formatearFecha(fechaStr) {
  if (!fechaStr) return '';
  const [y, m, d] = fechaStr.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long' });
}

function generarSlots(fecha) {
  const slots = [];
  for (let h = 8; h <= 20; h++) {
    const ocupados = CUPO_MAX - (CUPOS_DEMO[h] ?? 15);
    const libres = CUPO_MAX - ocupados;
    slots.push({
      hora: `${String(h).padStart(2, '0')}:00`,
      clase: 'Jump Básico',
      ocupados,
      libres,
      lleno: libres <= 0,
      precio: PRECIO,
    });
  }
  return slots;
}

function renderSlots(fecha) {
  const el = document.getElementById('slots');
  if (!fecha) {
    el.innerHTML = '<p class="hint">Selecciona una fecha para ver horarios.</p>';
    return;
  }

  const dt = new Date(fecha + 'T12:00:00');
  if (dt.getDay() === 0) {
    el.innerHTML = '<p class="hint">Domingos cerrado. Elige otro día.</p>';
    return;
  }

  const slots = generarSlots(fecha);
  const titulo = document.createElement('p');
  titulo.className = 'fecha-titulo';
  titulo.textContent = formatearFecha(fecha);

  el.innerHTML = titulo.outerHTML + slots.map(s => `
    <div class="slot ${s.lleno ? 'lleno' : ''}">
      <div class="slot-top">
        <div>
          <div class="hora">${s.hora} — ${s.clase}</div>
          <div class="cupos-texto">${s.lleno ? 'LLENO' : `${s.libres} cupos libres`} · $${PRECIO.toLocaleString('es-CO')}/persona</div>
        </div>
        ${s.lleno
          ? '<span class="badge-lleno">Sin cupo</span>'
          : `<button type="button" class="btn-reservar" data-hora="${s.hora}" data-libres="${s.libres}">Reservar</button>`}
      </div>
      ${barraCupos(s.ocupados, CUPO_MAX)}
    </div>
  `).join('');

  el.querySelectorAll('.btn-reservar').forEach(btn => {
    btn.addEventListener('click', () => abrirFormulario(fecha, btn.dataset.hora, Number(btn.dataset.libres)));
  });
}

function abrirFormulario(fecha, hora, libres) {
  slotSeleccionado = { fecha, hora, libres, precio: PRECIO };
  document.getElementById('resumen-slot').textContent =
    `${formatearFecha(fecha)} · ${hora} · Jump Básico · ${libres} cupos disponibles`;

  const select = document.getElementById('select-personas');
  select.innerHTML = '';
  for (let i = 1; i <= Math.min(libres, 8); i++) {
    const opt = document.createElement('option');
    opt.value = i;
    opt.textContent = i === 1 ? '1 persona' : `${i} personas`;
    select.appendChild(opt);
  }
  actualizarTotal();
  document.getElementById('form-reserva').reset();
  select.value = '1';
  actualizarTotal();

  const modal = document.getElementById('modal-reserva');
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function cerrarModal(id) {
  const modal = document.getElementById(id);
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

function actualizarTotal() {
  const personas = Number(document.getElementById('select-personas').value) || 1;
  document.getElementById('total-pagar').textContent =
    `$${(personas * PRECIO).toLocaleString('es-CO')}`;
}

function mostrarExito(datos) {
  document.getElementById('texto-exito').textContent =
    `${datos.nombre}, apartaste ${datos.personas} cupo(s) para el ${formatearFecha(datos.fecha)} a las ${datos.hora}. Total: $${datos.total.toLocaleString('es-CO')}.`;

  const modal = document.getElementById('modal-exito');
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

document.getElementById('btn-cargar').addEventListener('click', () => {
  renderSlots(document.getElementById('fecha').value);
});

document.getElementById('fecha').addEventListener('change', () => {
  renderSlots(document.getElementById('fecha').value);
});

document.getElementById('select-personas').addEventListener('change', actualizarTotal);

document.getElementById('form-reserva').addEventListener('submit', (e) => {
  e.preventDefault();
  if (!slotSeleccionado) return;

  const fd = new FormData(e.target);
  const personas = Number(fd.get('personas'));
  const datos = {
    nombre: fd.get('nombre'),
    telefono: fd.get('telefono'),
    personas,
    fecha: slotSeleccionado.fecha,
    hora: slotSeleccionado.hora,
    total: personas * PRECIO,
  };

  cerrarModal('modal-reserva');
  mostrarExito(datos);
});

document.querySelectorAll('[data-cerrar]').forEach(el => {
  el.addEventListener('click', () => cerrarModal('modal-reserva'));
});

document.querySelectorAll('[data-cerrar-exito]').forEach(el => {
  el.addEventListener('click', () => cerrarModal('modal-exito'));
});

// Inicio
const fechaInput = document.getElementById('fecha');
fechaInput.valueAsDate = new Date();
renderSlots(fechaInput.value);
