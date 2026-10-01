/**
 * dashboard.js
 * ------------
 * Client-side logic for the MALHAM Dashboard & UI enhancements.
 * - Live clock
 * - Dynamic Theme-Aware Chart.js charts (responds to Light/Dark mode)
 * - Mobile sidebar toggle
 * - Entrance animations & Number count-up
 * - Toast notification auto-dismiss
 */

let footfallChartInstance = null;
let deptChartInstance = null;
let lastChartData = null;

document.addEventListener("DOMContentLoaded", () => {
    initClock();
    initSidebarToggle();
    initAnimations();
    initNumberCountUp();
    initToasts();
    loadCharts();
});


/* ── Theme Helpers for Chart.js ───────────────────────────────────── */

function getChartColors() {
    const isLight = document.documentElement.getAttribute("data-theme") === "light";
    return {
        text: isLight ? "#1a1a1f" : "#f4f4f6",
        muted: isLight ? "#5b5b66" : "#9a9aa5",
        grid: isLight ? "rgba(0, 0, 0, 0.08)" : "rgba(255, 255, 255, 0.06)",
        cardBg: isLight ? "#ffffff" : "#14141a",
        cardBorder: isLight ? "rgba(220, 38, 38, 0.2)" : "rgba(255, 255, 255, 0.12)",
        primaryRed: isLight ? "#dc2626" : "#e11d48",
        primaryRedBg: isLight ? "rgba(220, 38, 38, 0.12)" : "rgba(225, 29, 72, 0.15)",
        pointBorder: isLight ? "#ffffff" : "#0a0a0d"
    };
}

window.updateChartsTheme = function() {
    const c = getChartColors();

    if (footfallChartInstance) {
        footfallChartInstance.data.datasets[0].borderColor = c.primaryRed;
        footfallChartInstance.data.datasets[0].backgroundColor = c.primaryRedBg;
        footfallChartInstance.data.datasets[0].pointBackgroundColor = c.primaryRed;
        footfallChartInstance.data.datasets[0].pointBorderColor = c.pointBorder;
        footfallChartInstance.options.scales.x.grid.color = c.grid;
        footfallChartInstance.options.scales.x.ticks.color = c.muted;
        footfallChartInstance.options.scales.y.grid.color = c.grid;
        footfallChartInstance.options.scales.y.ticks.color = c.muted;
        footfallChartInstance.options.plugins.tooltip.backgroundColor = c.cardBg;
        footfallChartInstance.options.plugins.tooltip.titleColor = c.text;
        footfallChartInstance.options.plugins.tooltip.bodyColor = c.text;
        footfallChartInstance.options.plugins.tooltip.borderColor = c.cardBorder;
        footfallChartInstance.update();
    }

    if (deptChartInstance) {
        deptChartInstance.data.datasets[0].borderColor = c.cardBg;
        deptChartInstance.options.plugins.legend.labels.color = c.muted;
        deptChartInstance.options.plugins.tooltip.backgroundColor = c.cardBg;
        deptChartInstance.options.plugins.tooltip.titleColor = c.text;
        deptChartInstance.options.plugins.tooltip.bodyColor = c.text;
        deptChartInstance.options.plugins.tooltip.borderColor = c.cardBorder;
        deptChartInstance.update();
    }
};


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


/* ── Charts (Chart.js - Theme Aware) ─────────────────────────────── */

async function loadCharts() {
    try {
        const response = await fetch("/api/dashboard-stats");
        const data = await response.json();
        lastChartData = data;
        renderFootfallChart(data.footfall);
        renderDepartmentChart(data.departments);
    } catch (err) {
        console.error("Failed to load chart data:", err);
    }
}


function renderFootfallChart(footfall) {
    const ctx = document.getElementById("footfallChart");
    if (!ctx) return;

    if (footfallChartInstance) {
        footfallChartInstance.destroy();
    }

    const c = getChartColors();
    const labels = footfall.map((d) => {
        const dt = new Date(d.date);
        return dt.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
    });
    const values = footfall.map((d) => d.count);

    footfallChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: "Patient Footfall",
                    data: values,
                    borderColor: c.primaryRed,
                    backgroundColor: c.primaryRedBg,
                    borderWidth: 3,
                    pointBackgroundColor: c.primaryRed,
                    pointBorderColor: c.pointBorder,
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
                    backgroundColor: c.cardBg,
                    titleColor: c.text,
                    bodyColor: c.text,
                    borderColor: c.cardBorder,
                    borderWidth: 1,
                    titleFont: { family: "Inter", weight: "700" },
                    bodyFont: { family: "Inter" },
                    cornerRadius: 10,
                    padding: 12,
                },
            },
            scales: {
                x: {
                    grid: { color: c.grid },
                    ticks: {
                        font: { family: "Inter", size: 11, weight: "500" },
                        color: c.muted,
                    },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: c.grid },
                    ticks: {
                        font: { family: "Inter", size: 11, weight: "500" },
                        color: c.muted,
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

    if (deptChartInstance) {
        deptChartInstance.destroy();
    }

    const c = getChartColors();
    const labels = departments.map((d) => d.department);
    const values = departments.map((d) => d.count);

    const colors = [
        "#e11d48", "#00d2ff", "#10b981", "#ffb703",
        "#a855f7", "#ec4899", "#3b82f6", "#f97316",
    ];

    deptChartInstance = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels,
            datasets: [
                {
                    data: values,
                    backgroundColor: colors.slice(0, labels.length),
                    borderWidth: 2,
                    borderColor: c.cardBg,
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
                        color: c.muted,
                        padding: 14,
                        usePointStyle: true,
                        pointStyleWidth: 10,
                    },
                },
                tooltip: {
                    backgroundColor: c.cardBg,
                    titleColor: c.text,
                    bodyColor: c.text,
                    borderColor: c.cardBorder,
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
