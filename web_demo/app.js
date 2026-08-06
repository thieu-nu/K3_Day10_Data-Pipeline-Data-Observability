// Interactive logic for Day 10 Lab Demo
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initPipelineVisualizer();
  initChatSimulator();
  initGateInspector();
  startConsoleAnimation();
});

// Tab Navigation
function initTabs() {
  const buttons = document.querySelectorAll('.nav-btn');
  const contents = document.querySelectorAll('.tab-content');

  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      const tabId = btn.getAttribute('data-tab');
      
      buttons.forEach(b => b.classList.remove('active'));
      contents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      document.getElementById(tabId).classList.add('active');
    });
  });
}

// Pipeline Steps Visualizer
const pipelineData = {
  step1: {
    title: "1. Raw Ingestion & Lineage",
    owner: "Vai trò 2: Đàm Minh Tuấn (2A202601169)",
    desc: "Kết nối Crossref REST API với Exponential Backoff & Retry. Thu lúa 24 bài báo khoa học chuẩn hóa về đối tượng PaperRecord. Bản gốc không bị can thiệp được phong tỏa lưu trú trong data/raw/ để truy vết Lineage và phục hồi sau này.",
    artifacts: "data/raw/crossref_response.json | data/raw/crossref_records.json",
    status: "PASSED (24/24 records fetched)"
  },
  step2: {
    title: "2. Data Cleaning & Sanitization",
    owner: "Vai trò 3: Đinh Huy Mạnh (2A202601677)",
    desc: "Khử trùng lặp theo paper_id, gọt bỏ thẻ HTML thô trong tóm tắt, chuẩn hóa ISO date và sa lôi các bài báo khuyết tóm tắt dưới 100 chữ. Tính toán chỉ số tuổi đời age_days.",
    artifacts: "data/clean/papers_clean.csv | data/clean/papers_clean.json",
    status: "PASSED (Clean Contract validated)"
  },
  step3: {
    title: "3. Clean Contract Gate C1",
    owner: "Vai trò 1: Trần Hoàng Quân (2A202601805)",
    desc: "Trạm kiểm soát Fail-closed Gate C1 rà soát SHA-256 Checksum, đối chiếu count giữa mốc thô và mốc sạch, và tính nhất quán CSV vs JSON. Chỉ khi bật tín hiệu GO, hạ nguồn mới được phép chạy.",
    artifacts: "data/quality/clean_contract_gate.json",
    status: "GATE OPEN — GO TO INDEX"
  },
  step4: {
    title: "4. Vector Indexing (RAG)",
    owner: "Vai trò 4: Lê Minh Khiêm (2A202601645)",
    desc: "Biến đổi đoạn kết hợp 'Title: {title} | Summary: {summary}' thành các ma trận vector toán học thông qua mô hình MiniLM-L6-v2 và cất trữ an toàn vào cơ sở dữ liệu vector ChromaDB.",
    artifacts: "data/embeddings/papers_embeddings.json | data/chroma/",
    status: "INDEX READY (Chroma collection 'papers-baseline')"
  },
  step5: {
    title: "5. Observability & Eval Reports",
    owner: "Vai trò 5: Nguyễn Quang Hưng (2A202601523)",
    desc: "Thi hành cảm biến đo lường Data Quality (duplicate/empty check) và Freshness (age_days < 180). Chạy tập 20 đề thi bất biến test_set.json chấm điểm Retrieval Hit Rate và Judge Accuracy.",
    artifacts: "data/reports/corruption_report.md | data/results/baseline_metrics.json",
    status: "PASSED (100% Hit Rate | Quality OK)"
  }
};

function initPipelineVisualizer() {
  const steps = document.querySelectorAll('.pipeline-step');
  const panelTitle = document.getElementById('step-detail-title');
  const panelOwner = document.getElementById('step-detail-owner');
  const panelDesc = document.getElementById('step-detail-desc');
  const panelArtifacts = document.getElementById('step-detail-artifacts');
  const panelStatus = document.getElementById('step-detail-status');

  steps.forEach(step => {
    step.addEventListener('click', () => {
      steps.forEach(s => s.classList.remove('active'));
      step.classList.add('active');

      const data = pipelineData[step.getAttribute('data-step')];
      panelTitle.textContent = data.title;
      panelOwner.textContent = data.owner;
      panelDesc.textContent = data.desc;
      panelArtifacts.textContent = data.artifacts;
      panelStatus.textContent = data.status;
    });
  });
}

