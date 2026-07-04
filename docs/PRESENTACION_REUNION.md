# Jump Zone — Propuesta y wireframes

## Arquitectura (3 capas)

```
WhatsApp (Twilio) ──► FastAPI (JumpBot + API) ──► PostgreSQL / Supabase
                              │
                              ├── Panel web (/web)
                              └── Recordatorios 24h (APScheduler)
```

## Fases de entrega

| Fase | Entregable | Tiempo |
|------|------------|--------|
| 0 | Demo WhatsApp + propuesta (hoy) | 2–4 h |
| 1 | BD real + tools de cupos | 1–2 sem |
| 2 | Panel web calendario + admin pagos | 1 sem |
| 3 | Recordatorios automáticos | 3–5 días |

---

## Wireframe — Vista cliente (`/web/`)

```
┌─────────────────────────────────────────────────────────┐
│  JUMP ZONE — Disponibilidad          [Admin]            │
├─────────────────────────────────────────────────────────┤
│  Fecha: [ 2026-06-28 ▼ ]  [ Ver cupos ]                 │
├─────────────────────────────────────────────────────────┤
│  10:00 — Jump Básico                                    │
│  ████████░░░░░░░  8/15 cupos libres                     │
│                                                         │
│  11:00 — Jump Básico                                    │
│  ███████████████  LLENO 15/15                           │
│                                                         │
│  18:00 — Jump Básico                                    │
│  ████░░░░░░░░░░░  4/15 cupos libres                     │
├─────────────────────────────────────────────────────────┤
│  ¿Reservar? Escríbenos por WhatsApp → JumpBot           │
└─────────────────────────────────────────────────────────┘
```

## Wireframe — Panel dueña (`/web/admin.html`)

```
┌──────────────────────────────────────────────────────────────────┐
│  JUMP ZONE — Admin                    [Disponibilidad]         │
├──────────────────────────────────────────────────────────────────┤
│  Fecha: [ hoy ▼ ]  [ Cargar reservas ]                           │
├────┬─────────┬────────────┬────────┬──────┬───────┬─────────────┤
│ ID │ Cliente │ Teléfono   │ Hora   │Cupos │ Pago  │ Acción      │
├────┼─────────┼────────────┼────────┼──────┼───────┼─────────────┤
│ 12 │ Ana     │ +57301...  │ 10:00  │  2   │Pend.  │[Confirmar]  │
│ 11 │ Luis    │ +57300...  │ 18:00  │  1   │Conf.  │     —       │
└────┴─────────┴────────────┴────────┴──────┴───────┴─────────────┘
```

## Flujo de pago (v1)

1. Cliente reserva → `pendiente_pago`
2. Cliente paga Nequi/transferencia
3. Dueña confirma en panel o WhatsApp admin
4. Bot notifica al cliente + recordatorio 24h antes

---

**Demo en vivo:** abrir `http://localhost:8000/web/` junto al WhatsApp.
