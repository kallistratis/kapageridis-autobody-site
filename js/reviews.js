/*
 * Reviews carousel (the hand-entered reviews from data/reviews.json).
 *
 * - Scrolls slowly to the left, forever (the cards are repeated once so the loop has no jump).
 * - Stops while the mouse is over it or it has keyboard focus (Tab). On a phone a
 *   touch or swipe stops it, and it carries on by itself a few seconds after the
 *   last touch, so there is time to read. No pause button (by request).
 * - With "reduce motion" it does not move. Without JavaScript it is a plain
 *   row the visitor scrolls sideways.
 */
(() => {
  const SPEED = 30; // px per second: slow enough to read while it moves
  const RESUME_AFTER = 6000; // ms after the last touch/swipe
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  document.querySelectorAll('[data-reviews-carousel]').forEach((root) => {
    const viewport = root.querySelector('.reviews-viewport');
    const track = root.querySelector('.reviews-track');
    if (!viewport || !track) return;

    // Second copy of the cards for a seamless loop (hidden from screen readers and Tab)
    [...track.children].forEach((card) => {
      const copy = card.cloneNode(true);
      copy.setAttribute('aria-hidden', 'true');
      copy.querySelectorAll('a').forEach((a) => { a.tabIndex = -1; });
      track.append(copy);
    });

    let hovering = false;
    let focused = false;
    let holdUntil = 0; // set by touch/swipe
    let position = viewport.scrollLeft;
    let last = null;

    const hold = () => { holdUntil = performance.now() + RESUME_AFTER; };

    function frame(time) {
      const moving = !reduceMotion.matches && !hovering && !focused && time >= holdUntil;
      if (last !== null && moving) {
        position += (SPEED * (time - last)) / 1000;
        const loop = track.scrollWidth / 2;
        if (position >= loop) position -= loop;
        viewport.scrollLeft = position;
      }
      last = time;
      window.requestAnimationFrame(frame);
    }

    // The visitor scrolled by hand: continue from where they left it
    viewport.addEventListener('scroll', () => {
      if (Math.abs(viewport.scrollLeft - position) > 2) {
        position = viewport.scrollLeft;
        if (!hovering) hold(); // swipe on a phone: wait before moving again
      }
    }, { passive: true });

    root.addEventListener('mouseenter', () => { hovering = true; });
    root.addEventListener('mouseleave', () => { hovering = false; });
    viewport.addEventListener('focusin', () => { focused = true; });
    viewport.addEventListener('focusout', () => { focused = false; });
    viewport.addEventListener('pointerdown', (event) => {
      if (event.pointerType !== 'mouse') hold(); // touch: stop so they can read
    });

    window.requestAnimationFrame(frame);
  });
})();

/*
 * Google reviews, live from the Google Places API (Maps JavaScript API, Places library).
 *
 * - GDPR: nothing is requested from Google until the visitor presses
 *   «Εμφάνιση κριτικών Google». Without an API key the widget stays hidden
 *   (the "see all reviews on Google" links below it always work).
 * - Google returns at most 5 reviews ("most relevant"). Reviews below
 *   data-min-rating stars are not shown; when that filter is on, a note says so,
 *   and the overall score always counts every review on Google.
 * - Reviews are shown as Google sends them (author, stars, date, original text)
 *   with "Κριτικές από το Google" attribution and links back to Google.
 * - Reviews already written by hand on the page (.reviews-static, from
 *   data/reviews.json) are not repeated: same author name = skipped.
 */
