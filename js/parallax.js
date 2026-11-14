/*
 * Subtle parallax for full-width photo sections (.fb-photo).
 *
 * - Moves only the background layer (.parallax-media) inside each .fb-photo,
 *   never text, cards or buttons.
 * - The layer shifts by 30% of the scroll distance relative to its section,
 *   so on screen it moves slower than the page.
 * - Transform only (translate3d), batched in requestAnimationFrame.
 * - Off below 768px and when the user prefers reduced motion.
 * - Progressive enhancement: without this script the page looks the same,
 *   just without the effect (the CSS for the taller layer only applies
 *   while <html> has the .parallax-on class, which this script adds).
 */
(() => {
  const SPEED = 0.3;
  const desktop = window.matchMedia('(min-width: 768px)');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  const items = Array.from(document.querySelectorAll('.fb-photo'))
    .map((section) => ({ section, media: section.querySelector(':scope > .parallax-media'), extra: 0 }))
    .filter((item) => item.media);
  if (!items.length) return;

  let active = false;
  let ticking = false;
  let viewportH = window.innerHeight;

  // How far the layer can travel while its section is on screen; the layer is
  // made this much taller above and below, so no edge ever shows.
  function measure() {
    viewportH = window.innerHeight;
    for (const item of items) {
      item.extra = Math.ceil((SPEED * (viewportH + item.section.offsetHeight)) / 2);
      item.section.style.setProperty('--parallax-extra', `${item.extra}px`);
    }
  }

  function update() {
    ticking = false;
    const viewportCenter = viewportH / 2;
    for (const item of items) {
      const rect = item.section.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > viewportH) continue; // off screen: skip
      const offset = (viewportCenter - (rect.top + rect.height / 2)) * SPEED;
      const clamped = Math.max(-item.extra, Math.min(item.extra, offset));
      item.media.style.transform = `translate3d(0, ${clamped.toFixed(1)}px, 0)`;
    }
  }

  function requestUpdate() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(update);
  }

  function onResize() {
    measure();
    requestUpdate();
  }

  // Section heights change when fonts load or the mobile menu opens
  const resizeObserver = 'ResizeObserver' in window ? new ResizeObserver(onResize) : null;

  function enable() {
    active = true;
    document.documentElement.classList.add('parallax-on');
    measure();
    update();
    window.addEventListener('scroll', requestUpdate, { passive: true });
    window.addEventListener('resize', onResize);
    if (resizeObserver) items.forEach((item) => resizeObserver.observe(item.section));
  }

  function disable() {
    active = false;
    document.documentElement.classList.remove('parallax-on');
    window.removeEventListener('scroll', requestUpdate);
    window.removeEventListener('resize', onResize);
    if (resizeObserver) resizeObserver.disconnect();
    for (const item of items) {
      item.media.style.transform = '';
      item.section.style.removeProperty('--parallax-extra');
    }
  }

  function check() {
    const shouldRun = desktop.matches && !reduceMotion.matches;
    if (shouldRun && !active) enable();
    else if (!shouldRun && active) disable();
  }

  desktop.addEventListener('change', check);
  reduceMotion.addEventListener('change', check);
  check();
})();
