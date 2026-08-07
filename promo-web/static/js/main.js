/**
 * Main Interactive JS Utilities
 */
document.addEventListener('DOMContentLoaded', () => {
  // Fixed header scroll effect
  const header = document.querySelector('header');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 30) {
      header.classList.add('scrolled');
    } else {
      header.classList.remove('scrolled');
    }
  });

  // Mobile navigation hamburger toggle
  const mobileToggle = document.querySelector('.mobile-toggle');
  const navLinks = document.querySelector('.nav-links');

  if (mobileToggle && navLinks) {
    mobileToggle.addEventListener('click', () => {
      navLinks.classList.toggle('mobile-open');
    });

    // Close mobile nav on link click
    navLinks.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        navLinks.classList.remove('mobile-open');
      });
    });
  }

  // Copy Docker / CLI terminal command
  const copyBtn = document.getElementById('copy-cmd-btn');
  const codeSnippet = document.getElementById('docker-cmd-code');
  if (copyBtn && codeSnippet) {
    copyBtn.addEventListener('click', () => {
      const textToCopy = codeSnippet.innerText.trim();
      navigator.clipboard.writeText(textToCopy).then(() => {
        const originalText = copyBtn.innerText;
        copyBtn.innerText = 'Copied! ✓';
        copyBtn.style.background = '#FC4C02';
        copyBtn.style.color = '#FFF';
        setTimeout(() => {
          copyBtn.innerText = originalText;
          copyBtn.style.background = '';
          copyBtn.style.color = '';
        }, 2000);
      });
    });
  }

  // Active Nav Link Detection
  const currentPath = window.location.pathname;
  const links = document.querySelectorAll('.nav-links a');
  links.forEach(link => {
    const href = link.getAttribute('href');
    if (href && (currentPath.endsWith(href) || (href !== '/' && currentPath.includes(href)))) {
      link.classList.add('active');
    }
  });
});
