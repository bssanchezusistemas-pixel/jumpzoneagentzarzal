# Guion de demo — Jump Zone (WhatsApp)

Duración estimada: **5–7 minutos**. Requisitos: servidor local + ngrok + Twilio sandbox unido.

## Antes de empezar

1. Arrancar servidor:
   ```powershell
   cd C:\Users\User\whatsapp-agentkit
   python -m uvicorn agent.main:app --host 0.0.0.0 --port 8000
   ```
2. Ngrok: `ngrok http 8000` → copiar URL en webhook Twilio (`/webhook`).
3. Abrir panel web: `http://localhost:8000/web/` y `http://localhost:8000/web/admin.html`.
4. (Opcional) Borrar historial del número demo si hace falta reiniciar conversación.

---

## Flujo 1 — Consultar disponibilidad (1 min)

**Cliente escribe:**
> ¿Qué hay libre esta semana?

**JumpBot debe:** usar `consultar_disponibilidad`, listar días/horas con cupos restantes (máx. 15/hora).

**Frase de cierre para la reunión:**
> "El bot siempre consulta la base de datos real — no inventa cupos."

---

## Flujo 2 — Reservar clase (2 min)

**Cliente escribe:**
> Quiero clase el sábado a las 10, somos 2 personas. Soy Ana.

**JumpBot debe:**
1. Confirmar cupos libres en ese horario.
2. Crear reserva con `crear_reserva`.
3. Indicar total a pagar y datos Nequi/Bancolombia.
4. Avisar que la dueña confirmará el pago manualmente.

**Mostrar en panel admin:** reserva aparece como `pendiente`.

---

## Flujo 3 — Comprobante de pago (30 s)

**Cliente envía captura** (imagen).

**JumpBot responde:**
> Recibí tu comprobante. La dueña lo revisará y te confirmará en breve.

*(No confirma automáticamente — v1 supervisada.)*

---

## Flujo 4 — Dueña confirma pago (1 min)

**Opción A — Panel web:** botón **Confirmar** en `/web/admin.html`.

**Opción B — WhatsApp admin** (número `+573013892917`):
> confirmar reserva 1

**Cliente recibe:**
> Listo, tu clase quedó confirmada: [fecha] a las [hora]...

---

## Flujo 5 — Reprogramar (1 min)

**Cliente escribe:**
> Necesito cambiar mi reserva al domingo a las 11

**JumpBot debe:**
- Validar regla de **24 horas** de anticipación.
- Si cumple: mostrar nuevo slot y reprogramar.
- Si no cumple: explicar política.

---

## Flujo 6 — Audio (opcional, 30 s)

**Cliente envía nota de voz:** "¿Cuánto cuesta la clase básica?"

Demostrar transcripción local (Whisper) + respuesta breve con precios de `knowledge/jumping-centro.txt`.

---

## Preguntas para cerrar la reunión

- Horario exacto y días cerrados
- Tipos de clase y precios finales
- ¿Paquetes mensuales?
- ¿Bloqueo manual de horarios (eventos/mantenimiento)?
- Número WhatsApp Business para producción (salir del sandbox Twilio)

## Riesgos a mencionar

- Sandbox Twilio solo para demo; producción requiere aprobación Meta/Twilio.
- Pagos siempre con supervisión de la dueña en v1.
- Recordatorios 24h activos con APScheduler en producción.
