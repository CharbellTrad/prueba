/**
 * Portal eWallet — JavaScript standalone
 * Auto-logout por inactividad, flip cards, animaciones de entrada, auto-cierre de alertas
 */
(function () {
    'use strict';

    var INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000;
    var CARD_FLIP_DURATION_MS = 30 * 1000;
    var inactivityTimer = null;

    // -- Timer de inactividad: auto-logout tras 5 minutos --

    function resetInactivityTimer() {
        if (inactivityTimer) {
            clearTimeout(inactivityTimer);
        }
        inactivityTimer = setTimeout(function () {
            window.location.href = '/ewallet/logout';
        }, INACTIVITY_TIMEOUT_MS);
    }

    function setupInactivityTimer() {
        // Solo activar en paginas autenticadas (dashboard, detalle, perfil)
        if (!document.querySelector('.ew-navbar')) {
            return;
        }
        var events = ['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart', 'click'];
        events.forEach(function (event) {
            document.addEventListener(event, resetInactivityTimer, { passive: true });
        });
        resetInactivityTimer();
    }

    // -- Tarjetas flip: volteo al clic, auto-regreso tras 30 segundos --

    function setupFlipCards() {
        var flipCards = document.querySelectorAll('.ew-flip-card');
        var flipTimers = new Map();

        flipCards.forEach(function (card) {
            card.addEventListener('click', function () {
                var isFlipped = card.classList.contains('flipped');
                if (isFlipped) {
                    card.classList.remove('flipped');
                    clearAutoFlipBack(card);
                } else {
                    card.classList.add('flipped');
                    setAutoFlipBack(card);
                }
            });
        });

        function setAutoFlipBack(card) {
            clearAutoFlipBack(card);
            var timer = setTimeout(function () {
                card.classList.remove('flipped');
                flipTimers.delete(card);
            }, CARD_FLIP_DURATION_MS);
            flipTimers.set(card, timer);
        }

        function clearAutoFlipBack(card) {
            if (flipTimers.has(card)) {
                clearTimeout(flipTimers.get(card));
                flipTimers.delete(card);
            }
        }
    }

    // -- Animaciones de entrada escalonadas --

    function setupAnimations() {
        var cards = document.querySelectorAll('.ew-wallet-card, .ew-flip-card');
        cards.forEach(function (card, index) {
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            card.style.transition = 'opacity 0.5s ease ' + (index * 0.1) + 's, transform 0.5s ease ' + (index * 0.1) + 's';
            requestAnimationFrame(function () {
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            });
        });

        var sections = document.querySelectorAll('.ew-section, .ew-detail-grid');
        sections.forEach(function (section, index) {
            section.style.opacity = '0';
            section.style.transform = 'translateY(15px)';
            section.style.transition = 'opacity 0.4s ease ' + (index * 0.15) + 's, transform 0.4s ease ' + (index * 0.15) + 's';
            requestAnimationFrame(function () {
                section.style.opacity = '1';
                section.style.transform = 'translateY(0)';
            });
        });
    }

    // -- Auto-cierre de alertas tras 6 segundos --

    function setupAlertDismiss() {
        var alerts = document.querySelectorAll('.ew-alert');
        alerts.forEach(function (alert) {
            setTimeout(function () {
                alert.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-10px)';
                setTimeout(function () { alert.remove(); }, 500);
            }, 6000);
        });
    }

    // -- Inicializacion --

    function init() {
        setupInactivityTimer();
        setupFlipCards();
        setupAnimations();
        setupAlertDismiss();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();