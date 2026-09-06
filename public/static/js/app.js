/**
 * Tally Voucher OCR & Notion Sync Application
 * Core Client-Side Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    // Lucide Icons Initialization
    if (window.lucide) {
        lucide.createIcons();
    }

    // App State
    const state = {
        records: [],
        filteredRecords: [],
        currentFilter: 'all',
        searchTerm: '',
        currentImageBase64: null,
        currentFilename: null,
        rotationAngle: 0,
        ocrText: '',
        extractedData: null,
        topMatch: null,
        candidates: [],
        webcamStream: null,
        autoSync: true,
        isProcessing: false
    };

    // DOM Elements
    const elements = {
        // Stats
        statTotal: document.getElementById('statTotal'),
        statReconciled: document.getElementById('statReconciled'),
        statPending: document.getElementById('statPending'),
        toggleAutoSync: document.getElementById('toggleAutoSync'),
        btnRefreshDb: document.getElementById('btnRefreshDb'),
        refreshIcon: document.getElementById('refreshIcon'),
        btnMobileQr: document.getElementById('btnMobileQr'),

        // Inputs & Dropzone
        cameraFileInput: document.getElementById('cameraFileInput'),
        fileUploadInput: document.getElementById('fileUploadInput'),
        btnWebcamToggle: document.getElementById('btnWebcamToggle'),
        dropzone: document.getElementById('dropzone'),
        dropzoneEmpty: document.getElementById('dropzoneEmpty'),
        videoContainer: document.getElementById('videoContainer'),
        webcamVideo: document.getElementById('webcamVideo'),
        btnTakeSnapshot: document.getElementById('btnTakeSnapshot'),
        previewContainer: document.getElementById('previewContainer'),
        imagePreview: document.getElementById('imagePreview'),
        btnRotateLeft: document.getElementById('btnRotateLeft'),
        btnRotateRight: document.getElementById('btnRotateRight'),
        btnReOCR: document.getElementById('btnReOCR'),
        btnClearImage: document.getElementById('btnClearImage'),

        // OCR
        ocrProgressContainer: document.getElementById('ocrProgressContainer'),
        ocrStatusText: document.getElementById('ocrStatusText'),
        ocrPercentText: document.getElementById('ocrPercentText'),
        ocrProgressBar: document.getElementById('ocrProgressBar'),

        // Extracted Card
        inputInvoiceNo: document.getElementById('inputInvoiceNo'),
        inputAmount: document.getElementById('inputAmount'),
        inputDate: document.getElementById('inputDate'),
        inputCustomerName: document.getElementById('inputCustomerName'),
        rawOcrText: document.getElementById('rawOcrText'),
        extractConfidenceBadge: document.getElementById('extractConfidenceBadge'),

        // Match Card
        matchIdle: document.getElementById('matchIdle'),
        matchCard: document.getElementById('matchCard'),
        scoreCircle: document.getElementById('scoreCircle'),
        scoreText: document.getElementById('scoreText'),
        matchHeading: document.getElementById('matchHeading'),
        matchSub: document.getElementById('matchSub'),
        cardConfidenceBadge: document.getElementById('cardConfidenceBadge'),
        matchStatusBadge: document.getElementById('matchStatusBadge'),
        
        cmpScannedInv: document.getElementById('cmpScannedInv'),
        cmpNotionInv: document.getElementById('cmpNotionInv'),
        cmpInvIcon: document.getElementById('cmpInvIcon'),

        cmpScannedAmt: document.getElementById('cmpScannedAmt'),
        cmpNotionAmt: document.getElementById('cmpNotionAmt'),
        cmpAmtIcon: document.getElementById('cmpAmtIcon'),

        cmpScannedDate: document.getElementById('cmpScannedDate'),
        cmpNotionDate: document.getElementById('cmpNotionDate'),
        cmpDateIcon: document.getElementById('cmpDateIcon'),

        cmpScannedCust: document.getElementById('cmpScannedCust'),
        cmpNotionCust: document.getElementById('cmpNotionCust'),
        cmpCustIcon: document.getElementById('cmpCustIcon'),


        targetCustomerTitle: document.getElementById('targetCustomerTitle'),
        targetCurrentRcg: document.getElementById('targetCurrentRcg'),
        targetDate: document.getElementById('targetDate'),

        btnSyncNotion: document.getElementById('btnSyncNotion'),
        btnSyncText: document.getElementById('btnSyncText'),
        btnOpenNotion: document.getElementById('btnOpenNotion'),
        syncStatusBox: document.getElementById('syncStatusBox'),
        syncStatusMessage: document.getElementById('syncStatusMessage'),

        candidatesSection: document.getElementById('candidatesSection'),
        candidatesList: document.getElementById('candidatesList'),

        // Table
        tableSearchInput: document.getElementById('tableSearchInput'),
        tabBtns: document.querySelectorAll('.tab-btn'),
        countAll: document.getElementById('countAll'),
        countPending: document.getElementById('countPending'),
        countReconciled: document.getElementById('countReconciled'),
        tableBody: document.getElementById('tableBody'),

        // Modal
        qrModal: document.getElementById('qrModal'),
        btnCloseQrModal: document.getElementById('btnCloseQrModal'),
        qrImage: document.getElementById('qrImage'),
        mobileUrlText: document.getElementById('mobileUrlText'),
        btnCopyMobileUrl: document.getElementById('btnCopyMobileUrl'),

        // Audio
        audioSuccess: document.getElementById('audioSuccess'),
        audioScan: document.getElementById('audioScan')
    };

    // =========================================================================
    // 1. Data Fetching & Database Table
    // =========================================================================
    async function loadRecords(forceRefresh = false) {
        try {
            if (elements.refreshIcon) {
                elements.refreshIcon.classList.add('spin-icon');
            }
            const res = await fetch(`/api/records?refresh=${forceRefresh}`);
            const data = await res.json();
            if (data.success) {
                state.records = data.records;
                updateStats(data);
                renderTable();
            } else {
                console.error("Failed to load records:", data.error);
            }
        } catch (err) {
            console.error("Error fetching Notion records:", err);
        } finally {
            if (elements.refreshIcon) {
                setTimeout(() => elements.refreshIcon.classList.remove('spin-icon'), 500);
            }
        }
    }

    function updateStats(data) {
        elements.statTotal.textContent = data.count || 0;
        elements.statReconciled.textContent = data.reconciled_count || 0;
        elements.statPending.textContent = data.pending_count || 0;
        
        elements.countAll.textContent = data.count || 0;
        elements.countPending.textContent = data.pending_count || 0;
        elements.countReconciled.textContent = data.reconciled_count || 0;
    }

    function renderTable() {
        const term = state.searchTerm.toLowerCase().trim();
        let filtered = state.records.filter(r => {
            // Tab filter
            if (state.currentFilter === 'pending' && r.rcg) return false;
            if (state.currentFilter === 'reconciled' && !r.rcg) return false;

            // Search filter
            if (term) {
                const cust = (r.customer_name || '').toLowerCase();
                const inv = (r.invoice_no || '').toLowerCase();
                const amt = String(r.amount || '');
                const rem = (r.remarks || '').toLowerCase();
                return cust.includes(term) || inv.includes(term) || amt.includes(term) || rem.includes(term);
            }
            return true;
        });

        state.filteredRecords = filtered;

        if (filtered.length === 0) {
            elements.tableBody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center py-6 text-muted">
                        No records match the selected filter.
                    </td>
                </tr>
            `;
            return;
        }

        elements.tableBody.innerHTML = filtered.map(r => {
            const isMatched = state.topMatch && state.topMatch.record.id === r.id;
            const rcgBadge = r.rcg
                ? `<span class="badge badge-emerald"><i data-lucide="check" style="width:12px;height:12px;margin-right:2px;"></i> Reconciled</span>`
                : `<span class="badge badge-amber"><i data-lucide="clock" style="width:12px;height:12px;margin-right:2px;"></i> Pending</span>`;

            const formattedAmount = r.amount != null 
                ? Number(r.amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                : '-';

            return `
                <tr class="${isMatched ? 'table-row-matched' : ''}" data-id="${r.id}">
                    <td>${rcgBadge}</td>
                    <td><strong>${escapeHtml(r.customer_name || '-')}</strong></td>
                    <td class="mono">${escapeHtml(r.invoice_no || '-')}</td>
                    <td class="mono font-bold">₹ ${formattedAmount}</td>
                    <td>${r.date ? escapeHtml(r.date) : '<span class="text-muted">-</span>'}</td>
                    <td><small class="text-secondary">${escapeHtml(r.remarks || '-')}</small></td>
                    <td>
                        <div style="display: flex; gap: 0.35rem;">
                            <a href="${r.url}" target="_blank" class="tool-btn" title="Open in Notion Side Peek">
                                <i data-lucide="external-link" style="width:13px;height:13px;"></i>
                            </a>
                            <button class="tool-btn btn-select-row" data-id="${r.id}" title="Select for sync">
                                Match
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

        if (window.lucide) {
            lucide.createIcons();
        }

        // Add row select event listeners
        document.querySelectorAll('.btn-select-row').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = e.currentTarget.dataset.id;
                const rec = state.records.find(r => r.id === id);
                if (rec) {
                    manuallySelectRecord(rec);
                }
            });
        });
    }

    // =========================================================================
    // 2. Image Handling & Capture
    // =========================================================================
    elements.cameraFileInput.addEventListener('change', handleFileSelect);
    elements.fileUploadInput.addEventListener('change', handleFileSelect);

    function handleFileSelect(e) {
        const file = e.target.files[0];
        if (file) {
            processImageFile(file);
        }
    }

    // Drag & Drop
    elements.dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.dropzone.classList.add('dragover');
    });

    elements.dropzone.addEventListener('dragleave', () => {
        elements.dropzone.classList.remove('dragover');
    });

    elements.dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        elements.dropzone.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            processImageFile(e.dataTransfer.files[0]);
        }
    });

    // Clipboard Paste
    window.addEventListener('paste', (e) => {
        const items = (e.clipboardData || e.originalEvent.clipboardData).items;
        for (let item of items) {
            if (item.kind === 'file' && item.type.startsWith('image/')) {
                const blob = item.getAsFile();
                processImageFile(blob);
                break;
            }
        }
    });

    function processImageFile(file) {
        stopWebcam();
        const reader = new FileReader();
        reader.onload = (e) => {
            state.currentImageBase64 = e.target.result;
            state.rotationAngle = 0;
            displayImagePreview(state.currentImageBase64);
            runOCR(state.currentImageBase64);
        };
        reader.readAsDataURL(file);
    }

    function displayImagePreview(src) {
        elements.dropzoneEmpty.style.display = 'none';
        elements.videoContainer.style.display = 'none';
        elements.previewContainer.style.display = 'flex';
        elements.imagePreview.src = src;
        elements.imagePreview.style.transform = `rotate(${state.rotationAngle}deg)`;
    }

    // Image Tools
    elements.btnRotateLeft.addEventListener('click', () => rotateImage(-90));
    elements.btnRotateRight.addEventListener('click', () => rotateImage(90));
    elements.btnReOCR.addEventListener('click', () => {
        if (state.currentImageBase64) {
            runOCR(state.currentImageBase64);
        }
    });
    elements.btnClearImage.addEventListener('click', resetScannerState);

    function rotateImage(delta) {
        state.rotationAngle = (state.rotationAngle + delta) % 360;
        elements.imagePreview.style.transform = `rotate(${state.rotationAngle}deg)`;
        
        // Render rotated image to canvas to get new base64
        const img = new Image();
        img.onload = () => {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            if (Math.abs(state.rotationAngle) === 90 || Math.abs(state.rotationAngle) === 270) {
                canvas.width = img.height;
                canvas.height = img.width;
            } else {
                canvas.width = img.width;
                canvas.height = img.height;
            }
            ctx.translate(canvas.width / 2, canvas.height / 2);
            ctx.rotate((state.rotationAngle * Math.PI) / 180);
            ctx.drawImage(img, -img.width / 2, -img.height / 2);
            state.currentImageBase64 = canvas.toDataURL('image/jpeg', 0.92);
            runOCR(state.currentImageBase64);
        };
        img.src = elements.imagePreview.src;
    }

    function resetScannerState() {
        stopWebcam();
        state.currentImageBase64 = null;
        state.rotationAngle = 0;
        state.ocrText = '';
        state.extractedData = null;
        state.topMatch = null;

        elements.dropzoneEmpty.style.display = 'flex';
        elements.previewContainer.style.display = 'none';
        elements.ocrProgressContainer.style.display = 'none';

        elements.inputInvoiceNo.value = '';
        elements.inputAmount.value = '';
        elements.inputCustomerName.value = '';
        elements.rawOcrText.value = '';
        elements.extractConfidenceBadge.textContent = 'Ready';

        elements.matchIdle.style.display = 'flex';
        elements.matchCard.style.display = 'none';
        elements.matchStatusBadge.textContent = 'Waiting for scan';
        elements.matchStatusBadge.className = 'badge';
        elements.syncStatusBox.style.display = 'none';
        elements.btnOpenNotion.style.display = 'none';

        renderTable();
    }

    // Webcam Live Stream
    elements.btnWebcamToggle.addEventListener('click', toggleWebcam);
    elements.btnTakeSnapshot.addEventListener('click', captureWebcamSnapshot);

    async function toggleWebcam() {
        if (state.webcamStream) {
            stopWebcam();
        } else {
            try {
                elements.dropzoneEmpty.style.display = 'none';
                elements.previewContainer.style.display = 'none';
                elements.videoContainer.style.display = 'flex';

                const constraints = {
                    video: {
                        facingMode: { ideal: 'environment' },
                        width: { ideal: 1920 },
                        height: { ideal: 1080 }
                    }
                };
                state.webcamStream = await navigator.mediaDevices.getUserMedia(constraints);
                elements.webcamVideo.srcObject = state.webcamStream;
            } catch (err) {
                alert("Camera access error: " + err.message);
                elements.dropzoneEmpty.style.display = 'flex';
                elements.videoContainer.style.display = 'none';
            }
        }
    }

    function stopWebcam() {
        if (state.webcamStream) {
            state.webcamStream.getTracks().forEach(track => track.stop());
            state.webcamStream = null;
        }
        elements.videoContainer.style.display = 'none';
    }

    function captureWebcamSnapshot() {
        if (!state.webcamStream) return;
        const video = elements.webcamVideo;
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth || 1280;
        canvas.height = video.videoHeight || 720;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        stopWebcam();
        playSound(elements.audioScan);
        state.currentImageBase64 = canvas.toDataURL('image/jpeg', 0.95);
        displayImagePreview(state.currentImageBase64);
        runOCR(state.currentImageBase64);
    }

    // =========================================================================
    // 3. Client & Server Multi-Engine OCR & Parsing
    // =========================================================================
    function preprocessImageForOCR(imageSource) {
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                
                // Scale up small images for better OCR resolution
                let width = img.width;
                let height = img.height;
                const minDimension = 1600;
                if (width < minDimension && height < minDimension) {
                    const scale = Math.max(minDimension / width, minDimension / height);
                    width = Math.round(width * scale);
                    height = Math.round(height * scale);
                }

                canvas.width = width;
                canvas.height = height;
                ctx.drawImage(img, 0, 0, width, height);

                // Get pixel data for contrast enhancement and grayscale
                const imgData = ctx.getImageData(0, 0, width, height);
                const d = imgData.data;

                for (let i = 0; i < d.length; i += 4) {
                    // Grayscale
                    const gray = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
                    // Contrast stretch
                    const contrast = 1.35;
                    const factor = (259 * (contrast + 255)) / (255 * (259 - contrast));
                    const highContrast = Math.min(255, Math.max(0, factor * (gray - 128) + 128));

                    d[i] = highContrast;
                    d[i + 1] = highContrast;
                    d[i + 2] = highContrast;
                }

                ctx.putImageData(imgData, 0, 0);
                resolve(canvas.toDataURL('image/jpeg', 0.95));
            };
            img.onerror = () => resolve(imageSource);
            img.src = imageSource;
        });
    }

    async function runOCR(imageSource) {
        if (state.isProcessing) return;
        state.isProcessing = true;

        elements.ocrProgressContainer.style.display = 'flex';
        elements.ocrStatusText.textContent = 'Enhancing image for text recognition...';
        elements.ocrProgressBar.style.width = '10%';
        elements.ocrPercentText.textContent = '10%';
        elements.extractConfidenceBadge.textContent = 'Scanning...';
        elements.extractConfidenceBadge.className = 'badge badge-purple';

        try {
            // Preprocess image to make text ultra-crisp
            const enhancedImage = await preprocessImageForOCR(imageSource);

            // Step 1: Run Tesseract.js client-side
            let ocrText = "";
            if (window.Tesseract) {
                const worker = await Tesseract.createWorker('eng', 1, {
                    logger: m => {
                        if (m.status === 'recognizing text') {
                            const pct = Math.round(m.progress * 100);
                            elements.ocrProgressBar.style.width = `${pct}%`;
                            elements.ocrPercentText.textContent = `${pct}%`;
                            elements.ocrStatusText.textContent = 'Analyzing voucher text & numbers...';
                        }
                    }
                });
                const ret = await worker.recognize(enhancedImage);
                ocrText = ret.data.text;
                await worker.terminate();
            }

            state.ocrText = ocrText;
            elements.rawOcrText.value = ocrText;
            elements.ocrProgressBar.style.width = '100%';
            elements.ocrPercentText.textContent = '100%';
            elements.ocrStatusText.textContent = 'Reconciling with Notion database...';

            // Step 2: Send OCR text & image to backend match engine
            await sendToBackendProcess(ocrText, imageSource);

        } catch (err) {
            console.error("OCR / Recognition error:", err);
            elements.ocrStatusText.textContent = 'Error: ' + err.message;
        } finally {
            state.isProcessing = false;
            setTimeout(() => {
                elements.ocrProgressContainer.style.display = 'none';
            }, 800);
        }
    }


    async function sendToBackendProcess(ocrText, imageBase64, overrides = {}) {
        const payload = {
            ocr_text: ocrText,
            image_base64: imageBase64,
            ...overrides
        };

        const res = await fetch('/api/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (data.success) {
            state.extractedData = data.extracted;
            state.topMatch = data.top_match;
            state.candidates = data.candidates || [];
            state.currentFilename = data.saved_filename;

            // Populate Extracted Fields
            elements.inputInvoiceNo.value = data.extracted.invoice_no || '';
            elements.inputAmount.value = data.extracted.amount != null ? data.extracted.amount : '';
            elements.inputDate.value = data.extracted.date || '';
            elements.inputCustomerName.value = data.extracted.customer_name || '';

            elements.extractConfidenceBadge.textContent = data.extracted.has_extraction ? 'Extracted' : 'Partial';
            elements.extractConfidenceBadge.className = data.extracted.has_extraction ? 'badge badge-emerald' : 'badge badge-amber';

            // Update Match Card
            updateMatchCard(data.top_match, data.candidates);
            renderTable();

            // Auto-Sync if enabled and confidence >= 80%
            if (elements.toggleAutoSync.checked && data.top_match && data.top_match.confidence >= 80) {
                triggerNotionSync(data.top_match.record.id, false);
            }
        } else {
            alert("Processing error: " + data.error);
        }
    }

    // Manual Quick Edit Trigger
    [elements.inputInvoiceNo, elements.inputAmount, elements.inputDate, elements.inputCustomerName].forEach(input => {
        input.addEventListener('change', () => {
            if (state.ocrText || state.currentImageBase64) {
                sendToBackendProcess(state.ocrText, state.currentImageBase64, {
                    override_invoice: elements.inputInvoiceNo.value,
                    override_amount: elements.inputAmount.value,
                    override_date: elements.inputDate.value,
                    override_customer: elements.inputCustomerName.value
                });
            }
        });
    });

    // =========================================================================
    // 4. Notion Match & Sync UI
    // =========================================================================
    function updateMatchCard(topMatch, candidates) {
        if (!topMatch || topMatch.confidence <= 0) {
            elements.matchIdle.style.display = 'flex';
            elements.matchCard.style.display = 'none';
            elements.matchStatusBadge.textContent = 'No Match Found';
            elements.matchStatusBadge.className = 'badge badge-amber';
            return;
        }

        elements.matchIdle.style.display = 'none';
        elements.matchCard.style.display = 'flex';

        const conf = topMatch.confidence;
        elements.scoreText.textContent = `${conf}%`;
        elements.cardConfidenceBadge.textContent = `${conf}% Match`;

        if (conf >= 80) {
            elements.scoreCircle.style.borderColor = 'var(--emerald-400)';
            elements.scoreCircle.style.color = 'var(--emerald-400)';
            elements.cardConfidenceBadge.className = 'badge badge-emerald';
            elements.matchHeading.textContent = 'High Confidence Match';
            elements.matchStatusBadge.textContent = 'Exact Match Ready';
            elements.matchStatusBadge.className = 'badge badge-emerald';
        } else if (conf >= 45) {
            elements.scoreCircle.style.borderColor = 'var(--amber-400)';
            elements.scoreCircle.style.color = 'var(--amber-400)';
            elements.cardConfidenceBadge.className = 'badge badge-amber';
            elements.matchHeading.textContent = 'Partial Match Found';
            elements.matchStatusBadge.textContent = 'Review & Confirm';
            elements.matchStatusBadge.className = 'badge badge-amber';
        } else {
            elements.scoreCircle.style.borderColor = 'var(--violet-400)';
            elements.scoreCircle.style.color = 'var(--violet-400)';
            elements.cardConfidenceBadge.className = 'badge badge-purple';
            elements.matchHeading.textContent = 'Low Confidence Match';
            elements.matchStatusBadge.textContent = 'Verify Row';
            elements.matchStatusBadge.className = 'badge badge-purple';
        }

        const ext = state.extractedData || {};
        const rec = topMatch.record;
        const details = topMatch.match_details || {};

        // Comparison Rows
        elements.cmpScannedInv.textContent = ext.invoice_no || '(Not detected)';
        elements.cmpNotionInv.textContent = rec.invoice_no || '(Empty)';
        setMatchIcon(elements.cmpInvIcon, details.invoice_match);

        elements.cmpScannedAmt.textContent = ext.amount != null ? `₹ ${ext.amount}` : '(Not detected)';
        elements.cmpNotionAmt.textContent = rec.amount != null ? `₹ ${rec.amount}` : '(Empty)';
        setMatchIcon(elements.cmpAmtIcon, details.amount_match);

        elements.cmpScannedDate.textContent = ext.date || '(Not detected)';
        elements.cmpNotionDate.textContent = rec.date || '(No date)';
        setMatchIcon(elements.cmpDateIcon, details.date_match);

        elements.cmpScannedCust.textContent = ext.customer_name || '(Not detected)';
        elements.cmpNotionCust.textContent = rec.customer_name || '(Empty)';
        setMatchIcon(elements.cmpCustIcon, details.customer_match);

        // Target Info
        elements.targetCustomerTitle.textContent = rec.customer_name || 'Unnamed Record';
        elements.targetCurrentRcg.textContent = rec.rcg ? 'True (Reconciled)' : 'False (Pending)';
        elements.targetCurrentRcg.className = rec.rcg ? 'badge badge-emerald' : 'badge badge-amber';
        elements.targetDate.textContent = rec.date || 'No date';


        // Candidates List
        if (candidates && candidates.length > 1) {
            elements.candidatesSection.style.display = 'block';
            elements.candidatesList.innerHTML = candidates.slice(1).map(c => `
                <div class="candidate-item" data-id="${c.record.id}">
                    <div>
                        <strong>${escapeHtml(c.record.customer_name || 'Unnamed')}</strong>
                        <small class="text-muted" style="margin-left:8px;">${escapeHtml(c.record.invoice_no || '')} &bull; ₹${c.record.amount || '-'}</small>
                    </div>
                    <span class="badge badge-subtle">${c.confidence}%</span>
                </div>
            `).join('');

            document.querySelectorAll('.candidate-item').forEach(item => {
                item.addEventListener('click', (e) => {
                    const cid = e.currentTarget.dataset.id;
                    const selected = candidates.find(c => c.record.id === cid);
                    if (selected) {
                        state.topMatch = selected;
                        updateMatchCard(selected, candidates);
                    }
                });
            });
        } else {
            elements.candidatesSection.style.display = 'none';
        }

        // Reset sync status box
        elements.syncStatusBox.style.display = 'none';
        elements.btnOpenNotion.style.display = 'none';
        elements.btnSyncNotion.disabled = false;
        elements.btnSyncText.textContent = 'Mark RCG & Upload Photo to Notion';
    }

    function setMatchIcon(el, isMatch) {
        if (isMatch) {
            el.innerHTML = '<i data-lucide="check" style="color: var(--emerald-400); width:16px; height:16px;"></i>';
        } else {
            el.innerHTML = '<i data-lucide="alert-circle" style="color: var(--amber-400); width:16px; height:16px;"></i>';
        }
        if (window.lucide) lucide.createIcons();
    }

    function manuallySelectRecord(record) {
        state.topMatch = {
            record: record,
            confidence: 100,
            status: 'manual_selection',
            match_details: {
                invoice_match: true,
                amount_match: true,
                customer_match: true
            }
        };
        updateMatchCard(state.topMatch, state.candidates);
        elements.matchHeading.textContent = 'Manually Selected Target';
        renderTable();
    }

    // =========================================================================
    // 5. Notion Sync Execution
    // =========================================================================
    elements.btnSyncNotion.addEventListener('click', () => {
        if (state.topMatch && state.topMatch.record) {
            triggerNotionSync(state.topMatch.record.id, true);
        }
    });

    async function triggerNotionSync(pageId, isManualClick = true) {
        if (!pageId) return;

        elements.btnSyncNotion.disabled = true;
        elements.btnSyncText.innerHTML = '<span class="loading-spinner"></span> Updating Notion & Uploading Photo...';

        try {
            const ext = state.extractedData || {};
            const payload = {
                page_id: pageId,
                filename: state.currentFilename,
                image_base64: state.currentImageBase64,
                metadata: {
                    invoice_no: ext.invoice_no || elements.inputInvoiceNo.value,
                    amount: ext.amount != null ? ext.amount : elements.inputAmount.value,
                    customer_name: ext.customer_name || elements.inputCustomerName.value,
                    add_remark: true
                }
            };

            const res = await fetch('/api/sync-notion', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (data.success) {
                playSound(elements.audioSuccess);

                elements.syncStatusBox.style.display = 'flex';
                elements.syncStatusMessage.innerHTML = `
                    <strong>Reconciliation Success!</strong> Row marked <span class="text-emerald">RCG: True</span> in Notion, and voucher photo was attached to side peek.
                `;

                elements.btnOpenNotion.href = data.notion_url;
                elements.btnOpenNotion.style.display = 'inline-flex';

                elements.btnSyncText.textContent = '✔ Synced to Notion';
                elements.targetCurrentRcg.textContent = 'True (Reconciled)';
                elements.targetCurrentRcg.className = 'badge badge-emerald';

                // Refresh Database Table
                await loadRecords(true);

            } else {
                alert("Failed to sync to Notion: " + data.error);
                elements.btnSyncNotion.disabled = false;
                elements.btnSyncText.textContent = 'Retry Sync to Notion';
            }
        } catch (err) {
            console.error("Sync error:", err);
            alert("Error syncing to Notion: " + err.message);
            elements.btnSyncNotion.disabled = false;
            elements.btnSyncText.textContent = 'Retry Sync to Notion';
        }
    }

    // =========================================================================
    // 6. Mobile QR Code Modal
    // =========================================================================
    elements.btnMobileQr.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/network-info');
            const data = await res.json();
            if (data.qr_code) {
                elements.qrImage.src = data.qr_code;
                elements.mobileUrlText.textContent = data.url;
                elements.qrModal.style.display = 'flex';
            }
        } catch (err) {
            console.error("Failed to load network info:", err);
        }
    });

    elements.btnCloseQrModal.addEventListener('click', () => {
        elements.qrModal.style.display = 'none';
    });

    elements.qrModal.addEventListener('click', (e) => {
        if (e.target === elements.qrModal) {
            elements.qrModal.style.display = 'none';
        }
    });

    elements.btnCopyMobileUrl.addEventListener('click', () => {
        navigator.clipboard.writeText(elements.mobileUrlText.textContent);
        elements.btnCopyMobileUrl.innerHTML = '<i data-lucide="check"></i> Copied!';
        if (window.lucide) lucide.createIcons();
        setTimeout(() => {
            elements.btnCopyMobileUrl.innerHTML = '<i data-lucide="copy"></i> Copy';
            if (window.lucide) lucide.createIcons();
        }, 2000);
    });

    // =========================================================================
    // 7. Table Controls & Filters
    // =========================================================================
    elements.tableSearchInput.addEventListener('input', (e) => {
        state.searchTerm = e.target.value;
        renderTable();
    });

    elements.tabBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            elements.tabBtns.forEach(b => b.classList.remove('active'));
            e.currentTarget.classList.add('active');
            state.currentFilter = e.currentTarget.dataset.filter;
            renderTable();
        });
    });

    elements.btnRefreshDb.addEventListener('click', () => loadRecords(true));

    // Audio helper
    function playSound(audioEl) {
        if (audioEl) {
            audioEl.currentTime = 0;
            audioEl.play().catch(() => {});
        }
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // Initial Load
    loadRecords();
});
