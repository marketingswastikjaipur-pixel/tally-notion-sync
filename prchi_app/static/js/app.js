/**
 * Prchi Voucher Notion Sync - Client Application Logic
 * Smart OCR (Tesseract.js WASM), Live Matching (Date + Cust + Price), Side-Peek Sync
 */

document.addEventListener('DOMContentLoaded', () => {
    // State
    let currentImageBase64 = null;
    let currentFilename = null;
    let pendingRecords = [];
    let currentTopMatch = null;
    let sessionReconciledCount = 0;

    // DOM Elements
    const cameraFileInput = document.getElementById('cameraFileInput');
    const galleryFileInput = document.getElementById('galleryFileInput');
    const dropZone = document.getElementById('dropZone');
    const dropZoneIdle = document.getElementById('dropZoneIdle');
    const previewContainer = document.getElementById('previewContainer');
    const imagePreview = document.getElementById('imagePreview');
    const btnRetake = document.getElementById('btnRetake');
    const btnRunOcrAgain = document.getElementById('btnRunOcrAgain');

    // Progress Elements
    const ocrProgressOverlay = document.getElementById('ocrProgressOverlay');
    const progressStatus = document.getElementById('progressStatus');
    const progressBarFill = document.getElementById('progressBarFill');
    const progressPct = document.getElementById('progressPct');

    // Field Inputs
    const inputDate = document.getElementById('inputDate');
    const inputPrice = document.getElementById('inputPrice');
    const inputCustomer = document.getElementById('inputCustomer');
    const rawOcrBox = document.getElementById('rawOcrBox');
    const btnManualMatch = document.getElementById('btnManualMatch');

    // Match Card Elements
    const matchIdle = document.getElementById('matchIdle');
    const matchCard = document.getElementById('matchCard');
    const matchStatusBadge = document.getElementById('matchStatusBadge');
    const matchScoreNumber = document.getElementById('matchScoreNumber');
    const matchVerdictTitle = document.getElementById('matchVerdictTitle');
    const matchVerdictDesc = document.getElementById('matchVerdictDesc');

    // Tags & Comp Table
    const tagDateMatch = document.getElementById('tagDateMatch');
    const tagPriceMatch = document.getElementById('tagPriceMatch');
    const tagCustomerMatch = document.getElementById('tagCustomerMatch');
    const tagDateVal = document.getElementById('tagDateVal');
    const tagPriceVal = document.getElementById('tagPriceVal');
    const tagCustomerVal = document.getElementById('tagCustomerVal');

    const compExtDate = document.getElementById('compExtDate');
    const compDbDate = document.getElementById('compDbDate');
    const compExtPrice = document.getElementById('compExtPrice');
    const compDbPrice = document.getElementById('compDbPrice');
    const compExtCustomer = document.getElementById('compExtCustomer');
    const compDbCustomer = document.getElementById('compDbCustomer');
    const compDbSites = document.getElementById('compDbSites');

    // Action Buttons
    const btnConfirmReconcile = document.getElementById('btnConfirmReconcile');
    const btnOpenNotionDirect = document.getElementById('btnOpenNotionDirect');
    const toggleMarkPrchi = document.getElementById('toggleMarkPrchi');

    // Other Candidates
    const candidatesContainer = document.getElementById('candidatesContainer');
    const candidatesList = document.getElementById('candidatesList');

    // Success State
    const successCard = document.getElementById('successCard');
    const btnSuccessNotionLink = document.getElementById('btnSuccessNotionLink');
    const btnScanNext = document.getElementById('btnScanNext');

    // Stats
    const statPending = document.getElementById('statPending');
    const statReconciledSession = document.getElementById('statReconciledSession');
    const btnRefreshDb = document.getElementById('btnRefreshDb');
    const refreshIcon = document.getElementById('refreshIcon');

    // Modals
    const btnMobileQr = document.getElementById('btnMobileQr');
    const qrModal = document.getElementById('qrModal');
    const btnCloseQrModal = document.getElementById('btnCloseQrModal');
    const qrImage = document.getElementById('qrImage');
    const qrUrlText = document.getElementById('qrUrlText');
    const btnCopyUrl = document.getElementById('btnCopyUrl');

    const btnBrowseDb = document.getElementById('btnBrowseDb');
    const recordsModal = document.getElementById('recordsModal');
    const btnCloseRecordsModal = document.getElementById('btnCloseRecordsModal');
    const recordSearchInput = document.getElementById('recordSearchInput');
    const recordsTableBody = document.getElementById('recordsTableBody');

    // 1. Initial Load of Pending Records
    fetchPendingRecords();

    async function fetchPendingRecords(force = false) {
        if (refreshIcon) refreshIcon.classList.add('spin');
        try {
            const resp = await fetch(`/api/records?refresh=${force}`);
            const data = await resp.json();
            if (data.success) {
                pendingRecords = data.records || [];
                statPending.textContent = pendingRecords.length;
            } else {
                console.error("Failed to load records:", data.error);
            }
        } catch (e) {
            console.error("Error fetching records:", e);
        } finally {
            if (refreshIcon) refreshIcon.classList.remove('spin');
        }
    }

    btnRefreshDb.addEventListener('click', () => fetchPendingRecords(true));

    // 2. File Upload & Camera Listeners
    cameraFileInput.addEventListener('change', (e) => handleFileSelect(e.target.files[0]));
    galleryFileInput.addEventListener('change', (e) => handleFileSelect(e.target.files[0]));

    // Drag & Drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    btnRetake.addEventListener('click', resetScanner);
    btnRunOcrAgain.addEventListener('click', () => {
        if (currentImageBase64) runOcrOnImage(currentImageBase64);
    });

    function resetScanner() {
        currentImageBase64 = null;
        currentFilename = null;
        currentTopMatch = null;
        previewContainer.classList.add('hidden');
        dropZoneIdle.classList.remove('hidden');
        imagePreview.src = '';
        inputDate.value = '';
        inputPrice.value = '';
        inputCustomer.value = '';
        rawOcrBox.textContent = 'No slip scanned yet.';
        matchCard.classList.add('hidden');
        candidatesContainer.classList.add('hidden');
        successCard.classList.add('hidden');
        matchIdle.classList.remove('hidden');
        matchStatusBadge.className = 'badge';
        matchStatusBadge.textContent = 'Waiting for scan';
        cameraFileInput.value = '';
        galleryFileInput.value = '';
    }

    btnScanNext.addEventListener('click', resetScanner);

    function handleFileSelect(file) {
        if (!file || !file.type.startsWith('image/')) {
            alert('Please select a valid image file.');
            return;
        }

        currentFilename = file.name;
        const reader = new FileReader();
        reader.onload = (e) => {
            currentImageBase64 = e.target.result;
            imagePreview.src = currentImageBase64;
            dropZoneIdle.classList.add('hidden');
            previewContainer.classList.remove('hidden');
            successCard.classList.add('hidden');
            runOcrOnImage(currentImageBase64);
        };
        reader.readAsDataURL(file);
    }

    // 3. Client-Side OCR Execution
    async function runOcrOnImage(imageSrc) {
        showProgress(true, 'Initializing OCR Engine...', 10);
        try {
            const worker = await Tesseract.createWorker('eng', 1, {
                logger: m => {
                    if (m.status === 'recognizing text') {
                        const pct = Math.round(m.progress * 100);
                        showProgress(true, `Reading Prchi Slip... ${pct}%`, pct);
                    }
                }
            });

            const ret = await worker.recognize(imageSrc);
            await worker.terminate();

            const ocrText = ret.data.text || '';
            rawOcrBox.textContent = ocrText || '(No text detected)';
            showProgress(false);

            // Process text & match with database
            await processSlipText(ocrText);
        } catch (e) {
            console.error("OCR Error:", e);
            showProgress(false);
            alert("OCR analysis error: " + e.message);
        }
    }

    function showProgress(show, text = '', pct = 0) {
        if (show) {
            ocrProgressOverlay.classList.remove('hidden');
            progressStatus.textContent = text;
            progressBarFill.style.width = pct + '%';
            progressPct.textContent = pct + '%';
        } else {
            ocrProgressOverlay.classList.add('hidden');
        }
    }

    // 4. Send OCR text to backend for parsing & ranking candidates
    async function processSlipText(ocrText, overrides = {}) {
        matchStatusBadge.className = 'badge badge-purple';
        matchStatusBadge.textContent = 'Matching...';

        try {
            const payload = {
                ocr_text: ocrText,
                image_base64: currentImageBase64,
                ...overrides
            };

            const resp = await fetch('/api/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await resp.json();
            if (!data.success) {
                alert("Error processing voucher: " + data.error);
                return;
            }

            const ext = data.extracted || {};
            // Populate input fields if not manually overridden
            if (!overrides.override_date) inputDate.value = ext.date || '';
            if (!overrides.override_price && !overrides.override_amount) {
                inputPrice.value = ext.price !== null && ext.price !== undefined ? ext.price : '';
            }
            if (!overrides.override_customer) inputCustomer.value = ext.customer_name || '';

            currentTopMatch = data.top_match;
            renderMatchResults(data.top_match, data.candidates || []);
        } catch (e) {
            console.error("Error processing slip text:", e);
        }
    }

    // Manual Re-match button listener
    btnManualMatch.addEventListener('click', () => {
        const overrides = {};
        if (inputDate.value) overrides.override_date = inputDate.value.trim();
        if (inputPrice.value) overrides.override_price = parseFloat(inputPrice.value.trim());
        if (inputCustomer.value) overrides.override_customer = inputCustomer.value.trim();

        processSlipText(rawOcrBox.textContent, overrides);
    });

    // 5. Render Match Results
    function renderMatchResults(topMatch, candidates) {
        matchIdle.classList.add('hidden');
        successCard.classList.add('hidden');

        if (!topMatch || topMatch.confidence < 20) {
            matchCard.classList.remove('hidden');
            matchStatusBadge.className = 'badge badge-amber';
            matchStatusBadge.textContent = 'No Close Match';

            matchScoreNumber.textContent = topMatch ? `${topMatch.confidence}%` : '0%';
            matchScoreNumber.style.color = '#f59e0b';
            matchVerdictTitle.textContent = 'No Clear Match in Database';
            matchVerdictDesc.textContent = 'Review extracted details on the left, or browse all pending records to match manually.';

            // Render whatever candidate we have or clear
            if (topMatch) {
                renderComparisonDetails(topMatch);
            }
            renderCandidatesList(candidates);
            return;
        }

        matchCard.classList.remove('hidden');
        renderComparisonDetails(topMatch);

        // Score formatting
        matchScoreNumber.textContent = `${topMatch.confidence}%`;
        if (topMatch.confidence >= 75) {
            matchStatusBadge.className = 'badge badge-emerald';
            matchStatusBadge.textContent = 'High Match';
            matchScoreNumber.style.color = '#10b981';
            matchVerdictTitle.textContent = 'High Confidence Match';
            matchVerdictDesc.textContent = 'Date, Customer Name, and Price aligned with this row.';
        } else {
            matchStatusBadge.className = 'badge badge-amber';
            matchStatusBadge.textContent = 'Partial Match';
            matchScoreNumber.style.color = '#f59e0b';
            matchVerdictTitle.textContent = 'Partial Candidate Found';
            matchVerdictDesc.textContent = 'Some fields matched. Verify values before confirming.';
        }

        renderCandidatesList(candidates);
    }

    function renderComparisonDetails(matchObj) {
        const rec = matchObj.record;
        const details = matchObj.match_details || {};

        // Breakdown pills
        tagDateVal.textContent = details.date_match ? 'Matched' : (details.date_score > 0 ? 'Close' : 'No');
        tagDateMatch.className = details.date_match ? 'pill pill-success' : 'pill pill-dim';

        tagPriceVal.textContent = details.price_match ? 'Matched' : (details.price_score > 0 ? 'Close' : 'No');
        tagPriceMatch.className = details.price_match ? 'pill pill-success' : 'pill pill-dim';

        tagCustomerVal.textContent = details.customer_match ? 'Matched' : (details.customer_score > 0 ? 'Partial' : 'No');
        tagCustomerMatch.className = details.customer_match ? 'pill pill-success' : 'pill pill-dim';

        // Table comparisons
        compExtDate.textContent = inputDate.value || 'None';
        compDbDate.textContent = rec.date || 'Empty';

        compExtPrice.textContent = inputPrice.value ? `₹${inputPrice.value}` : 'None';
        compDbPrice.textContent = rec.price !== null && rec.price !== undefined ? `₹${rec.price}` : 'Empty';

        compExtCustomer.textContent = inputCustomer.value || 'None';
        compDbCustomer.textContent = rec.customer_name || 'Empty';
        compDbSites.textContent = rec.sites || '-';

        // Direct Notion link
        btnOpenNotionDirect.href = rec.url;
    }

    function renderCandidatesList(candidates) {
        if (!candidates || candidates.length <= 1) {
            candidatesContainer.classList.add('hidden');
            return;
        }

        candidatesContainer.classList.remove('hidden');
        candidatesList.innerHTML = '';

        // Show candidates 2..5
        candidates.slice(1).forEach((cand, idx) => {
            const r = cand.record;
            const div = document.createElement('div');
            div.className = 'candidate-row';
            div.innerHTML = `
                <div>
                    <strong>${r.customer_name || r.sites || 'Unknown'}</strong>
                    <div style="font-size: 0.78rem; color: var(--text-muted);">
                        Date: ${r.date || '-'} • Price: ₹${r.price || 0}
                    </div>
                </div>
                <div class="candidate-score">${cand.confidence}% Match</div>
            `;
            div.addEventListener('click', () => {
                currentTopMatch = cand;
                renderComparisonDetails(cand);
            });
            candidatesList.appendChild(div);
        });
    }

    // 6. Confirm & Reconcile in Notion
    btnConfirmReconcile.addEventListener('click', async () => {
        if (!currentTopMatch || !currentTopMatch.record) {
            alert('No candidate selected for reconciliation.');
            return;
        }

        const rec = currentTopMatch.record;
        const pageId = rec.id;
        const markPrchi = toggleMarkPrchi.checked;

        btnConfirmReconcile.disabled = true;
        btnConfirmReconcile.innerHTML = `<span class="spinner" style="width: 18px; height: 18px; display: inline-block;"></span> Syncing to Notion...`;

        try {
            const payload = {
                page_id: pageId,
                image_base64: currentImageBase64,
                filename: currentFilename,
                mark_prchi: markPrchi,
                metadata: {
                    date: inputDate.value,
                    price: inputPrice.value,
                    customer_name: inputCustomer.value
                }
            };

            const resp = await fetch('/api/sync-notion', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await resp.json();
            if (!data.success) {
                alert('Reconciliation failed: ' + data.error);
                return;
            }

            // Success Transition
            matchCard.classList.add('hidden');
            candidatesContainer.classList.add('hidden');
            successCard.classList.remove('hidden');

            const prchiStatus = data.prchi_marked ? "PRCHI checkbox marked True" : "PRCHI checkbox left untouched";
            document.getElementById('successDesc').textContent = `Voucher photo attached to side peek (${prchiStatus}). Remarks & other columns remained untouched.`;
            btnSuccessNotionLink.href = data.notion_url;

            sessionReconciledCount++;
            statReconciledSession.textContent = sessionReconciledCount;

            // Remove reconciled record from local list
            pendingRecords = pendingRecords.filter(r => r.id !== pageId);
            statPending.textContent = pendingRecords.length;

        } catch (e) {
            console.error("Reconciliation error:", e);
            alert("Error syncing to Notion: " + e.message);
        } finally {
            btnConfirmReconcile.disabled = false;
            btnConfirmReconcile.innerHTML = `<i data-lucide="check-check"></i><span>Confirm & Reconcile in Notion</span>`;
            lucide.createIcons();
        }
    });

    // 7. Mobile QR Modal
    btnMobileQr.addEventListener('click', async () => {
        qrModal.classList.remove('hidden');
        try {
            const resp = await fetch('/api/mobile-qr');
            const data = await resp.json();
            if (data.success) {
                qrImage.src = data.qr_base64;
                qrUrlText.textContent = data.mobile_url;
            }
        } catch (e) {
            qrUrlText.textContent = "Error loading QR code";
        }
    });

    btnCloseQrModal.addEventListener('click', () => qrModal.classList.add('hidden'));
    btnCopyUrl.addEventListener('click', () => {
        navigator.clipboard.writeText(qrUrlText.textContent);
        alert('Copied URL to clipboard!');
    });

    // 8. Browse Pending Records Drawer
    btnBrowseDb.addEventListener('click', () => {
        recordsModal.classList.remove('hidden');
        renderRecordsTable(pendingRecords);
    });

    btnCloseRecordsModal.addEventListener('click', () => recordsModal.classList.add('hidden'));

    recordSearchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        const filtered = pendingRecords.filter(r => {
            const cust = (r.customer_name || '').toLowerCase();
            const site = (r.sites || '').toLowerCase();
            const dt = (r.date || '').toLowerCase();
            const pr = String(r.price || '');
            return cust.includes(query) || site.includes(query) || dt.includes(query) || pr.includes(query);
        });
        renderRecordsTable(filtered);
    });

    function renderRecordsTable(records) {
        recordsTableBody.innerHTML = '';
        if (!records.length) {
            recordsTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No records found.</td></tr>`;
            return;
        }

        records.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${r.date || '-'}</strong></td>
                <td>${r.customer_name || '-'}</td>
                <td style="color: var(--text-muted); font-size: 0.8rem;">${r.sites || '-'}</td>
                <td style="font-weight: 700; color: #34d399;">₹${r.price !== null ? r.price : '-'}</td>
                <td>
                    <button class="btn btn-glass" style="padding: 4px 10px; font-size: 0.75rem;">
                        Select
                    </button>
                </td>
            `;

            tr.querySelector('button').addEventListener('click', () => {
                recordsModal.classList.add('hidden');
                currentTopMatch = {
                    record: r,
                    confidence: 100,
                    status: 'manual_selection',
                    match_details: { date_match: true, price_match: true, customer_match: true }
                };
                renderMatchResults(currentTopMatch, []);
            });

            recordsTableBody.appendChild(tr);
        });
    }

    // Close modals on clicking backdrop
    window.addEventListener('click', (e) => {
        if (e.target === qrModal) qrModal.classList.add('hidden');
        if (e.target === recordsModal) recordsModal.classList.add('hidden');
    });
});
