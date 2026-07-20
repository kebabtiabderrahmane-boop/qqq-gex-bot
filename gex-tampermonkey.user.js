// ==UserScript==
// @name         QQQ GEX Confluence - TradingView Overlay v3
// @namespace    http://tampermonkey.net/
// @version      3.0
// @description  Displays high-probability confluence levels on TradingView charts
// @match        https://www.tradingview.com/chart/*
// @grant        GM_xmlhttpRequest
// @connect      raw.githubusercontent.com
// @run-at       document-idle
// @downloadURL  https://raw.githubusercontent.com/kebabtiabderrahmane-boop/qqq-gex-bot/main/gex-tampermonkey.user.js
// @updateURL    https://raw.githubusercontent.com/kebabtiabderrahmane-boop/qqq-gex-bot/main/gex-tampermonkey.user.js
// ==/UserScript==

(function() {
    'use strict';

    const DATA_URL = 'https://raw.githubusercontent.com/kebabtiabderrahmane-boop/qqq-gex-bot/main/data.json';
    const REFRESH_INTERVAL = 30000; // 30 seconds

    // Configuration
    const CONFIG = {
        CALL_COLOR: '#00FF00',      // Green for CALL levels
        PUT_COLOR: '#FF0000',       // Red for PUT levels
        FLIP_COLOR: '#FFFF00',     // Yellow for FLIP levels
        NEUTRAL_COLOR: '#FFFFFF',   // White for neutral
        LINE_WIDTH: 3,
        LABEL_FONT_SIZE: 11,
        MIN_SCORE: 2,              // Minimum confluence score to display
        MAX_LINES: 10              // Maximum number of lines to draw
    };

    // State
    let currentData = null;
    let overlayElements = [];
    let statusElement = null;
    let updateTimer = null;

    // Logging utility
    function log(message, data) {
        const timestamp = new Date().toISOString().split('T')[1].split('.')[0];
        const prefix = `[GEX-CONFLUENCE ${timestamp}]`;
        if (data !== undefined) {
            console.log(prefix, message, data);
        } else {
            console.log(prefix, message);
        }
    }

    // Inject CSS styles
    function injectStyles() {
        const styles = document.createElement('style');
        styles.id = 'gex-confluence-styles';
        styles.textContent = `
            .gex-confluence-overlay {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 999;
                overflow: hidden;
            }
            .gex-confluence-line {
                position: absolute;
                left: 0;
                width: 100%;
                height: 2px;
                opacity: 0.85;
                box-shadow: 0 0 4px currentColor;
            }
            .gex-confluence-line.type-call { background-color: ${CONFIG.CALL_COLOR}; }
            .gex-confluence-line.type-put { background-color: ${CONFIG.PUT_COLOR}; }
            .gex-confluence-line.type-flip { background-color: ${CONFIG.FLIP_COLOR}; }
            .gex-confluence-line.type-neutral { background-color: ${CONFIG.NEUTRAL_COLOR}; }
            
            .gex-confluence-label {
                position: absolute;
                right: 70px;
                padding: 3px 8px;
                font-size: ${CONFIG.LABEL_FONT_SIZE}px;
                font-family: 'Roboto Mono', 'Consolas', monospace;
                font-weight: bold;
                border-radius: 3px;
                white-space: nowrap;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
                background: rgba(0,0,0,0.75) !important;
            }
            .gex-confluence-label.type-call { color: ${CONFIG.CALL_COLOR}; }
            .gex-confluence-label.type-put { color: ${CONFIG.PUT_COLOR}; }
            .gex-confluence-label.type-flip { color: ${CONFIG.FLIP_COLOR}; }
            .gex-confluence-label.type-neutral { color: ${CONFIG.NEUTRAL_COLOR}; }
            
            .gex-confluence-badge {
                display: inline-block;
                padding: 1px 5px;
                margin-left: 5px;
                font-size: 9px;
                border-radius: 8px;
                vertical-align: middle;
            }
            .gex-confluence-badge.type-call { background: ${CONFIG.CALL_COLOR}; color: #000; }
            .gex-confluence-badge.type-put { background: ${CONFIG.PUT_COLOR}; color: #000; }
            .gex-confluence-badge.type-flip { background: ${CONFIG.FLIP_COLOR}; color: #000; }
            .gex-confluence-badge.type-neutral { background: ${CONFIG.NEUTRAL_COLOR}; color: #000; }
            
            .gex-confluence-status {
                position: fixed;
                top: 60px;
                right: 10px;
                padding: 8px 12px;
                background: rgba(0,0,0,0.85);
                color: #00ff88;
                font-size: 11px;
                font-family: 'Roboto Mono', monospace;
                border-radius: 6px;
                z-index: 10000;
                border: 1px solid rgba(0,255,136,0.3);
                max-width: 350px;
            }
            .gex-confluence-status.error {
                color: #ff4444;
                border-color: rgba(255,68,68,0.3);
            }
            .gex-confluence-status .title {
                font-weight: bold;
                margin-bottom: 4px;
                color: #fff;
            }
            .gex-confluence-status .levels {
                font-size: 10px;
                color: #ccc;
            }
            .gex-confluence-status .level-item {
                margin: 2px 0;
            }
            .gex-confluence-status .level-item .strike {
                font-weight: bold;
            }
            .gex-confluence-status .level-item.type-call .strike { color: ${CONFIG.CALL_COLOR}; }
            .gex-confluence-status .level-item.type-put .strike { color: ${CONFIG.PUT_COLOR}; }
            .gex-confluence-status .level-item.type-flip .strike { color: ${CONFIG.FLIP_COLOR}; }
            .gex-confluence-status .level-item.type-neutral .strike { color: ${CONFIG.NEUTRAL_COLOR}; }
        `;
        document.head.appendChild(styles);
        log('Styles injected');
    }

    // Fetch GEX data from GitHub
    function fetchGexData() {
        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                method: 'GET',
                url: DATA_URL,
                timeout: 15000,
                onload: function(response) {
                    try {
                        const data = JSON.parse(response.responseText);
                        if (!data.confluence || !Array.isArray(data.confluence)) {
                            reject(new Error('Invalid data format'));
                            return;
                        }
                        resolve(data);
                    } catch (e) {
                        reject(new Error('JSON parse error: ' + e.message));
                    }
                },
                onerror: function() {
                    reject(new Error('Network request failed'));
                },
                ontimeout: function() {
                    reject(new Error('Request timed out'));
                }
            });
        });
    }

    // Find the main chart container
    function findChartContainer() {
        // TradingView uses various selectors
        const selectors = [
            '.chart-container',
            '.tv-lightweight-charts',
            '.layout__chart',
            '#chart-container',
            '[class*="chart"][class*="container"]',
            '.chart-gui-wrapper'
        ];

        for (const selector of selectors) {
            const el = document.querySelector(selector);
            if (el && el.offsetWidth > 200 && el.offsetHeight > 200) {
                log(`Found chart container: ${selector}`);
                return el;
            }
        }

        // Fallback: find any large div that looks like a chart
        const allDivs = document.querySelectorAll('div');
        for (const div of allDivs) {
            const w = div.offsetWidth;
            const h = div.offsetHeight;
            if (w > 400 && h > 300 && w < 2000 && h < 1200) {
                const style = window.getComputedStyle(div);
                if (style.position === 'absolute' || style.position === 'relative') {
                    log(`Found chart div: ${div.className || div.id || 'unknown'}`);
                    return div;
                }
            }
        }

        log('Could not find chart container');
        return null;
    }

    // Extract visible price range from chart
    function getVisiblePriceRange() {
        // Look for price axis labels
        const priceLabels = [];
        
        // Try various TradingView price label selectors
        const selectors = [
            '.yAxis__right .axis__labels .axis__label',
            '.price-axis .axis__label',
            'tv-yaxis-label',
            '[class*="price-label"]',
            '[class*="y-axis"] .label'
        ];

        for (const selector of selectors) {
            const labels = document.querySelectorAll(selector);
            labels.forEach(label => {
                const text = label.textContent.trim();
                const price = parsePrice(text);
                if (price && price > 100 && price < 1000) {
                    priceLabels.push(price);
                }
            });
        }

        // Also look for any numbers on the right axis
        if (priceLabels.length < 2) {
            const rightAxis = document.querySelector('.layout__chart-area') || 
                             document.querySelector('[class*="pane"]');
            if (rightAxis) {
                const text = rightAxis.textContent;
                const matches = text.match(/\$?(\d{3,4})\.?\d*/g);
                if (matches) {
                    matches.forEach(m => {
                        const price = parsePrice(m);
                        if (price && price > 100 && price < 1000) {
                            priceLabels.push(price);
                        }
                    });
                }
            }
        }

        // Also check for price badges/badges on chart
        const badges = document.querySelectorAll('[class*="badge"], [class*="price"]');
        badges.forEach(badge => {
            const text = badge.textContent.trim();
            const price = parsePrice(text);
            if (price && price > 100 && price < 1000) {
                priceLabels.push(price);
            }
        });

        // Use spot price to estimate range if we can't find labels
        const spot = currentData?.spot || 700;
        
        if (priceLabels.length >= 2) {
            const high = Math.max(...priceLabels);
            const low = Math.min(...priceLabels);
            log(`Detected price range: ${low} - ${high}`);
            return { high, low, detected: true };
        }

        // Fallback: estimate based on spot
        log('Using estimated price range from spot');
        return { 
            high: spot + Math.max(30, spot * 0.05), 
            low: spot - Math.max(30, spot * 0.05), 
            detected: false 
        };
    }

    // Parse price from text like "$695.33" or "695.33"
    function parsePrice(text) {
        if (!text) return null;
        const cleaned = text.replace(/[$€£¥₹,\s]/g, '').trim();
        const price = parseFloat(cleaned);
        return isNaN(price) ? null : price;
    }

    // Calculate Y position for a price
    function priceToY(price, priceRange, containerHeight) {
        const { high, low } = priceRange;
        const range = high - low;
        if (range === 0) return containerHeight / 2;
        
        // Y increases as price decreases (in TradingView charts)
        const yPercent = (high - price) / range;
        return yPercent * containerHeight;
    }

    // Get color for level type
    function getColorForType(type) {
        const colors = {
            'CALL': CONFIG.CALL_COLOR,
            'PUT': CONFIG.PUT_COLOR,
            'FLIP': CONFIG.FLIP_COLOR,
            'NEUTRAL': CONFIG.NEUTRAL_COLOR
        };
        return colors[type] || CONFIG.NEUTRAL_COLOR;
    }

    // Create overlay elements for a confluence level
    function createOverlayElements(level, yPos, containerHeight) {
        const typeClass = `type-${level.type.toLowerCase()}`;
        const color = getColorForType(level.type);

        // Create line
        const line = document.createElement('div');
        line.className = `gex-confluence-line ${typeClass}`;
        line.style.top = `${yPos}px`;

        // Create label
        const label = document.createElement('div');
        label.className = `gex-confluence-label ${typeClass}`;
        
        // Format: "$STRIKE ⚡SCORE: X"
        const scoreClass = `gex-confluence-badge ${typeClass}`;
        label.innerHTML = `
            <span class="strike">$${level.strike.toFixed(2)}</span>
            <span class="${scoreClass}">⚡${level.score}</span>
        `;
        label.style.top = `${Math.max(5, yPos - 10)}px`;

        return { line, label };
    }

    // Clear all overlay elements
    function clearOverlays() {
        overlayElements.forEach(({ line, label }) => {
            if (line.parentNode) line.parentNode.removeChild(line);
            if (label.parentNode) label.parentNode.removeChild(label);
        });
        overlayElements = [];
    }

    // Update the status panel
    function updateStatusPanel(data) {
        if (!statusElement) return;

        const levelItems = data.confluence
            .slice(0, 5)
            .map(c => `
                <div class="level-item ${c.type.toLowerCase()}">
                    <span class="strike">$${c.strike.toFixed(2)}</span>
                    <span>[${c.type}]</span>
                    <span>⚡${c.score}</span>
                </div>
            `).join('');

        statusElement.innerHTML = `
            <div class="title">📊 QQQ GEX Confluence</div>
            <div>Spot: <b>$${data.spot.toFixed(2)}</b> | ${data.is_0dte ? '🎯 0DTE' : 'Standard'}</div>
            <div class="levels">${levelItems}</div>
            <div style="margin-top:5px;font-size:9px;color:#888;">Updated: ${data.updated}</div>
        `;
        statusElement.className = 'gex-confluence-status';
    }

    // Create status panel
    function createStatusPanel() {
        if (statusElement) return;
        
        statusElement = document.createElement('div');
        statusElement.className = 'gex-confluence-status';
        statusElement.innerHTML = '<div class="title">📊 QQQ GEX Confluence</div><div>Loading...</div>';
        document.body.appendChild(statusElement);
        log('Status panel created');
    }

    // Main update function
    async function updateOverlay() {
        log('Updating confluence overlay...');

        try {
            const data = await fetchGexData();
            currentData = data;
            log('Data received:', data);

            // Update status panel
            updateStatusPanel(data);

            // Find chart container
            const container = findChartContainer();
            if (!container) {
                log('ERROR: Could not find chart container');
                return;
            }

            // Ensure container has relative positioning
            const computedStyle = window.getComputedStyle(container);
            if (computedStyle.position === 'static') {
                container.style.position = 'relative';
            }

            // Get container dimensions
            const rect = container.getBoundingClientRect();
            const containerHeight = rect.height;
            const containerWidth = rect.width;

            log(`Container: ${containerWidth}x${containerHeight}`);

            // Get visible price range
            const priceRange = getVisiblePriceRange();
            log('Price range:', priceRange);

            // Clear old overlays
            clearOverlays();

            // Filter and sort confluence levels
            const levels = data.confluence
                .filter(c => c.score >= CONFIG.MIN_SCORE)
                .slice(0, CONFIG.MAX_LINES);

            log(`Drawing ${levels.length} confluence levels`);

            // Draw each level
            for (const level of levels) {
                const yPos = priceToY(level.strike, priceRange, containerHeight);

                // Skip if outside visible range
                if (yPos < -50 || yPos > containerHeight + 50) {
                    log(`Skipping ${level.strike} (outside visible range at Y=${yPos})`);
                    continue;
                }

                const { line, label } = createOverlayElements(level, yPos, containerHeight);
                container.appendChild(line);
                container.appendChild(label);
                overlayElements.push({ line, label });

                log(`Drew ${level.type} line at $${level.strike}, Y=${yPos.toFixed(1)}px`);
            }

            log(`Overlay update complete. Drew ${overlayElements.length} elements.`);

        } catch (error) {
            log('ERROR: ' + error.message);
            if (statusElement) {
                statusElement.innerHTML = `
                    <div class="title">📊 QQQ GEX Confluence</div>
                    <div style="color:#ff4444;">Error: ${error.message}</div>
                    <div style="font-size:9px;color:#888;">Retrying in 30s...</div>
                `;
                statusElement.className = 'gex-confluence-status error';
            }
        }
    }

    // Initialize
    function init() {
        log('GEX Confluence v3 initializing...');

        // Inject styles
        injectStyles();

        // Create status panel
        createStatusPanel();

        // Wait for chart to load, then update
        let attempts = 0;
        const maxAttempts = 30;

        function checkForChart() {
            attempts++;
            const container = findChartContainer();

            if (container) {
                log('Chart detected, starting overlay');
                updateOverlay();

                // Set up periodic updates
                if (updateTimer) clearInterval(updateTimer);
                updateTimer = setInterval(updateOverlay, REFRESH_INTERVAL);
            } else if (attempts < maxAttempts) {
                log(`Waiting for chart... (${attempts}/${maxAttempts})`);
                setTimeout(checkForChart, 1000);
            } else {
                log('Chart not found after timeout');
            }
        }

        checkForChart();

        // Handle SPA navigation
        const originalPushState = history.pushState;
        history.pushState = function() {
            originalPushState.apply(this, arguments);
            log('URL changed, rechecking for chart');
            setTimeout(() => {
                clearOverlays();
                checkForChart();
            }, 2000);
        };
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
