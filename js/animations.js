/*
 * Reveal-on-scroll effects + "Before & After" sliders. No libraries.
 * Loaded with `defer`, so it never blocks the first paint.
 *
 * - Adds class "js" to <html>. Only then does css/animations.css hide
 *   anything for an effect, so without this script everything is visible.
 * - [data-reveal="fade|left|right"]: element appears when it enters the screen.
 * - [data-reveal-group]: its children appear one after another (0.1s apart).
 * - Each element is revealed once; scrolling back up does not replay it.
 * - With "reduce motion" on, everything is shown at once (CSS hides nothing
 *   in that case either).
 */
(() => {
  const root = document.documentElement;
  root.classList.add('js');

  /* ---------- Reveal on scroll ---------- */
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const targets = Array.from(document.querySelectorAll('[data-reveal], [data-reveal-group]'));

  document.querySelectorAll('[data-reveal-group]').forEach((group) => {
    Array.from(group.children).forEach((child, index) => {
      child.style.setProperty('--reveal-index', index);
    });
  });

  const show = (el) => el.classList.add('is-visible');
  const showAll = () => targets.forEach(show);

  if (reduceMotion.matches || !('IntersectionObserver' in window)) {
    showAll();
  } else {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          show(entry.target);
          observer.unobserve(entry.target); // once only
        }
      },
      // threshold 0 so even elements taller than the screen get revealed;
      // the bottom margin waits until the element is a little way in.
      { threshold: 0, rootMargin: '0px 0px -10% 0px' }
    );
    targets.forEach((el) => observer.observe(el));
  }
  reduceMotion.addEventListener('change', () => {
    if (reduceMotion.matches) showAll();
  });

  /* ---------- "Before & After" sliders ---------- */
  document.querySelectorAll('.ba').forEach((slider) => {
    const frame = slider.querySelector('.ba-frame');
    const range = slider.querySelector('.ba-range');
    if (!frame || !range) return;

    let pending = null;
    let frameRequested = false;

    function setPosition(percent) {
      const p = Math.min(100, Math.max(0, percent));
      slider.style.setProperty('--pos', `${p}%`);
      range.value = String(p);
      range.setAttribute('aria-valuetext', document.documentElement.lang === 'en'
        ? `Before ${Math.round(p)}%, after ${100 - Math.round(p)}%`
        : `Πριν ${Math.round(p)}%, μετά ${100 - Math.round(p)}%`);
    }

    // Batch pointer moves into one update per frame (smooth on phones)
    function setFromClientX(clientX) {
      pending = clientX;
      if (frameRequested) return;
      frameRequested = true;
      window.requestAnimationFrame(() => {
        frameRequested = false;
        const rect = frame.getBoundingClientRect();
        setPosition(((pending - rect.left) / rect.width) * 100);
      });
    }

    // Keyboard (arrows, Home/End, PageUp/PageDown) and screen readers
    range.addEventListener('input', () => setPosition(Number(range.value)));

    // Mouse: press and drag. Touch/pen: a sideways drag moves the line,
    // an up-down swipe scrolls the page (touch-action: pan-y), a tap jumps.
    let dragging = false;
    let start = null;

    frame.addEventListener('pointerdown', (event) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      try {
        frame.setPointerCapture(event.pointerId); // keep receiving moves outside the frame
      } catch (_) {
        /* capture is a nicety; dragging still works inside the frame */
      }
      start = { x: event.clientX, y: event.clientY, type: event.pointerType };
      if (event.pointerType === 'mouse') {
        dragging = true;
        setFromClientX(event.clientX);
        event.preventDefault(); // no text/image selection while dragging
      }
    });

    frame.addEventListener('pointermove', (event) => {
      if (!start) return;
      if (!dragging) {
        const dx = Math.abs(event.clientX - start.x);
        const dy = Math.abs(event.clientY - start.y);
        if (dx > 4 && dx > dy) dragging = true;
        else return;
      }
      setFromClientX(event.clientX);
    });

    function end(event) {
      if (start && !dragging && event.type === 'pointerup') {
        setFromClientX(event.clientX); // tap on touch screens
      }
      dragging = false;
      start = null;
    }
    frame.addEventListener('pointerup', end);
    frame.addEventListener('pointercancel', end);

    setPosition(Number(range.value) || 50); // starts in the middle
  });
})();
