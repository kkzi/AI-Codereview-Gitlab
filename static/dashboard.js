let currentType = 'push';  // 默认选中代码推送
        let currentPage = 1;
        let pageSize = 50;
        let lastPagination = null;
        let sortField = 'updated_at';
        let sortOrder = 'desc';
        let currentDetailId = null;
        let lastLlmCheckAt = 0;
        let jobStatusTimer = null;
        let jobStatusPollToken = 0;
        let lastWorkerStats = null;
        let lastWorkerStatsAt = 0;

	        function initDates() {
	            const today = new Date();
	            const weekAgo = new Date(today);
	            weekAgo.setDate(today.getDate() - 7);

	            const endInput = document.getElementById('endDate');
	            const startInput = document.getElementById('startDate');
	            if (endInput) endInput.value = today.toISOString().split('T')[0];
	            if (startInput) startInput.value = weekAgo.toISOString().split('T')[0];

	            if (window.flatpickr) {
	                window.flatpickr('#startDate', {
	                    dateFormat: 'Y-m-d',
	                    allowInput: true,
	                    defaultDate: weekAgo,
	                });
	                window.flatpickr('#endDate', {
	                    dateFormat: 'Y-m-d',
	                    allowInput: true,
	                    defaultDate: today,
	                });
	            }
	        }

	        function switchTab(type) {
	            currentType = type;
	            document.querySelectorAll('.tab').forEach(tab => {
	                tab.classList.toggle('active', tab.dataset.type === type);
	            });
	            currentPage = 1;
	            loadData();
	        }

	        function setSort(field) {
	            if (sortField === field) {
	                sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
	            } else {
	                sortField = field;
	                sortOrder = field === 'updated_at' ? 'desc' : 'asc';
	            }
	            currentPage = 1;
	            refreshSortIndicators();
	            loadData();
	        }

	        function refreshSortIndicators() {
	            const scoreEl = document.getElementById('sortScore');
	            const updatedEl = document.getElementById('sortUpdated');
	            if (scoreEl) scoreEl.textContent = '↕';
	            if (updatedEl) updatedEl.textContent = '↕';

	            const symbol = sortOrder === 'asc' ? '↑' : '↓';
	            if (sortField === 'score' && scoreEl) scoreEl.textContent = symbol;
	            if (sortField === 'updated_at' && updatedEl) updatedEl.textContent = symbol;
	        }

	        function openDetail(recordId) {
	            currentDetailId = recordId;
	            stopJobStatusPolling();
	            const modal = document.getElementById('detailModal');
	            const title = document.getElementById('detailTitle');
	            const meta = document.getElementById('detailMeta');
	            const links = document.getElementById('detailLinks');
	            const body = document.getElementById('detailBody');
	            const retryBtn = document.getElementById('retryBtn');

	            if (!modal || !title || !meta || !body) return;
	            modal.classList.add('open');
	            modal.setAttribute('aria-hidden', 'false');
	            body.textContent = '加载中...';
	            meta.textContent = '';
	            if (links) links.innerHTML = '';
	            title.textContent = `审查详情 #${recordId}`;
	            if (retryBtn) retryBtn.disabled = false;

	            setJobStatusLoading();
	            loadDetail(recordId);
	            loadJobStatus(recordId, { poll: true, refreshOnDone: true });
	        }

	        function closeDetail() {
	            const modal = document.getElementById('detailModal');
	            if (!modal) return;
	            modal.classList.remove('open');
	            modal.setAttribute('aria-hidden', 'true');
	            currentDetailId = null;
	            stopJobStatusPolling();
	            clearJobStatus();
	        }

	        async function loadDetail(recordId) {
	            try {
	                const res = await fetch(`/dashboard/api/reviews/${recordId}?type=${encodeURIComponent(currentType)}`);
	                const result = await res.json();
	                if (result.error) throw new Error(result.error);

	                const data = result.data || {};
	                const meta = document.getElementById('detailMeta');
	                const links = document.getElementById('detailLinks');
	                const body = document.getElementById('detailBody');

	                const project = data.project_name || '';
	                const author = (data.author_display_name || '').trim() || data.author || '';
	                const updated = data.updated_at || '';
	                const modelName = data.model_name || '';
	                const score = data.score != null ? data.score : '';
	                const status = data.status || '';
	                const retryCount = data.retry_count != null ? data.retry_count : '';
	                const projectUrl = data.project_url || '';
	                const commitUrl = data.commit_url || '';
	                const commitId = (data.last_commit_id || '').trim();
	                const mrUrl = data.url || '';

                if (meta) {
                    meta.textContent = '';
                    meta.appendChild(document.createTextNode('项目: '));
                    if (projectUrl) {
                        const link = document.createElement('a');
                        link.href = projectUrl;
                        link.target = '_blank';
                        link.rel = 'noopener noreferrer';
                        link.textContent = project || projectUrl;
                        meta.appendChild(link);
                    } else {
                        meta.appendChild(document.createTextNode(project));
                    }
                    if (commitUrl) {
                        let commitLabel = '';
                        if (commitId) {
                            commitLabel = commitId.slice(0, 8);
                        } else {
                            const raw = commitUrl.split('#')[0].split('?')[0];
                            const parts = raw.split('/').filter(Boolean);
                            const last = parts.length ? parts[parts.length - 1] : '';
                            commitLabel = last ? last.slice(0, 8) : '';
                        }
                        if (!commitLabel) commitLabel = '提交链接';
                        const link = document.createElement('a');
                        link.href = commitUrl;
	                        link.target = '_blank';
	                        link.rel = 'noopener noreferrer';
	                        link.textContent = commitLabel;
	                        link.style.marginLeft = '8px';
	                        meta.appendChild(link);
	                    }
	                    if (mrUrl) {
	                        const link = document.createElement('a');
	                        link.href = mrUrl;
	                        link.target = '_blank';
	                        link.rel = 'noopener noreferrer';
	                        link.textContent = 'MR链接';
	                        link.style.marginLeft = '8px';
	                        meta.appendChild(link);
	                    }
	                    meta.appendChild(
	                        document.createTextNode(
	                            ` | 开发者: ${author} | 时间: ${updated} | 模型: ${modelName} | 得分: ${score} | 状态: ${formatReviewStatus(status)} | 重试: ${retryCount}`
	                        )
	                    );
	                }
	                if (links) {
	                    links.innerHTML = '';
	                }
	                if (body) {
	                    renderMarkdown(body, data.review_result || '(无审查详情)');
	                }
	            } catch (e) {
	                const body = document.getElementById('detailBody');
	                if (body) body.textContent = `加载失败: ${e && e.message ? e.message : e}`;
	            }
	        }

	        const JOB_STATUS_LABELS = {
	            pending: '排队中',
	            running: '执行中',
	            done: '已完成',
	            failed: '失败'
	        };

	        function formatJobStatus(status) {
	            if (!status) return '未知';
	            return JOB_STATUS_LABELS[status] || status;
	        }

	        function jobStatusClass(status) {
	            if (status === 'pending') return 'pending';
	            if (status === 'running') return 'running';
	            if (status === 'done') return 'done';
	            if (status === 'failed') return 'failed';
	            return 'pending';
	        }

	        function clearJobStatus() {
	            const el = document.getElementById('detailJobMeta');
	            if (!el) return;
	            el.textContent = '';
	            el.style.display = 'none';
	        }

	        function setJobStatusLoading(message = '后台任务: 加载中...') {
	            const el = document.getElementById('detailJobMeta');
	            if (!el) return;
	            el.textContent = message;
	            el.style.display = 'flex';
	        }

	        function renderJobStatus(job) {
	            const el = document.getElementById('detailJobMeta');
	            if (!el) return;
	            if (!job) {
	                clearJobStatus();
	                return;
	            }

	            const status = (job.status || '').toLowerCase();
	            el.textContent = '';
	            el.style.display = 'flex';
	            el.appendChild(document.createTextNode('后台任务: '));
	            const statusSpan = document.createElement('span');
	            statusSpan.className = `job-status ${jobStatusClass(status)}`;
	            statusSpan.textContent = formatJobStatus(status);
	            el.appendChild(statusSpan);

	            const extra = [];
	            const attempts = job.attempts != null ? job.attempts : '';
	            const maxAttempts = job.max_attempts != null ? job.max_attempts : '';
	            if (attempts !== '' && maxAttempts !== '') {
	                extra.push(`尝试 ${attempts}/${maxAttempts}`);
	            }
	            if (status === 'pending' && job.run_after_at) {
	                extra.push(`计划执行 ${job.run_after_at}`);
	            }
	            if (job.updated_at) {
	                extra.push(`更新时间 ${job.updated_at}`);
	            }
	            if (status === 'failed' && job.last_error) {
	                extra.push(`错误 ${truncate(job.last_error, 120)}`);
	            }
	            if (extra.length) {
	                el.appendChild(document.createTextNode(' | ' + extra.join(' | ')));
	            }
	        }

	        async function fetchJobStatus(recordId) {
	            try {
	                const res = await fetch(`/dashboard/api/reviews/${recordId}/job`);
	                const result = await res.json();
	                if (!res.ok) {
	                    throw new Error(result.error || '加载任务状态失败');
	                }
	                return result.job || null;
	            } catch (e) {
	                return null;
	            }
	        }

	        function stopJobStatusPolling() {
	            if (jobStatusTimer) {
	                clearTimeout(jobStatusTimer);
	                jobStatusTimer = null;
	            }
	            jobStatusPollToken += 1;
	        }

	        async function loadJobStatus(
	            recordId,
	            { poll = false, refreshOnDone = false, emptyCount = 0 } = {}
	        ) {
	            if (!recordId || currentDetailId !== recordId) return;
	            const token = jobStatusPollToken + 1;
	            jobStatusPollToken = token;

	            const job = await fetchJobStatus(recordId);
	            if (jobStatusPollToken !== token) return;
	            renderJobStatus(job);

	            if (!poll || currentDetailId !== recordId) {
	                return;
	            }

	            if (!job) {
	                if (emptyCount < 5) {
	                    jobStatusTimer = setTimeout(
	                        () =>
	                            loadJobStatus(recordId, {
	                                poll: true,
	                                refreshOnDone,
	                                emptyCount: emptyCount + 1
	                            }),
	                        2000
	                    );
	                }
	                return;
	            }

	            const status = (job.status || '').toLowerCase();
	            if (status === 'pending' || status === 'running') {
	                const delay = status === 'running' ? 2000 : 3000;
	                jobStatusTimer = setTimeout(
	                    () =>
	                        loadJobStatus(recordId, {
	                            poll: true,
	                            refreshOnDone: true,
	                            emptyCount: 0
	                        }),
	                    delay
	                );
	                return;
	            }

	            if (refreshOnDone) {
	                loadDetail(recordId);
	            }
	        }

	        // renderMarkdown provided by /static/review_markdown.js

	        async function retryCurrentRecord() {
	            if (!currentDetailId) return;
	            const btn = document.getElementById('retryBtn');
	            if (btn) btn.disabled = true;
	
	            try {
	                const res = await fetch(`/dashboard/api/reviews/${currentDetailId}/retry?type=${encodeURIComponent(currentType)}`, {
	                    method: 'POST'
	                });
	                const contentType = (res.headers.get('content-type') || '').toLowerCase();
	                let result = null;
	                if (contentType.includes('application/json')) {
	                    result = await res.json();
	                } else {
	                    const text = await res.text();
	                    throw new Error(text && text.trim() ? text.trim() : '非 JSON 响应');
	                }
	                if (!res.ok) {
	                    throw new Error(result.error || result.message || '重试失败');
	                }
	                stopJobStatusPolling();
	                setJobStatusLoading('重试已提交，正在排队...');
	                loadJobStatus(currentDetailId, { poll: true, refreshOnDone: true });
            } catch (e) {
                alert(`重试失败: ${e && e.message ? e.message : e}`);
            } finally {
                if (btn) btn.disabled = false;
            }
	        }

	        function prevPage() {
	            if (!lastPagination) return;
	            if (currentPage <= 1) return;
	            currentPage -= 1;
	            loadData();
	        }

	        function nextPage() {
	            if (!lastPagination) return;
	            const totalPages = lastPagination.total_pages || 1;
	            if (currentPage >= totalPages) return;
	            currentPage += 1;
	            loadData();
	        }

	        async function loadData() {
	            const startDate = document.getElementById('startDate').value;
	            const endDate = document.getElementById('endDate').value;
	            const author = document.getElementById('authorFilter').value;
	            const project = document.getElementById('projectFilter').value;
	            const language = (document.getElementById('languageFilter') || {}).value || '';

	            document.getElementById('loading').style.display = 'block';
	            document.getElementById('empty').style.display = 'none';
	            document.getElementById('pagination').style.display = 'none';
	            document.querySelector('#tableBody').innerHTML = '';

            try {
	                const params = new URLSearchParams({
	                    type: currentType,
	                    start_date: startDate,
	                    end_date: endDate,
	                    page: String(currentPage),
	                    page_size: String(pageSize),
	                    sort: sortField,
	                    order: sortOrder
	                });

                if (author) params.append('author', author);
                if (project) params.append('project', project);
                if (language) params.append('language', language);

                const response = await fetch(`/dashboard/api/reviews?${params}`);
                const result = await response.json();

                if (result.error) {
                    alert(result.error);
                    return;
                }

	                updateFilters(result.filters);
	                updateStats(result.stats);
	                updatePagination(result.pagination);
	                renderTable(result.data);
            } catch (error) {
                console.error('Error loading data:', error);
                alert('加载数据失败');
            } finally {
	                document.getElementById('loading').style.display = 'none';
            }
        }

        function updateFilters(filters) {
            const authorInput = document.getElementById('authorFilter');
            const projectInput = document.getElementById('projectFilter');
            const languageInput = document.getElementById('languageFilter');
            const authorList = document.getElementById('authorOptions');
            const projectList = document.getElementById('projectOptions');
            const languageList = document.getElementById('languageOptions');

            const currentAuthor = authorInput ? authorInput.value : '';
            const currentProject = projectInput ? projectInput.value : '';
            const currentLanguage = languageInput ? languageInput.value : '';

            if (authorList) authorList.innerHTML = '';
            if (projectList) projectList.innerHTML = '';
            if (languageList) languageList.innerHTML = '';

            (filters.authors || []).forEach(a => {
                if (a && authorList) {
                    authorList.innerHTML += `<option value="${a}"></option>`;
                }
            });

            (filters.projects || []).forEach(p => {
                if (p && projectList) {
                    projectList.innerHTML += `<option value="${p}"></option>`;
                }
            });

            (filters.languages || []).forEach(l => {
                if (l && languageList) {
                    languageList.innerHTML += `<option value="${l}"></option>`;
                }
            });

            if (authorInput) authorInput.value = currentAuthor;
            if (projectInput) projectInput.value = currentProject;
            if (languageInput) languageInput.value = currentLanguage;
        }

        function updateStats(stats) {
            document.getElementById('totalCount').textContent = stats.total;
            document.getElementById('successCount').textContent = stats.success;
            document.getElementById('failedCount').textContent = stats.failed;
            document.getElementById('avgScore').textContent = stats.avg_score;
        }

	        function updatePagination(pagination) {
	            lastPagination = pagination || null;
	            if (!lastPagination) {
	                document.getElementById('pagination').style.display = 'none';
	                return;
	            }

	            const total = lastPagination.total || 0;
	            const totalPages = lastPagination.total_pages || 1;
	            currentPage = lastPagination.page || currentPage;
	            pageSize = lastPagination.page_size || pageSize;

	            document.getElementById('pageMeta').textContent = `第 ${currentPage} / ${totalPages} 页，共 ${total} 条`;

	            const pageSizeSelect = document.getElementById('pageSize');
	            if (pageSizeSelect && String(pageSizeSelect.value) !== String(pageSize)) {
	                pageSizeSelect.value = String(pageSize);
	            }

	            document.getElementById('prevPage').disabled = currentPage <= 1;
	            document.getElementById('nextPage').disabled = currentPage >= totalPages;
	            document.getElementById('pagination').style.display = total > 0 ? 'flex' : 'none';
	        }

	        function renderTable(data) {
            const tbody = document.getElementById('tableBody');

            if (!data || data.length === 0) {
                document.getElementById('empty').style.display = 'block';
                return;
            }

	            const html = data.map(buildRowHtml).join('');
	            tbody.innerHTML = html;
        }

	        const REVIEW_STATUS_LABELS = {
	            success: '成功',
	            failed: '失败',
	            skipped: '跳过',
	            pending: '排队中',
	            running: '处理中'
	        };

	        function formatReviewStatus(status) {
	            if (!status) return '';
	            return REVIEW_STATUS_LABELS[status] || status;
	        }

	        function reviewStatusClass(status) {
	            if (status === 'success') return 'success';
	            if (status === 'skipped') return 'skipped';
	            if (status === 'pending' || status === 'running') return 'pending';
	            return 'failed';
	        }

	        function buildRowHtml(row) {
	            const recordId = row.id;
	            const statusClass = reviewStatusClass(row.status);
	            const statusText = formatReviewStatus(row.status);

	            const modelName = row.model_name || '';
	            const language = row.language || '';

	            let branchHtml = '';
	            if (currentType === 'mr') {
	                const sourceBranch = row.source_branch || '';
	                const targetBranch = row.target_branch || '';
	                const sourceBranchUrl = row.source_branch_url || '';
	                const targetBranchUrl = row.target_branch_url || '';
	
	                const sourceEl = sourceBranchUrl
	                    ? `<a href="${sourceBranchUrl}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()"><span class="branch-tag">${escapeHtml(sourceBranch)}</span></a>`
	                    : `<span class="branch-tag">${escapeHtml(sourceBranch)}</span>`;
	                const targetEl = targetBranchUrl
	                    ? `<a href="${targetBranchUrl}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()"><span class="branch-tag">${escapeHtml(targetBranch)}</span></a>`
	                    : `<span class="branch-tag">${escapeHtml(targetBranch)}</span>`;
	                branchHtml = `
	                    ${sourceEl}
	                    <span style="color: #999; margin: 0 4px;">→</span>
	                    ${targetEl}
	                `;
	            } else {
	                const branchUrl = row.branch_url || '';
	                const branch = row.branch || '';
	                branchHtml = branchUrl
	                    ? `<a href="${branchUrl}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()"><span class="branch-tag">${escapeHtml(branch)}</span></a>`
	                    : `<span class="branch-tag">${escapeHtml(branch)}</span>`;
	            }

	            const authorText = row.author || '';
	            const authorUrl = row.author_url || '';
	            const authorHtml = authorUrl
	                ? `<a href="${authorUrl}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">${escapeHtml(authorText)}</a>`
	                : escapeHtml(authorText);

	            const commitUrl = row.commit_url || row.url || '';
	            const commitText = row.commit_messages || '';
	            const commitHtml = commitUrl
	                ? `<a href="${commitUrl}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()" title="${escapeHtml(commitText)}">${escapeHtml(truncate(commitText, 120))}</a>`
	                : escapeHtml(truncate(commitText, 120));

	            const projectUrl = row.project_url || '';
	            const projectText = row.project_name || '';
	            const projectHtml = projectUrl
	                ? `<a href="${projectUrl}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">${escapeHtml(projectText)}</a>`
	                : escapeHtml(projectText);

	            const delta = row.delta || '';
	            const deltaHtml = delta.replace(/\+/g, '<span class="delta-positive">+').replace(/\n-/g, '</span><span class="delta-negative">-').replace(/<\/span>$/, '</span>');

	            return `
	                <tr onclick="openDetail(${recordId})" style="cursor: pointer;">
	                    <td>${projectHtml}</td>
	                    <td>${branchHtml}</td>
	                    <td>${authorHtml}</td>
	                    <td class="commit-col">${commitHtml}</td>
	                    <td class="delta">${deltaHtml.replace(/\n/g, '<br>')}</td>
	                    <td>${escapeHtml(modelName)}</td>
	                    <td>${escapeHtml(language)}</td>
	                    <td><span class="score">${row.score.toFixed(1)}</span></td>
	                    <td><span class="status ${statusClass}">${statusText}</span></td>
	                    <td>${escapeHtml(row.updated_at || '')}</td>
	                </tr>
	            `;
	        }


        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function truncate(text, length) {
            if (!text) return '';
            return text.length > length ? text.substring(0, length) + '...' : text;
        }

        function exportData() {
            // Server-side export: avoids exporting only the current page or stale cached data.
            const startDate = document.getElementById('startDate').value;
            const endDate = document.getElementById('endDate').value;
            const author = document.getElementById('authorFilter').value;
            const project = document.getElementById('projectFilter').value;

            const params = new URLSearchParams();
            params.append('type', currentType);
            if (startDate) params.append('start_date', startDate);
            if (endDate) params.append('end_date', endDate);
            if (author) params.append('author', author);
            if (project) params.append('project', project);

            // Trigger a file download.
            window.location.href = `/dashboard/api/reviews/export?${params}`;
        }

	        function setLlmStatus(state) {
	            const dot = document.getElementById('llmStatusDot');
	            if (!dot) return;
	            dot.classList.remove('ok', 'bad', 'loading', 'unknown');
	            dot.classList.add(state);
	        }

	        async function checkLlmAvailability() {
	            const now = Date.now();
	            if (now - lastLlmCheckAt < 5000) {
	                return;
	            }

	            const nameBtn = document.getElementById('llmModelName');
	            if (nameBtn) nameBtn.disabled = true;
	            setLlmStatus('loading');
	            lastLlmCheckAt = now;
	
	            try {
	                const res = await fetch('/dashboard/api/llm/check', { method: 'POST' });
	                const result = await res.json();
	                if (!res.ok) {
	                    throw new Error(result.error || '检测失败');
	                }
	                setLlmStatus(result.available ? 'ok' : 'bad');
	                if (nameBtn && result.model_name) {
	                    nameBtn.textContent = result.model_name;
	                }
	            } catch (e) {
	                setLlmStatus('bad');
	            } finally {
	                if (nameBtn) nameBtn.disabled = false;
	            }
	        }

	        async function loadLlmStatus() {
	            try {
	                const res = await fetch('/dashboard/api/llm/status');
	                const result = await res.json();
	                if (!res.ok) {
	                    throw new Error(result.error || '加载失败');
	                }
	                if (result.available === true) {
	                    setLlmStatus('ok');
	                } else if (result.available === false) {
	                    setLlmStatus('bad');
	                } else {
	                    setLlmStatus('unknown');
	                }
	                const nameBtn = document.getElementById('llmModelName');
	                if (nameBtn && result.model_name) {
	                    nameBtn.textContent = result.model_name;
	                }
	            } catch (e) {
	                setLlmStatus('unknown');
	            }
	        }

        function showToast(html, { duration = 4200, anchor = null } = {}) {
            const toast = document.createElement('div');
            toast.className = 'toast';
            toast.innerHTML = html;
            toast.style.visibility = 'hidden';
            document.body.appendChild(toast);

            const margin = 8;
            const rect = anchor ? anchor.getBoundingClientRect() : null;
            const toastWidth = toast.offsetWidth || 280;
            const toastHeight = toast.offsetHeight || 60;
            let top = rect ? rect.bottom + margin : margin;
            let left = rect ? rect.left : margin;

            if (rect && rect.bottom + toastHeight + margin > window.innerHeight) {
                top = rect.top - toastHeight - margin;
            }
            if (left + toastWidth + margin > window.innerWidth) {
                left = Math.max(margin, window.innerWidth - toastWidth - margin);
            }
            if (left < margin) left = margin;
            if (top < margin) top = margin;

            toast.style.top = `${top}px`;
            toast.style.left = `${left}px`;
            toast.style.visibility = 'visible';
            requestAnimationFrame(() => toast.classList.add('show'));

            setTimeout(() => {
                toast.classList.add('hide');
                setTimeout(() => toast.remove(), 220);
            }, duration);
        }

	        function updateWorkerStatsChip(stats) {
	            const el = document.getElementById('workerSuccessRate');
	            if (!el) return;
	            if (!stats || stats.success_rate == null) {
	                el.textContent = '-';
	                return;
	            }
	            const rate = Number(stats.success_rate);
	            if (!Number.isFinite(rate)) {
	                el.textContent = '-';
	                return;
	            }
	            el.textContent = `${(rate * 100).toFixed(1)}%`;
	        }

	        async function loadWorkerStats({ force = false } = {}) {
	            const now = Date.now();
	            if (!force && lastWorkerStats && now - lastWorkerStatsAt < 5000) {
	                return lastWorkerStats;
	            }
	            try {
	                const res = await fetch('/dashboard/api/worker/stats');
	                const result = await res.json();
	                if (!res.ok) {
	                    throw new Error(result.error || '加载失败');
	                }
	                lastWorkerStats = result || null;
	                lastWorkerStatsAt = now;
	                updateWorkerStatsChip(lastWorkerStats);
	                return lastWorkerStats;
	            } catch (e) {
	                updateWorkerStatsChip(null);
	                return null;
	            }
	        }

	        function buildWorkerToast(stats) {
	            if (!stats) {
	                return '<div class="toast-title">Worker 统计</div><div>暂无数据</div>';
	            }
	            const queue = stats.queue || {};
	            const pending = Number(queue.pending || 0);
	            const running = Number(queue.running || 0);
	            const done = Number(queue.done || 0);
	            const failed = Number(queue.failed || 0);
	            const total = Number(queue.total || pending + running + done + failed);
	            const processed = stats.processed || {};
	            const processedTotal = Number(
	                processed.total != null ? processed.total : done + failed
	            );
	            const rate = Number(stats.success_rate);
	            const rateText = Number.isFinite(rate) ? `${(rate * 100).toFixed(1)}%` : '暂无';
	            const latestUpdate = stats.latest_update_at || '';
	            const latestFailedAt = stats.latest_failed_at || '';
	            const latestFailedError = stats.latest_failed_error || '';

	            const lines = [
	                '<div class="toast-title">Worker 统计</div>',
	                `<div>成功率: ${rateText}</div>`,
	                `<div>处理中: ${running} | 排队: ${pending} | 完成: ${done} | 失败: ${failed} | 总计: ${total}</div>`
	            ];
	            if (processedTotal > 0) {
	                lines.push(`<div>已处理: ${processedTotal}</div>`);
	            }
	            if (latestUpdate) {
	                lines.push(`<div>最近更新时间: ${latestUpdate}</div>`);
	            }
	            if (latestFailedAt) {
	                const err = latestFailedError ? truncate(latestFailedError, 120) : '暂无错误信息';
	                lines.push(`<div>最近失败: ${latestFailedAt}</div>`);
	                lines.push(`<div>失败原因: ${err}</div>`);
	            }
	            return lines.join('');
	        }

	        document.addEventListener('DOMContentLoaded', () => {
	            initDates();
	            refreshSortIndicators();
	            setLlmStatus('unknown');
	            loadLlmStatus();
	            loadWorkerStats();

	            let filterDebounceTimer = null;
	            const scheduleFilterLoad = () => {
	                if (filterDebounceTimer) {
	                    clearTimeout(filterDebounceTimer);
	                }
	                filterDebounceTimer = setTimeout(() => {
	                    currentPage = 1;
	                    loadData();
	                }, 300);
	            };

	            const modal = document.getElementById('detailModal');
	            if (modal) {
	                modal.addEventListener('click', (e) => {
	                    if (e.target === modal) {
	                        closeDetail();
	                    }
	                });
	            }

	            const detailLinks = document.getElementById('detailLinks');
	            if (detailLinks) {
	                detailLinks.addEventListener('click', (e) => {
	                    // Clicking links inside the modal should not bubble to the overlay.
	                    e.stopPropagation();
	                });
	            }

	            document.addEventListener('keydown', (e) => {
	                if (e.key === 'Escape') {
	                    closeDetail();
	                }
	            });

	            const pageSizeSelect = document.getElementById('pageSize');
	            if (pageSizeSelect) {
	                pageSizeSelect.addEventListener('change', () => {
	                    const v = parseInt(pageSizeSelect.value, 10);
	                    pageSize = Number.isFinite(v) ? v : 50;
	                    currentPage = 1;
	                    loadData();
	                });
	            }

            const bindFilterChange = (id, listenInput = false) => {
                const el = document.getElementById(id);
                if (!el) return;
                el.addEventListener('change', () => {
                    scheduleFilterLoad();
                });
                if (listenInput) {
                    el.addEventListener('input', () => {
                        scheduleFilterLoad();
                    });
                }
            };
            bindFilterChange('startDate');
            bindFilterChange('endDate');
            bindFilterChange('authorFilter', true);
            bindFilterChange('projectFilter', true);
            bindFilterChange('languageFilter', true);

	            const llmBtn = document.getElementById('llmModelName');
	            if (llmBtn) {
	                llmBtn.addEventListener('click', () => checkLlmAvailability());
	            }

            const workerChip = document.getElementById('workerStatsChip');
            if (workerChip) {
                workerChip.addEventListener('click', async () => {
                    const stats = await loadWorkerStats({ force: true });
                    showToast(buildWorkerToast(stats), { anchor: workerChip });
                });
            }
            const workerRefresh = document.getElementById('workerStatsRefresh');
            if (workerRefresh) {
                workerRefresh.addEventListener('click', async () => {
                    const stats = await loadWorkerStats({ force: true });
                    showToast(buildWorkerToast(stats), { anchor: workerRefresh });
                });
            }
	            setInterval(() => {
	                loadWorkerStats();
	            }, 30000);

	            loadData();
	            // auto refresh timer removed
	        });