// Interactive RAG Chat Simulator
const ragResponses = {
  baseline: {
    dbName: "Baseline Vector Index (Clean Data)",
    hitRate: "100.0%",
    statusClass: "badge-pass",
    statusText: "HEALTHY",
    responses: {
      "q1": {
        text: "Hệ thống tự chẩn đoán và tự làm lành RAG (Self-healing RAG) giúp tự động tái đồng bộ bộ index cơ sở dữ liệu mỗi khi có tín hiệu cảnh báo thiu thối hay biến thiên lỗi phân phối trên đường ống nạp vào.",
        doc: "10.1000/mock1 — Reliability of AI Pipelines (Published: 2026-07-01)",
        f1: "0.89",
        judge: "PASS (Accuracy 100%)"
      },
      "q2": {
        text: "Theo dữ liệu ghi nhận từ Crossref API, bài báo 'Reliability of AI Pipelines' do tác giả John Doe công bố với phân loại chính là Software Engineering.",
        doc: "10.1000/mock1 — Authors: [John Doe] | Categories: [Software Engineering]",
        f1: "0.95",
        judge: "PASS (Accuracy 100%)"
      },
      "q3": {
        text: "Hợp đồng dữ liệu Clean-v1 (Clean Contract Gate) khóa chặn toàn bộ tiến trình index nhúng vector xuống ChromaDB nếu phát hiện chữ ký SHA-256 sai lệch hoặc có bất kỳ tóm tắt nào ngắn dưới 100 ký tự.",
        doc: "10.1000/contract_audit — Clean Contract Specification",
        f1: "0.92",
        judge: "PASS (Accuracy 100%)"
      }
    }
  },
  corrupted: {
    dbName: "Corrupted Vector Index (Phase 2 Data Drop & Noise)",
    hitRate: "60.0%",
    statusClass: "badge-fail",
    statusText: "CORRUPTED (DATA LOSS)",
    responses: {
      "q1": {
        text: "[Hallucinated Response]: RAG là hệ thống tạo văn bản ngẫu nhiên không sử dụng cơ sở dữ liệu thực. [CORRUPTED NOISE %%% ERR_NIL_SUMMARY].",
        doc: "WARNING: No vector matches found! Summary field was blanked/corrupted.",
        f1: "0.05",
        judge: "FAIL (Hallucination Detected)"
      },
      "q2": {
        text: "Tác giả bài báo là không xác định. Dữ liệu đã bị xé gãy tiêu đề và quá hạn năm 2020.",
        doc: "10.1000/mock1 (Truncated title / Stale Timestamp > 2300 days)",
        f1: "0.12",
        judge: "FAIL (Incorrect Author/Stale Data)"
      },
      "q3": {
        text: "[CORRUPTED NOISE %%%] Không tìm thấy hợp đồng dữ liệu nào trong bảng Vector Index bị lỗi.",
        doc: "ERROR_VECTOR_OUTLIER_NOT_FOUND",
        f1: "0.00",
        judge: "FAIL (Zero Context Hit)"
      }
    }
  },
  repaired: {
    dbName: "Repaired Vector Index (Source Re-ingested from Raw)",
    hitRate: "100.0%",
    statusClass: "badge-pass",
    statusText: "REPAIRED (100% RECOVERY)",
    responses: {
      "q1": {
        text: "Hệ thống tự chẩn đoán và tự làm lành RAG (Self-healing RAG) giúp tự động tái đồng bộ bộ index cơ sở dữ liệu mỗi khi có tín hiệu cảnh báo thiu thối hay biến thiên lỗi phân phối trên đường ống nạp vào.",
        doc: "10.1000/mock1 — Restored from immutable Raw Lineage (data/raw/crossref_records.json)",
        f1: "0.89",
        judge: "PASS (Accuracy 100%)"
      },
      "q2": {
        text: "Theo dữ liệu khôi phục hoàn hảo từ Raw Lineage, bài báo do tác giả John Doe công bố thuộc chuyên ngành Software Engineering.",
        doc: "10.1000/mock1 — Authors: [John Doe] (Restored)",
        f1: "0.95",
        judge: "PASS (Accuracy 100%)"
      },
      "q3": {
        text: "Hợp đồng dữ liệu Clean-v1 khóa chặn toàn bộ tiến trình index xuống ChromaDB nếu phát hiện chữ ký SHA-256 sai lệch. Sau khi Re-ingest từ raw, chữ ký SHA-256 đã hợp lệ trở lại!",
        doc: "10.1000/contract_audit — Clean Contract Restored",
        f1: "0.94",
        judge: "PASS (Accuracy 100%)"
      }
    }
  }
};

