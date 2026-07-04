/**
 * Jumping Fit — micro-animaciones GSAP
 * Respeta prefers-reduced-motion
 */
(function () {
  if (typeof gsap === 'undefined') return;

  const reducedMq = window.matchMedia('(prefers-reduced-motion: reduce)');

  function isReduced() {
    return reducedMq.matches;
  }

  function dur(normal) {
    return isReduced() ? 0 : normal;
  }

  reducedMq.addEventListener?.('change', () => {});

  const Motion = {
    initLanding() {
      const hero = document.getElementById('hero');
      if (!hero) return;
      const logo = hero.querySelector('.jf-logo-hero');
      const title = hero.querySelector('.jf-hero-title');
      const slogan = hero.querySelector('.jf-slogan');
      const chips = hero.querySelectorAll('.jf-chip');
      const btn = hero.querySelector('.jf-btn-hero');
      const tl = gsap.timeline({ defaults: { ease: 'power2.out' } });
      if (logo) tl.from(logo, { scale: 0.88, opacity: 0, duration: dur(0.55) });
      if (title) tl.from(title, { y: 16, opacity: 0, duration: dur(0.4) }, '-=0.25');
      if (slogan) tl.from(slogan, { y: 12, opacity: 0, duration: dur(0.35) }, '-=0.2');
      if (chips.length) tl.from(chips, { y: 10, opacity: 0, stagger: 0.08, duration: dur(0.3) }, '-=0.15');
      if (btn) tl.from(btn, { y: 8, opacity: 0, duration: dur(0.3) }, '-=0.1');
    },

    initLogin() {
      const card = document.getElementById('login-card');
      if (!card) return;
      gsap.from(card, { y: 24, opacity: 0, duration: dur(0.45), ease: 'power2.out' });
    },

    shakeLoginError() {
      const card = document.getElementById('login-card');
      if (!card || isReduced()) return;
      gsap.fromTo(card, { x: -8 }, { x: 8, duration: 0.08, repeat: 3, yoyo: true, ease: 'power1.inOut' });
    },

    scrollToReservar() {
      const target = document.getElementById('reservar');
      if (!target) return;
      target.scrollIntoView({ behavior: isReduced() ? 'auto' : 'smooth', block: 'start' });
      const card = target.querySelector('.jf-wizard-card');
      if (card && !isReduced()) {
        gsap.fromTo(card, { opacity: 0.6, y: 12 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' });
      }
    },

    onPasoChange(pasoId) {
      const paso = document.getElementById(pasoId);
      if (!paso || isReduced()) return;
      gsap.fromTo(paso, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' });
      const stepNum = { 'paso-plan': 1, 'paso-horarios': 2, 'paso-form': 3, 'paso-exito': 4 }[pasoId];
      if (stepNum) this.updateStepper(stepNum);
    },

    updateStepper(active) {
      document.querySelectorAll('.jf-step').forEach((el) => {
        const n = Number(el.dataset.step);
        el.classList.toggle('activo', n === active);
        el.classList.toggle('completado', n < active);
      });
    },

    staggerPlanCards() {
      const cards = document.querySelectorAll('.plan-card');
      if (!cards.length || isReduced()) return;
      gsap.from(cards, { y: 16, opacity: 0, stagger: 0.07, duration: 0.35, ease: 'power2.out' });
    },

    staggerAdminCards(container) {
      if (!container || isReduced()) return;
      const cards = container.querySelectorAll('.admin-card');
      if (!cards.length) return;
      gsap.from(cards, { y: 12, opacity: 0, stagger: 0.06, duration: 0.3, ease: 'power2.out' });
    },
  };

  window.JFMotion = Motion;

  document.addEventListener('DOMContentLoaded', () => {
    if (document.body.classList.contains('reserva-page')) {
      Motion.initLanding();
    }
    if (document.getElementById('vista-login') && !document.getElementById('vista-panel')?.classList.contains('activo')) {
      Motion.initLogin();
    }
  });
})();
