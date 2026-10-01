/**
 * dashboard.js
 * ------------
 * Client-side logic for the MALHAM Dashboard & UI enhancements.
 * - Live clock
 * - Chart.js charts (dark mode styling with neon red #ff2a5f & cyan #00d2ff)
 * - Mobile sidebar toggle
 * - Entrance animations & Number count-up
 * - Toast notification auto-dismiss
 */

document.addEventListener("DOMContentLoaded", () => {
    initClock();
    initSidebarToggle();
    initAnimations();
    initNumberCountUp();
    initToasts();
    loadCharts();
});


/* ── Live Clock ───────────────────────────────────────────────────── */

function initClock() {
    const el = document.getElementById("header-clock");
    if (!el) return;

    function tick() {
        const now = new Date();
        const options = {
            weekday: "short",
            day: "numeric",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: true,
        };
        el.textContent = now.toLocaleString("en-IN", options);
    }

    tick();
    setInterval(tick, 1000);
}


/* ── Mobile Sidebar Toggle ────────────────────────────────────────── */

function initSidebarToggle() {
    const toggle  = document.getElementById("menu-toggle");
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebar-overlay");

    if (!toggle || !sidebar) return;

    toggle.addEventListener("click", () => {
        sidebar.classList.toggle("open");
        if (overlay) overlay.classList.toggle("active");
    });

    if (overlay) {
        overlay.addEventListener("click", () => {
            sidebar.classList.remove("open");
            overlay.classList.remove("active");
        });
    }
}


/* ── Entrance Animations ──────────────────────────────────────────── */

function initAnimations() {
    const items = document.querySelectorAll(".animate-in");
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.style.animationPlayState = "running";
                    observer.unobserve(entry.target);
                }
            });
        },
        { threshold: 0.1 }
    );

    items.forEach((item) => {
        item.style.animationPlayState = "paused";
        observer.observe(item);
    });
}


/* ── Number Count-up Animation ───────────────────────────────────── */

function initNumberCountUp() {
    const numElements = document.querySelectorAll(".stat-value, .doc-count, .bed-count, .med-count");
    numElements.forEach((el) => {
        const fullText = el.textContent.trim();
        const match = fullText.match(/^(\d+)(.*)$/);
        if (!match) return;

        const targetNum = parseInt(match[1], 10);
        const suffix = match[2] || "";
        if (isNaN(targetNum) || targetNum === 0) return;

        let start = 0;
        const duration = 600;
        const startTime = performance.now();

        function updateCount(now) {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const current = Math.floor(progress * targetNum);
            if (el.childNodes.length > 0 && el.childNodes[0].nodeType === 3) {
                el.childNodes[0].nodeValue = current + suffix;
            }
            if (progress < 1) {
                requestAnimationFrame(updateCount);
            } else if (el.childNodes.length > 0 && el.childNodes[0].nodeType === 3) {
                el.childNodes[0].nodeValue = targetNum + suffix;
            }
        }

        requestAnimationFrame(updateCount);
    });
}


/* ── Toast Notifications Auto-Dismiss ────────────────────────────── */

function initToasts() {
    const toasts = document.querySelectorAll(".toast-notification");
    toasts.forEach((toast) => {
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(100%)";
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    });
}


/* ── Charts (Chart.js - Dark Mode) ───────────────────────────────── */

async function loadCharts() {
    try {
        const response = await fetch("/api/dashboard-stats");
        const data = await response.json();
        renderFootfallChart(data.footfall);
        renderDepartmentChart(data.departments);
    } catch (err) {
        console.error("Failed to load chart data:", err);
    }
}


function renderFootfallChart(footfall) {
    const ctx = document.getElementById("footfallChart");
    if (!ctx) return;

    const labels = footfall.map((d) => {
        const dt = new Date(d.date);
        return dt.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
    });
    const values = footfall.map((d) => d.count);

    new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: "Patient Footfall",
                    data: values,
                    borderColor: "#ff2a5f",
                    backgroundColor: "rgba(255, 42, 95, 0.12)",
                    borderWidth: 3,
                    pointBackgroundColor: "#ff2a5f",
                    pointBorderColor: "#ffffff",
                    pointBorderWidth: 2,
                    pointRadius: 5,
                    pointHoverRadius: 8,
                    fill: true,
                    tension: 0.4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: "#141924",
                    titleColor: "#ffffff",
                    bodyColor: "#f0f4f8",
                    borderColor: "rgba(255, 42, 95, 0.4)",
                    borderWidth: 1,
                    titleFont: { family: "Inter", weight: "700" },
                    bodyFont: { family: "Inter" },
                    cornerRadius: 10,
                    padding: 12,
                },
            },
            scales: {
                x: {
                    grid: { color: "rgba(255, 255, 255, 0.05)" },
                    ticks: {
                        font: { family: "Inter", size: 11, weight: "500" },
                        color: "#94a3b8",
                    },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: "rgba(255, 255, 255, 0.05)" },
                    ticks: {
                        font: { family: "Inter", size: 11, weight: "500" },
                        color: "#94a3b8",
                        stepSize: 1,
                    },
                },
            },
        },
    });
}


function renderDepartmentChart(departments) {
    const ctx = document.getElementById("deptChart");
    if (!ctx) return;

    const labels = departments.map((d) => d.department);
    const values = departments.map((d) => d.count);

    const colors = [
        "#ff2a5f", "#00d2ff", "#10b981", "#ffb703",
        "#a855f7", "#ec4899", "#3b82f6", "#f97316",
    ];

    new Chart(ctx, {
        type: "doughnut",
        data: {
            labels,
            datasets: [
                {
                    data: values,
                    backgroundColor: colors.slice(0, labels.length),
                    borderWidth: 2,
                    borderColor: "#141924",
                    hoverOffset: 8,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "68%",
            plugins: {
                legend: {
                    position: "bottom",
                    labels: {
                        font: { family: "Inter", size: 11, weight: "500" },
                        color: "#94a3b8",
                        padding: 14,
                        usePointStyle: true,
                        pointStyleWidth: 10,
                    },
                },
                tooltip: {
                    backgroundColor: "#141924",
                    titleColor: "#ffffff",
                    bodyColor: "#f0f4f8",
                    borderColor: "rgba(255, 255, 255, 0.1)",
                    borderWidth: 1,
                    titleFont: { family: "Inter", weight: "700" },
                    bodyFont: { family: "Inter" },
                    cornerRadius: 10,
                    padding: 12,
                },
            },
        },
    });
}