let currentDb = 'baseline';

function initChatSimulator() {
  const dbOptions = document.querySelectorAll('.db-option');
  const chatMessages = document.getElementById('chat-messages');
  const questionSelect = document.getElementById('question-select');
  const customInput = document.getElementById('custom-question');
  const btnSend = document.getElementById('btn-send');
  const dbStatusPill = document.getElementById('db-status-pill');

  dbOptions.forEach(opt => {
    opt.addEventListener('click', () => {
      dbOptions.forEach(o => o.classList.remove('active'));
      opt.classList.add('active');
      currentDb = opt.getAttribute('data-db');
      
      const dbInfo = ragResponses[currentDb];
      dbStatusPill.className = `badge ${dbInfo.statusClass}`;
      dbStatusPill.textContent = `${dbInfo.statusText} | Hit Rate: ${dbInfo.hitRate}`;

      // Add System Notice in Chat
      appendMessage('bot', `🔄 Chuyển sang kết nối: **${dbInfo.dbName}**. Hệ thống Vector Store sẵn sàng!`, null);
    });
  });

  btnSend.addEventListener('click', async () => {
    let qId = questionSelect.value;
    let queryText = customInput.value.trim();
    let isCustom = (queryText !== "");

    if (!isCustom && qId === "") {
      alert("Vui lòng chọn một đề thi mẫu hoặc gõ câu hỏi!");
      return;
    }

    let displayQ = isCustom ? queryText : questionSelect.options[questionSelect.selectedIndex].text;
    appendMessage('user', displayQ, null);
    if (isCustom) customInput.value = "";

    // Add loading indicator
    const chatMessages = document.getElementById('chat-messages');
    const loadDiv = document.createElement('div');
    loadDiv.className = "message bot";
    loadDiv.id = "loading-msg";
    loadDiv.innerHTML = "<div>⏳ Đang truy vết Vector Store & gọi LLM Judge chấm điểm...</div>";
    chatMessages.appendChild(loadDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
      // 1. Try hitting real Python Backend API (/api/query)
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          db: currentDb,
          question: isCustom ? queryText : displayQ,
          ground_truth: ""
        })
      });

      const data = await res.json();
      const loader = document.getElementById('loading-msg');
      if (loader) loader.remove();

      if (data.status === 'success') {
        appendMessage('bot', data.answer, { doc: data.doc_hit, f1: data.f1_score, judge: data.llm_judge });
        return;
      }
      throw new Error("Backend return error, falling back to client simulation");
    } catch (err) {
      // 2. Offline / Local file Fallback simulation
      const loader = document.getElementById('loading-msg');
      if (loader) loader.remove();

      setTimeout(() => {
        let targetId = isCustom ? "q1" : qId;
        const resp = ragResponses[currentDb].responses[targetId];
        appendMessage('bot', resp.text, { doc: resp.doc, f1: resp.f1, judge: resp.judge });
      }, 400);
    }
  });
}

