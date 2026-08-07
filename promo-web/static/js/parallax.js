/**
 * Scroll-Driven Parallax Engine
 */
(function() {
  const parallaxElements = document.querySelectorAll('[data-parallax-speed]');

  if (!parallaxElements.length) return;

  let latestKnownScrollY = 0;
  let ticking = false;

  function onScroll() {
    latestKnownScrollY = window.scrollY;
    requestTick();
  }

  function requestTick() {
    if (!ticking) {
      requestAnimationFrame(update);
    }
    ticking = true;
  }

  function update() {
    ticking = false;
    const scrollY = latestKnownScrollY;

    parallaxElements.forEach(el => {
      const speed = parseFloat(el.getAttribute('data-parallax-speed')) || 0.1;
      const yPos = -(scrollY * speed);
      el.style.transform = `translate3d(0, ${yPos}px, 0)`;
    });
  }

  window.addEventListener('scroll', onScroll, { passive: true });
})();
