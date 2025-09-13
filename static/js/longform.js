(() => {
  const projectSelect = document.getElementById('projectSelect');
  const createBtn = document.getElementById('createProjectBtn');
  const deleteBtn = document.getElementById('deleteProjectBtn');
  const tableBody = document.querySelector('#longformTable tbody');
  const compileBtn = document.getElementById('compileBtn');
  const generateBtn = document.getElementById('generateRemainingBtn');
  const projectStatus = document.getElementById('projectStatus');
  const intervalModalEl = document.getElementById('intervalModal');
  const intervalMinutesEl = document.getElementById('intervalMinutes');
  const confirmSendBtn = document.getElementById('confirmSendRemaining');
  let intervalModal;
  let jobActive = false;
  let jobEndsAt = null;
  let jobTimerId = null;

  let projects = [];
  let currentProjectId = '';

  function setStatus(msg, type = 'muted') {
    if (!projectStatus) return;
    const cls = type === 'error' ? 'text-danger' : type === 'success' ? 'text-success' : 'text-muted';
    projectStatus.className = `card-footer ${cls}`;
    projectStatus.textContent = msg || '';
  }

  function api(path, opts = {}) {
    return fetch(path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts))
      .then(r => r.json());
  }

  function renderProjectSelect() {
    projectSelect.innerHTML = '';
    projects.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name;
      projectSelect.appendChild(opt);
    });
    if (projects.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'No projects yet';
      projectSelect.appendChild(opt);
      deleteBtn.disabled = true;
      compileBtn.disabled = true;
      generateBtn.disabled = true;
      tableBody.innerHTML = '';
    } else {
      if (!currentProjectId || !projects.find(p => p.id === currentProjectId)) {
        currentProjectId = projects[0].id;
      }
      projectSelect.value = currentProjectId;
      deleteBtn.disabled = false;
      // Initially disable buttons until rows are loaded and status is computed
      compileBtn.disabled = true;
      generateBtn.disabled = true;
      loadRows(currentProjectId);
    }
  }

  function setButtonsDisabled(disabled) {
    generateBtn.disabled = disabled || generateBtn.disabled;
    // For compile button, we need to respect both the disabled state AND the complete status requirement
    if (disabled) {
      compileBtn.disabled = true;
    } else {
      // Recompute status to check if all rows are complete
      recomputeStatuses();
    }
  }

  function updateJobCountdownUI() {
    const el = document.getElementById('projectStatus');
    if (!jobActive || !jobEndsAt) {
      if (el) el.textContent = '';
      return;
    }
    try {
      const end = new Date(jobEndsAt).getTime();
      const now = Date.now();
      const remainingMs = Math.max(0, end - now);
      const mins = Math.floor(remainingMs / 60000);
      const secs = Math.floor((remainingMs % 60000) / 1000);
      el.textContent = `Job in progress… ~${mins}m ${secs}s remaining`;
      if (remainingMs === 0) {
        jobActive = false;
        jobEndsAt = null;
        clearInterval(jobTimerId);
        jobTimerId = null;
        setButtonsDisabled(false);
        recomputeStatuses();
      }
    } catch {}
  }

  function pollJobStatusOnce() {
    return fetch('/api/longform/job-status').then(r => r.json()).then(res => {
      if (res.success) {
        jobActive = !!res.active;
        jobEndsAt = res.ends_at || null;
        if (jobActive) {
          setButtonsDisabled(true);
          if (!jobTimerId) jobTimerId = setInterval(updateJobCountdownUI, 1000);
          updateJobCountdownUI();
        } else {
          setButtonsDisabled(false);
          if (jobTimerId) { clearInterval(jobTimerId); jobTimerId = null; }
          updateJobCountdownUI();
        }
      }
    }).catch(() => {});
  }

  function createRowElement(row) {
    const tr = document.createElement('tr');

    const tdSerial = document.createElement('td');
    tdSerial.textContent = row.serial_number;
    tr.appendChild(tdSerial);

    const tdAudio = document.createElement('td');
    const audioInput = document.createElement('input');
    audioInput.type = 'url';
    audioInput.className = 'form-control form-control-sm';
    audioInput.placeholder = 'https://...';
    audioInput.value = row.audio_url || '';
    audioInput.addEventListener('change', onAnyCellChange);
    tdAudio.appendChild(audioInput);
    tr.appendChild(tdAudio);

    const tdImage = document.createElement('td');
    const imageInput = document.createElement('input');
    imageInput.type = 'url';
    imageInput.className = 'form-control form-control-sm';
    imageInput.placeholder = 'https://...';
    imageInput.value = row.image_url || '';
    imageInput.addEventListener('change', onAnyCellChange);
    tdImage.appendChild(imageInput);
    tr.appendChild(tdImage);

    const tdStatus = document.createElement('td');
    const statusBadge = document.createElement('span');
    const statusVal = (row.status || 'incomplete').toLowerCase() === 'complete' ? 'complete' : 'incomplete';
    statusBadge.className = `badge ${statusVal === 'complete' ? 'bg-success' : 'bg-secondary'}`;
    statusBadge.textContent = statusVal;
    tdStatus.appendChild(statusBadge);
    tr.appendChild(tdStatus);

    return tr;
  }

  function isValidUrl(u) {
    if (!u) return false;
    try {
      const parsed = new URL(u);
      return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch { return false; }
  }

  function isRowComplete(tr) {
    const audio = tr.querySelector('td:nth-child(2) input');
    const imgInput = tr.querySelector('td:nth-child(3) input');
    if (!isValidUrl(audio.value.trim())) return false;
    return isValidUrl(imgInput.value.trim());
  }

  function recomputeStatuses() {
    // Preserve displayed status; only update button enablement
    const rows = tableBody.querySelectorAll('tr');
    let completeCount = 0;
    let hasIncomplete = false;
    rows.forEach(tr => {
      const badge = tr.querySelector('td:nth-child(4) .badge');
      const status = badge ? badge.textContent.trim().toLowerCase() : 'incomplete';
      if (status === 'complete') completeCount += 1;
      if (status === 'incomplete') hasIncomplete = true;
    });
    // Compile button is only enabled when ALL rows have "complete" status
    compileBtn.disabled = !(rows.length === 14 && completeCount === 14);
    // Generate button is enabled when there are incomplete rows
    generateBtn.disabled = !hasIncomplete;
  }

  function serializeRows() {
    const out = [];
    const rows = tableBody.querySelectorAll('tr');
    rows.forEach((tr, idx) => {
      const audio = tr.querySelector('td:nth-child(2) input').value.trim();
      const image = tr.querySelector('td:nth-child(3) input').value.trim();
      const statusBadge = tr.querySelector('td:nth-child(4) .badge');
      const status = statusBadge ? statusBadge.textContent.trim().toLowerCase() : 'incomplete';
      out.push({
        serial_number: idx + 1,
        audio_url: audio,
        image_url: image,
        status: status === 'complete' ? 'complete' : 'incomplete'
      });
    });
    return out;
  }

  function onAnyCellChange() {
    recomputeStatuses();
    debounceSave();
  }

  let saveTimer = null;
  function debounceSave() {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(saveRows, 400);
  }

  function saveRows() {
    if (!currentProjectId) return;
    const payload = { rows: serializeRows() };
    api(`/api/longform/projects/${currentProjectId}/rows`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }).then(res => {
      if (!res.success) setStatus(res.error || 'Failed to save rows', 'error');
      else setStatus('Saved', 'success');
    }).catch(() => setStatus('Failed to save rows', 'error'));
  }

  function loadRows(projectId) {
    tableBody.innerHTML = '';
    setStatus('Loading...');
    api(`/api/longform/projects/${projectId}/rows`).then(res => {
      if (!res.success) {
        setStatus(res.error || 'Failed to load rows', 'error');
        return;
      }
      const rows = res.rows || [];
      // Ensure exactly 14 rows
      for (let i = 0; i < 14; i++) {
        const row = rows[i] || { serial_number: i + 1, audio_url: '', image_url: '', status: 'incomplete' };
        const tr = createRowElement(row);
        tableBody.appendChild(tr);
      }
      recomputeStatuses();
      setStatus('');
    }).catch(() => setStatus('Failed to load rows', 'error'));
  }

  function loadProjects() {
    api('/api/longform/projects').then(res => {
      if (!res.success) {
        showToast(res.error || 'Failed to load projects', 'error');
        return;
      }
      projects = res.projects || [];
      renderProjectSelect();
    }).catch(() => showToast('Failed to load projects', 'error'));
  }

  // Modal instances
  let createProjectModal, deleteProjectModal;

  // Initialize modals
  function initModals() {
    createProjectModal = new bootstrap.Modal(document.getElementById('createProjectModal'));
    deleteProjectModal = new bootstrap.Modal(document.getElementById('deleteProjectModal'));
  }

  // Handlers
  createBtn.addEventListener('click', () => {
    document.getElementById('projectNameInput').value = '';
    document.getElementById('createProjectStatus').innerHTML = '';
    createProjectModal.show();
  });

  deleteBtn.addEventListener('click', () => {
    if (!currentProjectId) return;
    const project = projects.find(p => p.id === currentProjectId);
    document.getElementById('deleteProjectName').textContent = project ? project.name : 'Unknown';
    document.getElementById('deleteProjectStatus').innerHTML = '';
    deleteProjectModal.show();
  });

  // Create project confirmation
  document.getElementById('confirmCreateProject').addEventListener('click', () => {
    const name = document.getElementById('projectNameInput').value.trim();
    if (!name) {
      document.getElementById('createProjectStatus').innerHTML = '<div class="alert alert-danger">Please enter a project name.</div>';
      return;
    }
    
    document.getElementById('createProjectStatus').innerHTML = '<div class="alert alert-info"><i class="fas fa-spinner fa-spin me-2"></i>Creating project...</div>';
    
    api('/api/longform/projects', { method: 'POST', body: JSON.stringify({ name }) })
      .then(res => {
        if (res.success) {
          projects.push(res.project);
          currentProjectId = res.project.id;
          renderProjectSelect();
          createProjectModal.hide();
          showToast('Project created successfully', 'success');
        } else {
          document.getElementById('createProjectStatus').innerHTML = `<div class="alert alert-danger">${res.error || 'Failed to create project'}</div>`;
        }
      }).catch(() => {
        document.getElementById('createProjectStatus').innerHTML = '<div class="alert alert-danger">Failed to create project</div>';
      });
  });

  // Delete project confirmation
  document.getElementById('confirmDeleteProject').addEventListener('click', () => {
    document.getElementById('deleteProjectStatus').innerHTML = '<div class="alert alert-info"><i class="fas fa-spinner fa-spin me-2"></i>Deleting project...</div>';
    
    api(`/api/longform/projects/${currentProjectId}`, { method: 'DELETE' })
      .then(res => {
        if (res.success) {
          projects = projects.filter(p => p.id !== currentProjectId);
          currentProjectId = projects[0]?.id || '';
          renderProjectSelect();
          deleteProjectModal.hide();
          showToast('Project deleted successfully', 'success');
        } else {
          document.getElementById('deleteProjectStatus').innerHTML = `<div class="alert alert-danger">${res.error || 'Failed to delete project'}</div>`;
        }
      }).catch(() => {
        document.getElementById('deleteProjectStatus').innerHTML = '<div class="alert alert-danger">Failed to delete project</div>';
      });
  });

  projectSelect.addEventListener('change', () => {
    currentProjectId = projectSelect.value;
    if (currentProjectId) loadRows(currentProjectId);
  });


  generateBtn.addEventListener('click', () => {
    if (jobActive) { showToast('A job is already in progress.', 'info'); return; }
    if (!intervalModal) intervalModal = new bootstrap.Modal(intervalModalEl);
    intervalMinutesEl.value = '1';
    document.getElementById('intervalStatus').innerHTML = '';
    intervalModal.show();
  });

  function getProjectNameById(id) {
    const p = projects.find(x => x.id === id);
    return p ? p.name : '';
  }

  function getRemainingRows() {
    const rows = [];
    const trs = tableBody.querySelectorAll('tr');
    trs.forEach((tr, idx) => {
      const badge = tr.querySelector('td:nth-child(4) .badge');
      const status = badge ? badge.textContent.trim().toLowerCase() : 'incomplete';
      if (status === 'incomplete') {
        const audio = tr.querySelector('td:nth-child(2) input').value.trim();
        const image = tr.querySelector('td:nth-child(3) input').value.trim();
        // Only include rows where fields are present (non-empty); backend validates formats
        if (audio && image) {
          rows.push({
            serial_number: idx + 1,
            audio_url: audio,
            image_url: image
          });
        }
      }
    });
    return rows;
  }

  function updateRowStatusToComplete(serialNumber) {
    const tr = tableBody.querySelectorAll('tr')[serialNumber - 1];
    if (!tr) return;
    const badge = tr.querySelector('td:nth-child(4) .badge');
    badge.className = 'badge bg-success';
    badge.textContent = 'complete';
    // Recompute button states after updating status
    recomputeStatuses();
  }

  function postLongformPayload(payload) {
    // Call backend to handle Discord extraction and n8n dispatch
    return fetch('/api/longform/dispatch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(resp => resp.json()).then(res => {
      if (!res.success) throw new Error(res.error || 'Dispatch failed');
      return res;
    });
  }

  confirmSendBtn.addEventListener('click', () => {
    const minutes = Math.max(0, parseInt(intervalMinutesEl.value || '0', 10));
    const remaining = getRemainingRows();
    if (remaining.length === 0) {
      document.getElementById('intervalStatus').innerHTML = '<div class="alert alert-info">No valid remaining rows available.</div>';
      return;
    }
    const projectName = getProjectNameById(currentProjectId);
    intervalModal.hide();
    showToast(`Sending ${remaining.length} rows at ${minutes} min interval`, 'info');
    // Calculate job window: total send time + 12 minutes buffer
    const totalSeconds = (remaining.length > 0 ? (minutes * 60 * (remaining.length - 1)) : 0) + (12 * 60);
    fetch('/api/longform/start-job', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ seconds: totalSeconds, reason: 'generate_remaining' }) })
      .then(r => r.json()).then(res => {
        if (!res.success) { showToast(res.error || 'Failed to start job lock', 'error'); return; }
        jobActive = true; jobEndsAt = res.ends_at; setButtonsDisabled(true);
        if (!jobTimerId) jobTimerId = setInterval(updateJobCountdownUI, 1000); updateJobCountdownUI();
      }).catch(() => {});

    let i = 0;
    const sendNext = () => {
      if (i >= remaining.length) {
        recomputeStatuses();
        saveRows();
        showToast('All remaining rows dispatched', 'success');
        return;
      }
      const row = remaining[i];
      const payload = {
        project_name: projectName,
        serial_number: row.serial_number,
        audio_url: row.audio_url,
        image_url: row.image_url // Discord message link with 5 attachments (order 5..1)
      };
      postLongformPayload(payload)
        .then(() => {
          updateRowStatusToComplete(row.serial_number);
          saveRows();
        })
        .catch((e) => {
          showToast(`Row ${row.serial_number} failed: ${e.message}`, 'error');
        })
        .finally(() => {
          i += 1;
          if (minutes === 0) {
            sendNext();
          } else {
            setTimeout(sendNext, minutes * 60 * 1000);
          }
        });
    };
    sendNext();
  });

  // Compile button: send project name to compile webhook
  compileBtn.addEventListener('click', () => {
    if (jobActive) { showToast('A job is already in progress.', 'info'); return; }
    const projectName = getProjectNameById(currentProjectId);
    if (!projectName) { showToast('No project selected', 'error'); return; }
    
    // Check if all rows are complete
    const rows = tableBody.querySelectorAll('tr');
    let completeCount = 0;
    rows.forEach(tr => {
      const badge = tr.querySelector('td:nth-child(4) .badge');
      const status = badge ? badge.textContent.trim().toLowerCase() : 'incomplete';
      if (status === 'complete') completeCount += 1;
    });
    
    if (completeCount !== 14) {
      showToast(`Cannot compile: ${14 - completeCount} rows are still incomplete. All rows must be complete before compiling.`, 'error');
      return;
    }
    
    const seconds = 12 * 60; // 12 minute lock
    fetch('/api/longform/start-job', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ seconds, reason: 'compile' }) })
      .then(r => r.json()).then(res => {
        if (!res.success) { showToast(res.error || 'Failed to start job', 'error'); return; }
        jobActive = true; jobEndsAt = res.ends_at; setButtonsDisabled(true);
        if (!jobTimerId) jobTimerId = setInterval(updateJobCountdownUI, 1000); updateJobCountdownUI();
        
        // Send compile request
        fetch('/api/longform/compile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_name: projectName }) })
          .then(r => r.json()).then(compileRes => {
            if (compileRes.success) {
              showToast('Compile job sent successfully', 'success');
            } else {
              showToast(`Compile failed: ${compileRes.error || 'Unknown error'}`, 'error');
            }
          }).catch(() => showToast('Compile request failed', 'error'));
      }).catch(() => showToast('Failed to start compile job', 'error'));
  });

  // init
  initModals();
  loadProjects();
  pollJobStatusOnce();
})();