function appendMessage(sender, text, meta) {
  const chatMessages = document.getElementById('chat-messages');
  const msgDiv = document.createElement('div');
  msgDiv.className = `message ${sender}`;
  
  let content = `<div>${text}</div>`;
  if (meta) {
    content += `
      <div class="bot-meta">
        <span>📄 <strong>Retrieval Hit:</strong> ${meta.doc}</span>
        <span>⚡ <strong>F1 Score:</strong> ${meta.f1}</span>
        <span>🛡️ <strong>LLM Judge:</strong> ${meta.judge}</span>
      </div>
    `;
  }
  msgDiv.innerHTML = content;
  chatMessages.appendChild(msgDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Gate Inspector Simulation
function initGateInspector() {
  const btnTest = document.getElementById('btn-test-gate');
  if (!btnTest) return;

  btnTest.addEventListener('click', () => {
    const sampleType = document.getElementById('gate-sample').value;
    const resultBox = document.getElementById('gate-result-box');
    
    if (sampleType === 'valid') {
      resultBox.className = 'card style-pass';
      resultBox.innerHTML = `
        <h3 style="color: var(--status-pass);">🟢 GATE STATUS: GO / APPROVED</h3>
        <p><strong>SHA-256 Checksum:</strong> f4e81a9c3d2... (MATCHED)</p>
        <p><strong>Count Reconciliation:</strong> Raw (24) == Clean (24) (MATCHED)</p>
        <p><strong>Schema Quality:</strong> All summaries &gt; 100 chars, no duplicates, ISO dates valid.</p>
        <div class="badge badge-pass" style="margin-top: 1rem; display: inline-block;">Downstream RAG Indexing Allowed</div>
      `;
    } else if (sampleType === 'short') {
      resultBox.className = 'card style-fail';
      resultBox.innerHTML = `
        <h3 style="color: var(--status-fail);">🔴 GATE STATUS: STOP / CLOSED (C1-BLOCKER)</h3>
        <p><strong>Violation Detected:</strong> filtered_short_summary &gt; 0</p>
        <p><strong>Reason:</strong> Found 3 papers with summary length &lt; 100 chars ("This study focuses on RAG.").</p>
        <p><strong>Action:</strong> Pipeline frozen. Downstream embeddings execution aborted to prevent database pollution.</p>
        <div class="badge badge-fail" style="margin-top: 1rem; display: inline-block;">Fail-Closed Gate Activated</div>
      `;
    } else {
      resultBox.className = 'card style-fail';
      resultBox.innerHTML = `
        <h3 style="color: var(--status-fail);">🔴 GATE STATUS: STOP / CLOSED (STALE DATA WARNING)</h3>
        <p><strong>Violation Detected:</strong> freshness_threshold_exceeded == True</p>
        <p><strong>Reason:</strong> Timestamp modified to 2020-01-01 (Age: 2320 days &gt; 180 max threshold).</p>
        <p><strong>Action:</strong> Alert sent to Observability Dashboard. Data rejected!</p>
        <div class="badge badge-fail" style="margin-top: 1rem; display: inline-block;">Stale Data Alert</div>
      `;
    }
  });
}

// Console Logs Animation
function startConsoleAnimation() {
  const consoleBox = document.getElementById('console-log');
  if (!consoleBox) return;

  const logs = [
    '<span class="info">[06:30:12] [*] Starting Phase 2 Corruption & Repair Flow...</span>',
    '<span class="info">[06:30:12] [i] Step 1: Loading baseline clean dataset and metrics... [OK]</span>',
    '<span class="warn">[06:30:13] [!] Step 2: Generating corrupted dataset (Dropping latest 2 records & Blanking summaries)...</span>',
    '<span class="info">[06:30:14] [i] Step 3: Saving corrupted artifacts into data/clean/corrupted...</span>',
    '<span class="warn">[06:30:15] [!] Step 4: Building corrupted vector index & evaluating... Retrieval Hit Rate collapsed to 60.0%!</span>',
    '<span class="err">[06:30:16] [✗] Step 5: Data Quality Gate FAILED (Found blank summaries & duplicate keys). Freshness FAILED!</span>',
    '<span class="info">[06:30:17] [🔄] Step 6: Initiating Source Re-ingestion / Repair from immutable raw_records.json...</span>',
    '<span class="info">[06:30:18] [✓] Step 7: Building repaired vector index & re-evaluating... Retrieval Hit Rate recovered to 100.0%!</span>',
    '<span class="info">[06:30:19] [🎉] Step 8: Generating Phase 2 Comparison Report -> data/reports/corruption_report.md</span>',
    '<span class="info" style="color: #FFF; font-weight: bold;">[✓] PIPELINE COMPLETED SUCCESSFULLY: 100% RECOVERY ACHIEVED!</span>'
  ];

  let i = 0;
  const timer = setInterval(() => {
    if (i < logs.length) {
      consoleBox.innerHTML += logs[i] + '<br>';
      consoleBox.scrollTop = consoleBox.scrollHeight;
      i++;
    } else {
      clearInterval(timer);
    }
  }, 900);
}
