let currentType = 'push';  // 默认选中代码推送
        let currentPage = 1;
        let pageSize = 50;
        let lastPagination = null;
        let sortField = 'updated_at';
        let sortOrder = 'desc';
        let currentDetailId = null;
        let lastLlmCheckAt = 0;

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

	            loadDetail(recordId);
	        }

	        function closeDetail() {
	            const modal = document.getElementById('detailModal');
	            if (!modal) return;
	            modal.classList.remove('open');
	            modal.setAttribute('aria-hidden', 'true');
	            currentDetailId = null;
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
	                const author = data.author || '';
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
	                            ` | 开发者: ${author} | 时间: ${updated} | 模型: ${modelName} | 得分: ${score} | 状态: ${status} | 重试: ${retryCount}`
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
            const authorSelect = document.getElementById('authorFilter');
            const projectSelect = document.getElementById('projectFilter');
            const languageSelect = document.getElementById('languageFilter');

            const currentAuthor = authorSelect.value;
            const currentProject = projectSelect.value;
            const currentLanguage = languageSelect ? languageSelect.value : '';

            authorSelect.innerHTML = '<option value="">全部</option>';
            projectSelect.innerHTML = '<option value="">全部</option>';
            if (languageSelect) languageSelect.innerHTML = '<option value="">全部</option>';

            filters.authors.forEach(a => {
                if (a) {
                    authorSelect.innerHTML += `<option value="${a}">${a}</option>`;
                }
            });

            filters.projects.forEach(p => {
                if (p) {
                    projectSelect.innerHTML += `<option value="${p}">${p}</option>`;
                }
            });

            (filters.languages || []).forEach(l => {
                if (languageSelect && l) {
                    languageSelect.innerHTML += `<option value="${l}">${l}</option>`;
                }
            });

            authorSelect.value = currentAuthor;
            projectSelect.value = currentProject;
            if (languageSelect) languageSelect.value = currentLanguage;
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

	        function buildRowHtml(row) {
	            const recordId = row.id;
	            const statusClass = row.status === 'success' ? 'success' : 'failed';
	            const statusText = row.status === 'success' ? '成功' : '失败';

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

	        document.addEventListener('DOMContentLoaded', () => {
	            initDates();
	            refreshSortIndicators();
	            setLlmStatus('unknown');
	            loadLlmStatus();

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

	            const bindFilterChange = (id) => {
	                const el = document.getElementById(id);
	                if (!el) return;
	                el.addEventListener('change', () => {
	                    scheduleFilterLoad();
	                });
	            };
	            bindFilterChange('startDate');
	            bindFilterChange('endDate');
	            bindFilterChange('authorFilter');
	            bindFilterChange('projectFilter');
	            bindFilterChange('languageFilter');

	            const llmBtn = document.getElementById('llmModelName');
	            if (llmBtn) {
	                llmBtn.addEventListener('click', () => checkLlmAvailability());
	            }

	            loadData();
	            // auto refresh timer removed
	        });
