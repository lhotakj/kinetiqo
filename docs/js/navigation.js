/**
 * Kinetiqo Documentation - Navigation Script
 * Handles collapsible navigation sections and smooth scrolling
 */

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeNavigation();
    initializeSmoothScrolling();
    highlightActiveSection();
});

/**
 * Initialize collapsible navigation sections
 */
function initializeNavigation() {
    const navHeaders = document.querySelectorAll('.nav-section-header');
    
    navHeaders.forEach(header => {
        header.addEventListener('click', function() {
            const sectionId = this.getAttribute('data-section');
            const content = document.getElementById(sectionId);
            
            // Toggle active state
            this.classList.toggle('active');
            content.classList.toggle('expanded');
            
            // Close other sections (optional - for accordion behavior)
            // Uncomment the following lines if you want only one section open at a time
            /*
            navHeaders.forEach(otherHeader => {
                if (otherHeader !== this) {
                    otherHeader.classList.remove('active');
                    const otherId = otherHeader.getAttribute('data-section');
                    document.getElementById(otherId).classList.remove('expanded');
                }
            });
            */
        });
    });
    
    // Open the first section by default
    if (navHeaders.length > 0) {
        navHeaders[0].click();
    }
}

/**
 * Initialize smooth scrolling for anchor links
 */
function initializeSmoothScrolling() {
    const navLinks = document.querySelectorAll('.nav-link');
    
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            
            // Only handle internal anchor links
            if (href && href.startsWith('#')) {
                e.preventDefault();
                
                const targetId = href.substring(1);
                const targetElement = document.getElementById(targetId);
                
                if (targetElement) {
                    // Smooth scroll to target
                    targetElement.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                    
                    // Update active link
                    updateActiveLink(this);
                    
                    // Update URL without jumping
                    history.pushState(null, null, href);
                }
            }
        });
    });
}

/**
 * Highlight active section based on scroll position
 */
function highlightActiveSection() {
    const sections = document.querySelectorAll('.content-section[id]');
    const navLinks = document.querySelectorAll('.nav-link');
    
    if (sections.length === 0) return;
    
    // Create an intersection observer
    const observerOptions = {
        root: null,
        rootMargin: '-100px 0px -66%',
        threshold: 0
    };
    
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const id = entry.target.getAttribute('id');
                const correspondingLink = document.querySelector(`.nav-link[href="#${id}"]`);
                
                if (correspondingLink) {
                    updateActiveLink(correspondingLink);
                }
            }
        });
    }, observerOptions);
    
    // Observe all sections
    sections.forEach(section => {
        observer.observe(section);
    });
    
    // Handle initial load with hash
    if (window.location.hash) {
        const targetLink = document.querySelector(`.nav-link[href="${window.location.hash}"]`);
        if (targetLink) {
            updateActiveLink(targetLink);
            
            // Ensure the section containing this link is expanded
            const navSection = targetLink.closest('.nav-section');
            if (navSection) {
                const header = navSection.querySelector('.nav-section-header');
                const content = navSection.querySelector('.nav-section-content');
                if (header && content && !content.classList.contains('expanded')) {
                    header.click();
                }
            }
        }
    }
}

/**
 * Update the active link styling
 */
function updateActiveLink(activeLink) {
    const allLinks = document.querySelectorAll('.nav-link');
    
    allLinks.forEach(link => {
        link.classList.remove('active');
    });
    
    if (activeLink) {
        activeLink.classList.add('active');
        
        // Ensure the parent section is expanded
        const parentSection = activeLink.closest('.nav-section');
        if (parentSection) {
            const header = parentSection.querySelector('.nav-section-header');
            const content = parentSection.querySelector('.nav-section-content');
            
            if (header && content && !content.classList.contains('expanded')) {
                header.classList.add('active');
                content.classList.add('expanded');
            }
        }
    }
}

/**
 * Handle browser back/forward buttons
 */
window.addEventListener('popstate', function() {
    if (window.location.hash) {
        const targetLink = document.querySelector(`.nav-link[href="${window.location.hash}"]`);
        if (targetLink) {
            updateActiveLink(targetLink);
        }
    }
});

/**
 * Utility: Debounce function for performance optimization
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Add keyboard navigation support
document.addEventListener('keydown', function(e) {
    // Press 'Escape' to collapse all navigation sections
    if (e.key === 'Escape') {
        const navHeaders = document.querySelectorAll('.nav-section-header.active');
        navHeaders.forEach(header => {
            header.click();
        });
    }
});

console.log('Kinetiqo Documentation - Navigation initialized');