(() => {
  const widget = document.querySelector('.reviews-widget');
  if (!widget) return;

  const { placeId, apiKey } = widget.dataset;
  const minRating = Math.max(1, Math.min(5, Number(widget.dataset.minRating) || 1));
  const consent = widget.querySelector('.reviews-consent');
  const button = widget.querySelector('.reviews-load');
  const summary = widget.querySelector('.reviews-summary');
  const grid = widget.querySelector('.reviews-grid');
  const note = widget.querySelector('.reviews-note');
  const status = widget.querySelector('.reviews-status');

  if (!apiKey || !placeId) {
    widget.hidden = true; // not set up yet: only the links to Google show
    return;
  }

  const numberEl = new Intl.NumberFormat('el-GR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

  function loadMapsApi() {
    if (window.google && window.google.maps && window.google.maps.importLibrary) return Promise.resolve();
    return new Promise((resolve, reject) => {
      window.__kapReviewsReady = () => resolve();
      const script = document.createElement('script');
      script.src = 'https://maps.googleapis.com/maps/api/js'
        + `?key=${encodeURIComponent(apiKey)}&v=weekly&language=el&loading=async&callback=__kapReviewsReady`;
      script.async = true;
      script.onerror = () => reject(new Error('Maps JavaScript API failed to load'));
      document.head.appendChild(script);
    });
  }

  function stars(value) {
    const full = Math.round(value);
    const span = document.createElement('span');
    span.className = 'review-stars';
    span.textContent = '★'.repeat(full) + '☆'.repeat(5 - full);
    span.setAttribute('role', 'img');
    span.setAttribute('aria-label', `${numberEl.format(value).replace(',0', '')} από 5 αστέρια`);
    return span;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function renderSummary(place) {
    summary.replaceChildren();
    if (document.querySelector('.reviews-summary-static')) return; // score already shown above
    if (typeof place.rating !== 'number') return;
    summary.append(el('span', 'reviews-score', numberEl.format(place.rating)), stars(place.rating));
    if (place.userRatingCount) {
      summary.append(el('span', 'reviews-count', `${place.userRatingCount} κριτικές στο Google`));
    }
    summary.hidden = false;
  }

  function renderCard(review) {
    const card = el('article', 'review-card');
    card.append(stars(review.rating || 0));

    const text = review.originalText || review.text || '';
    card.append(el('p', 'review-text', text));

    const author = el('p', 'review-author');
    const attribution = review.authorAttribution || {};
    if (attribution.photoURI) {
      const img = el('img');
      img.src = attribution.photoURI;
      img.alt = '';
      img.width = 40;
      img.height = 40;
      img.loading = 'lazy';
      img.referrerPolicy = 'no-referrer';
      author.append(img);
    }
    const name = attribution.uri ? el('a', null, attribution.displayName || 'Χρήστης Google') : el('span', null, attribution.displayName || 'Χρήστης Google');
    if (attribution.uri) {
      name.href = attribution.uri;
      name.target = '_blank';
      name.rel = 'noopener';
    }
    author.append(name);
    card.append(author);

    if (review.relativePublishTimeDescription) {
      card.append(el('p', 'review-time', review.relativePublishTimeDescription));
    }
    return card;
  }

  async function load() {
    button.disabled = true;
    status.textContent = 'Φόρτωση κριτικών…';
    try {
      await loadMapsApi();
      const { Place } = await google.maps.importLibrary('places');
      const place = new Place({ id: placeId, requestedLanguage: 'el' });
      await place.fetchFields({ fields: ['rating', 'userRatingCount', 'reviews'] });

      renderSummary(place);
      // Skip reviews already shown in the carousel (data/reviews.json), matched by author name.
      // The carousel may show "Maria N." for "Maria Ntotsika", so compare both forms.
      const normalize = (s) => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
      const shortName = (s) => {
        const parts = (s || '').trim().split(/\s+/);
        return parts.length < 2 ? (s || '') : `${parts[0]} ${parts[parts.length - 1][0].toUpperCase()}.`;
      };
      const handWritten = new Set(
        [...document.querySelectorAll('.reviews-static .review-author')].map((n) => normalize(n.textContent))
      );
      const already = (name) => handWritten.has(normalize(name)) || handWritten.has(normalize(shortName(name)));
      const shown = (place.reviews || []).filter((r) =>
        (r.rating || 0) >= minRating
        && (r.originalText || r.text)
        && !already(r.authorAttribution && r.authorAttribution.displayName));
      grid.replaceChildren(...shown.map(renderCard));
      grid.hidden = shown.length === 0;

      note.textContent = (minRating > 1
        ? `Κριτικές από το Google. Εμφανίζονται κριτικές με ${minRating} αστέρια και πάνω· η συνολική βαθμολογία περιλαμβάνει όλες τις κριτικές.`
        : 'Κριτικές από το Google.');
      note.hidden = false;
      consent.hidden = true;
      status.textContent = shown.length ? '' : 'Δείτε όλες τις κριτικές μας στο Google.';
    } catch (error) {
      console.error(error);
      status.textContent = 'Δεν ήταν δυνατή η φόρτωση των κριτικών αυτή τη στιγμή. Δείτε τις στο Google.';
      button.disabled = false;
    }
  }

  button.addEventListener('click', load);
})();
