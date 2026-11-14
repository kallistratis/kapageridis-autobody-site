/*
 * Shared behaviour for every page (loaded with `defer`):
 * mobile menu button, the floating chat menu (phone / email), the hero video,
 * the free estimate form (Tally, /dorean-ektimisi/) and the cookie banner for
 * the statistics (Google Analytics 4, only after consent).
 * Header, footer and chat markup are written by scripts/build.py.
 */
(() => {
  // Respect "reduce motion": keep the hero video still
  const heroVideo = document.querySelector('.hero-video');
  if (heroVideo && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    heroVideo.removeAttribute('autoplay');
    heroVideo.pause();
  }

  // Mobile menu
  const toggle = document.querySelector('.nav-toggle');
  const nav = document.getElementById('main-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = nav.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(open));
    });
  }

  // Chat button: open/close the phone + email menu (Esc or a click elsewhere closes it)
  const chatBtn = document.querySelector('.chat-float .fb-chat-btn');
  const chatMenu = document.getElementById('chat-menu');
  if (chatBtn && chatMenu) {
    const setChat = (open) => {
      chatMenu.hidden = !open;
      chatBtn.setAttribute('aria-expanded', String(open));
      chatBtn.setAttribute('aria-label', open ? 'Κλείσιμο' : 'Επικοινωνία: τηλέφωνο ή email');
      if (open) chatMenu.querySelector('a').focus();
    };
    chatBtn.addEventListener('click', () => setChat(chatMenu.hidden));
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !chatMenu.hidden) { setChat(false); chatBtn.focus(); }
    });
    document.addEventListener('click', (e) => {
      if (!chatMenu.hidden && !e.target.closest('.chat-float')) setChat(false);
    });
  }

  // Free estimate form (Tally), only on the page that has it: Tally's script fills in
  // the iframe and keeps its height equal to the form. If the script fails, load it anyway.
  const tallyFrames = document.querySelectorAll('iframe[data-tally-src]');
  if (tallyFrames.length) {
    const showForms = () => {
      if (window.Tally) window.Tally.loadEmbeds();
      else tallyFrames.forEach((frame) => { if (!frame.src) frame.src = frame.dataset.tallySrc; });
    };
    const tallyScript = document.createElement('script');
    tallyScript.src = 'https://tally.so/widgets/embed.js';
    tallyScript.async = true;
    tallyScript.onload = showForms;
    tallyScript.onerror = showForms;
    document.body.appendChild(tallyScript);
  }

  // Statistics consent (Google Analytics 4). The banner exists only when
  // data/business.json has analytics.ga4Id. GA4 is loaded ONLY after «Αποδοχή»;
  // the choice is kept on this device for 12 months, then we ask again.
  const consent = document.getElementById('consent');
  if (consent) {
    const KEY = 'kapageridis-consent';
    const MAX_AGE = 365 * 24 * 60 * 60 * 1000;
    const gaId = consent.dataset.gaId || '';
    let gaLoaded = false;

    const readChoice = () => {
      try {
        const saved = JSON.parse(localStorage.getItem(KEY));
        return saved && Date.now() - saved.time < MAX_AGE ? saved.choice : null;
      } catch (e) {
        return null;
      }
    };
    const saveChoice = (choice) => {
      try { localStorage.setItem(KEY, JSON.stringify({ choice, time: Date.now() })); } catch (e) { /* private mode */ }
    };

    const loadAnalytics = () => {
      if (gaLoaded || !/^G-[A-Z0-9]+$/.test(gaId)) return;
      gaLoaded = true;
      window.dataLayer = window.dataLayer || [];
      window.gtag = function gtag() { window.dataLayer.push(arguments); };
      // statistics only: nothing for advertising
      window.gtag('consent', 'default', {
        analytics_storage: 'granted', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied',
      });
      window.gtag('js', new Date());
      window.gtag('config', gaId, { allow_google_signals: false, allow_ad_personalization_signals: false });
      const script = document.createElement('script');
      script.async = true;
      script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(gaId)}`;
      document.head.appendChild(script);
    };

    // Remove the _ga cookies (this host and the main domain) when consent is withdrawn
    const removeAnalyticsCookies = () => {
      const host = location.hostname;
      const domains = ['', host, `.${host.replace(/^www\./, '')}`];
      document.cookie.split(';')
        .map((c) => c.split('=')[0].trim())
        .filter((name) => name.startsWith('_ga'))
        .forEach((name) => domains.forEach((d) => {
          document.cookie = `${name}=; Max-Age=0; path=/${d ? `; domain=${d}` : ''}`;
        }));
    };

    const choose = (choice) => {
      const before = readChoice();
      saveChoice(choice);
      consent.hidden = true;
      if (choice === 'granted') {
        loadAnalytics();
      } else if (before === 'granted' || gaLoaded) {
        removeAnalyticsCookies();
        window.location.reload(); // stop the analytics already running on this page
      }
    };

    consent.querySelectorAll('[data-consent]').forEach((btn) => {
      btn.addEventListener('click', () => choose(btn.dataset.consent));
    });
    // «Ρυθμίσεις cookies» (footer, privacy page): show the banner again
    document.querySelectorAll('[data-consent-open]').forEach((btn) => {
      btn.addEventListener('click', () => {
        consent.hidden = false;
        consent.querySelector('[data-consent]').focus();
      });
    });

    const saved = readChoice();
    if (saved === 'granted') loadAnalytics();
    else if (saved === null) consent.hidden = false;
  }
})();
