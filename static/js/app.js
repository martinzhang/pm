/* ── Globals ── */
var ME = null;
var USERS = [];
var currentProject = null;
var calYear, calMonth;

// ── Custom phase support: wrap PHASE_MAP/PHASE_COLORS with fallbacks ──
// Unknown phase keys → label = key itself, color = hash-based pastel
(function(){
    function hashColor(s){
        if (!s) return '#95A3B3';
        var h = 0; for (var i = 0; i < s.length; i++) h = ((h * 31) + s.charCodeAt(i)) >>> 0;
        return 'hsl(' + (h % 360) + ', 42%, 62%)';
    }
    if (typeof Proxy !== 'undefined') {
        try {
            PHASE_MAP = new Proxy(PHASE_MAP, { get: function(t, k){ return (k in t) ? t[k] : (k && k !== 'undefined' ? k : ''); } });
            PHASE_COLORS = new Proxy(PHASE_COLORS, { get: function(t, k){ return (k in t) ? t[k] : hashColor(String(k||'')); } });
        } catch(e) {}
    }
    window._hashPhaseColor = hashColor;
})();
var ganttZoom = 'week';
var ORG_DATA = null;
var USERS_MAP = {};

// ── Init ──
(function(){
    var d = new Date();
    calYear = d.getFullYear();
    calMonth = d.getMonth() + 1;
    api('/api/me', null, function(u){ ME = u; });
    api('/api/users', null, function(u){ USERS = u; USERS.forEach(function(usr){ USERS_MAP[usr.username] = usr; }); });
    loadDashboard();
})();

// ── API ──
function api(url, body, cb, method) {
    var opts = { credentials: 'same-origin' };
    if (body !== null && body !== undefined) {
        if (body instanceof FormData) {
            opts.method = method || 'POST';
            opts.body = body;
        } else {
            opts.method = method || 'POST';
            opts.headers = { 'Content-Type': 'application/json' };
            opts.body = JSON.stringify(body);
        }
    }
    fetch(B + url, opts)
        .then(function(r){ return r.json(); })
        .then(function(data){
            if (data.error) { toast(data.error, true); return; }
            if (cb) cb(data);
        })
        .catch(function(){ toast('网络错误', true); });
}

// ── Nav ──
var pageStack = ['dashboard'];
function switchTab(tab) {
    pageStack = [tab];
    showPage(tab);
    document.querySelectorAll('.tab-btn').forEach(function(b){ b.classList.remove('active'); });
    document.getElementById('tab-' + tab).classList.add('active');
    document.getElementById('nav-back').style.display = 'none';
    if (tab === 'dashboard') { setTitle('<span class="cursor-blink">&gt;_</span>奈娃咖啡项目管理', true); loadDashboard(); }
    else if (tab === 'projects') { setTitle('全部项目'); loadProjects(); }
    else if (tab === 'calendar') { setTitle('我的日历'); loadCalendar(); }
    else if (tab === 'meetings') { setTitle('会议纪要'); loadMeetings(); }
}
function showPage(id) {
    document.querySelectorAll('.page').forEach(function(p){ p.classList.remove('active'); });
    var el = document.getElementById('page-' + id);
    if (el) el.classList.add('active');
    // Hide/show FABs
    document.querySelectorAll('.fab').forEach(function(f){ f.style.display = 'none'; });
    if (id === 'projects') document.querySelector('#page-projects .fab').style.display = '';
    if (id === 'project') document.getElementById('fab-add-task').style.display = '';
    if (id === 'calendar') document.querySelector('#page-calendar .fab').style.display = '';
    if (id === 'meetings') document.querySelector('#page-meetings .fab').style.display = '';
}
function pushPage(id) {
    pageStack.push(id);
    showPage(id);
    document.getElementById('nav-back').style.display = '';
}
function goBack() {
    if (pageStack.length > 1) {
        pageStack.pop();
        var prev = pageStack[pageStack.length - 1];
        showPage(prev);
        if (pageStack.length <= 1) document.getElementById('nav-back').style.display = 'none';
        if (prev === 'projects') { setTitle('全部项目'); loadProjects(); }
        else if (prev === 'dashboard') { setTitle('<span class="cursor-blink">&gt;_</span>奈娃咖啡项目管理', true); loadDashboard(); }
        else if (prev === 'calendar') setTitle('我的日历');
        else if (prev === 'meetings') { setTitle('会议纪要'); loadMeetings(); }
    }
}
function setTitle(t, isHtml) {
    var el = document.getElementById('nav-title');
    if (isHtml) el.innerHTML = t;
    else el.textContent = t;
}

// ── Toast ──
function toast(msg, isErr) {
    var t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast' + (isErr ? ' error' : '');
    clearTimeout(window._tt);
    window._tt = setTimeout(function(){ t.classList.add('hidden'); }, 2500);
}

// ── Modal ──
function openModal(html) {
    document.getElementById('modal-content').innerHTML = html;
    document.getElementById('modal-overlay').classList.remove('hidden');
}
function closeModal() {
    document.getElementById('modal-overlay').classList.add('hidden');
}

// ── In-page confirm dialog (replacement for native confirm) ──
function confirmDialog(msg, onOk) {
    var existing = document.getElementById('confirm-overlay');
    if (existing) existing.parentNode.removeChild(existing);
    var ov = document.createElement('div');
    ov.id = 'confirm-overlay';
    ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:9999;display:flex;align-items:center;justify-content:center;';
    ov.innerHTML = '<div style="background:#fff;border-radius:14px;padding:20px;min-width:260px;max-width:84vw;box-shadow:0 10px 40px rgba(0,0,0,0.2)">'
        + '<div style="font-size:15px;color:#1a1a1a;margin-bottom:16px;line-height:1.5">' + msg + '</div>'
        + '<div style="display:flex;gap:8px;justify-content:flex-end">'
        + '<button id="confirm-cancel" class="btn btn-sm btn-ghost">取消</button>'
        + '<button id="confirm-ok" class="btn btn-sm btn-danger">确定</button>'
        + '</div></div>';
    document.body.appendChild(ov);
    function close() { if (ov.parentNode) ov.parentNode.removeChild(ov); }
    document.getElementById('confirm-cancel').onclick = function(e) { e.stopPropagation(); close(); };
    document.getElementById('confirm-ok').onclick = function(e) { e.stopPropagation(); close(); if (onOk) onOk(); };
    ov.onclick = function(e) { if (e.target === ov) close(); };
}

// ── Alerts ──
function toggleAlerts() {
    var p = document.getElementById('alert-panel');
    var b = document.getElementById('alert-backdrop');
    if (p.classList.contains('hidden')) {
        p.classList.remove('hidden'); b.classList.remove('hidden');
        loadAlerts();
    } else {
        p.classList.add('hidden'); b.classList.add('hidden');
    }
}
function loadAlerts() {
    api('/api/alerts', null, function(data) {
        var dot = document.getElementById('alert-dot');
        dot.style.display = data.unread > 0 ? '' : 'none';
        var html = '';
        if (!data.alerts.length) {
            html = '<div class="empty" style="padding:40px"><div class="empty-text">暂无通知</div></div>';
        }
        data.alerts.forEach(function(a) {
            html += '<div class="alert-item ' + (a.is_read ? '' : 'unread') + '" onclick="readAlert(' + a.id + (a.related_project_id ? ',' + a.related_project_id : '') + ')">'
                + '<div class="alert-title">' + esc(a.title) + '</div>'
                + '<div class="alert-msg">' + esc(a.message || '') + '</div>'
                + '<div class="alert-time">' + timeago(a.created_at) + '</div></div>';
        });
        document.getElementById('alert-list').innerHTML = html;
    }, 'GET');
}
function readAlert(aid, pid) {
    api('/api/alerts/' + aid + '/read', {}, function() {
        if (pid) openProject(pid);
        toggleAlerts();
    }, 'PUT');
}
function markAllRead() {
    api('/api/alerts/read-all', {}, function() { loadAlerts(); toast('全部已读'); });
}

// Check alerts on load
setTimeout(function() {
    api('/api/alerts', null, function(data) {
        document.getElementById('alert-dot').style.display = data.unread > 0 ? '' : 'none';
    }, 'GET');
}, 1000);

// ── Dashboard ──
function loadDashboard() {
    api('/api/dashboard', null, function(d) {
        document.getElementById('dash-stats').innerHTML =
            '<div class="dash-stat" onclick="projectFilter=\'active\';switchTab(\'projects\')" style="cursor:pointer"><div class="dash-stat-num">' + d.total_projects + '</div><div class="dash-stat-label">进行中项目</div></div>'
            + '<div class="dash-stat"><div class="dash-stat-num">' + d.my_tasks.length + '</div><div class="dash-stat-label">我的待办</div></div>'
            + '<div class="dash-stat dash-overdue"><div class="dash-stat-num">' + d.overdue_count + '</div><div class="dash-stat-label">已逾期</div></div>'
            + '<div class="dash-stat"><div class="dash-stat-num">' + d.unread_alerts + '</div><div class="dash-stat-label">未读通知</div></div>';
        var html = '';
        if (!d.my_tasks.length) {
            html = '<div class="empty"><div class="empty-text">没有代办任务 -- 去钓小鱼吧</div></div>';
        }
        d.my_tasks.forEach(function(t) {
            var overdue = t.end_date && t.end_date < new Date().toISOString().slice(0,10) && t.progress < 100;
            html += '<div class="task-item" onclick="openProject(' + t.project_id + ')">'
                + progressRing(t.progress, 32)
                + '<div class="task-info">'
                + '<div class="task-name">' + esc(t.name) + '</div>'
                + '<div class="task-sub">'
                + '<span style="color:' + (t.project_color || 'var(--main)') + '">' + esc(t.project_name) + '</span>'
                + '<span>' + (PHASE_MAP[t.phase] || '') + '</span>'
                + (overdue ? '<span style="color:#E85D5D;font-weight:600">已逾期</span>' : '<span>' + (t.end_date || '') + (t.start_time||t.end_time ? ' ⏰ ' + (t.start_time||'') + (t.end_time ? (t.start_time?'–':'截止 ')+t.end_time : '') : '') + '</span>')
                + '</div></div>'
                + priorityTag(t.priority)
                + '<button class="dash-done-btn" title="标记完成" onclick="event.stopPropagation();quickCompleteTask(' + t.id + ',100);this.closest(\'.task-item\').style.opacity=\'0.4\'">'
                + '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4,10 8,14 16,6"/></svg>'
                + '</button>'
                + '</div>';
        });
        // Recently completed (last 14d) — with overdue badge
        if (d.recent_completed && d.recent_completed.length) {
            html += '<div class="section-title" style="margin-top:18px;padding:0 4px 8px;font-size:13px;color:var(--muted);font-weight:600">最近完成</div>';
            d.recent_completed.forEach(function(t) {
                var badge;
                if (t.end_date && t.completed_at && t.completed_at.slice(0,10) > t.end_date) {
                    var cd = t.completed_at.slice(0,10);
                    var mo = parseInt(cd.slice(5,7),10), dd = parseInt(cd.slice(8,10),10);
                    badge = '<span style="color:#E85D5D;font-weight:600">逾期完成 · ' + mo + '月' + dd + '日</span>';
                } else {
                    badge = '<span style="color:#34C759;font-weight:600">已完成</span>';
                }
                html += '<div class="task-item" onclick="openProject(' + t.project_id + ')">'
                    + progressRing(100, 32)
                    + '<div class="task-info">'
                    + '<div class="task-name" style="text-decoration:line-through;opacity:0.7">' + esc(t.name) + '</div>'
                    + '<div class="task-sub">'
                    + '<span style="color:' + (t.project_color || 'var(--main)') + '">' + esc(t.project_name) + '</span>'
                    + badge
                    + '</div></div>'
                    + priorityTag(t.priority)
                    + '</div>';
            });
        }
        document.getElementById('dash-tasks').innerHTML = html;
    }, 'GET');
}

// ── Projects ──
var projectFilter = 'active';
function loadProjects() {
    var fHtml = '';
    [['', '全部'], ['active','进行中'], ['paused','暂停'], ['completed','已完成']].forEach(function(s) {
        fHtml += '<span class="chip ' + (projectFilter === s[0] ? 'active' : '') + '" onclick="projectFilter=\'' + s[0] + '\';loadProjects()">' + s[1] + '</span>';
    });
    document.getElementById('project-filter').innerHTML = fHtml;

    api('/api/projects?status=' + projectFilter, null, function(list) {
        var html = '';
        if (!list.length) {
            html = '<div class="empty"><div class="empty-icon">&#128194;</div><div class="empty-text">还没有项目</div></div>';
        }
        list.forEach(function(p) {
            html += '<div class="card project-card" onclick="openProject(' + p.id + ')">'
                + '<div class="project-card-top">'
                + '<div class="project-dot" style="background:' + (p.color || '#95A3B3') + '"></div>'
                + '<div class="project-name">' + esc(p.name) + '</div>'
                + '</div>'
                + '<div class="progress-bar"><div class="progress-fill" style="width:' + p.avg_progress + '%;background:' + (p.color || 'var(--main)') + '"></div></div>'
                + '<div class="project-meta">'
                + '<span>' + p.task_done + '/' + p.task_total + ' 任务</span>'
                + '<span>进度 ' + p.avg_progress + '%</span>'
                + (p.deadline ? '<span>截止 ' + p.deadline + '</span>' : '')
                + '</div></div>';
        });
        document.getElementById('projects-list').innerHTML = html;
    }, 'GET');
}

// ── Open Project ──
function openProject(pid) {
    api('/api/projects/' + pid, null, function(p) {
        currentProject = p;
        setTitle(p.name);
        pushPage('project');
        renderProjectDetail(p);
    }, 'GET');
}
function reloadProject() {
    if (!currentProject) return;
    var listEl = document.getElementById('list-view');
    window._keepView = listEl && listEl.style.display !== 'none' ? 'list' : 'gantt';
    openProject(currentProject.id);
}

function renderProjectDetail(p) {
    var html = '';
    // Project header
    html += '<div class="card" style="border-left:4px solid ' + (p.color||'#95A3B3') + ';cursor:default">'
        + '<div class="flex-between"><div class="project-name">' + esc(p.name) + '</div>'
        + '<button class="btn btn-sm btn-ghost" onclick="openProjectForm(' + p.id + ')">编辑</button></div>'
        + (p.description ? '<div class="text-muted mt-8">' + esc(p.description) + '</div>' : '')
        + '<div class="progress-bar mt-8"><div class="progress-fill" style="width:' + p.avg_progress + '%;background:' + (p.color||'var(--main)') + '"></div></div>'
        + '<div class="project-meta mt-8"><span>总进度 ' + p.avg_progress + '%</span><span>'
        + p.task_done + '/' + p.task_total + ' 完成</span>'
        + (p.deadline ? '<span>截止 ' + p.deadline + '</span>' : '') + '</div>'
        + (function() {
            var vt = p.visible_to || [];
            if (!vt.length) return '<div class="visible-tags mt-8"><span class="visible-tag">仅创建人' + (p.owner_name ? '（' + esc(p.owner_name) + '）' : '') + '与任务相关人可见</span></div>';
            var tags = '';
            vt.forEach(function(uname) {
                var usr = USERS_MAP[uname];
                tags += '<span class="visible-tag">' + esc(usr ? usr.display_name : uname) + '</span>';
            });
            return '<div class="visible-tags mt-8"><span style="color:var(--muted);font-size:12px;margin-right:2px">可见范围:</span>' + tags + '</div>';
        })()
        + '</div>';


    // Project files
    var filesHTML = '<div class="card" style="cursor:default">';
    filesHTML += '<div class="section-title">项目附件</div>';
    filesHTML += '<div class="file-grid">';
    (p.files||[]).forEach(function(f) {
        var ext = f.original_name.split('.').pop().toLowerCase();
        var isImg = ['jpg','jpeg','png','gif','webp'].indexOf(ext) >= 0;
        filesHTML += '<div class="file-thumb" onclick="window.open(B+\'/api/project-uploads/' + p.id + '/' + f.filename + '\')">';
        if (isImg) filesHTML += '<img src="' + B + '/api/project-uploads/' + p.id + '/' + f.filename + '" loading="lazy">';
        else filesHTML += '<div class="file-thumb-icon"><span class="ext">' + ext.toUpperCase() + '</span><span>' + esc(f.original_name).slice(0,8) + '</span></div>';
        filesHTML += '<button class="file-del" onclick="event.stopPropagation();deleteProjectFile(' + f.id + ')">x</button></div>';
    });
    filesHTML += '</div>';
    filesHTML += '<div style="margin-top:8px"><label class="btn btn-sm btn-ghost" style="cursor:pointer">'
        + '<input type="file" style="display:none" onchange="uploadProjectFile(' + p.id + ',this)">'
        + '上传文件</label></div></div>';

    // View toggle
    html += '<div class="chip-bar" style="margin-top:4px">'
        + '<span class="chip active" id="view-gantt-btn" onclick="setView(\'gantt\')">甘特图</span>'
        + '<span class="chip" id="view-list-btn" onclick="setView(\'list\')">列表</span></div>';

    // Gantt
    html += '<div id="gantt-view">' + renderGantt(p) + '</div>';

    // Task list
    html += '<div id="list-view" style="display:none">';
    if (!p.tasks.length) {
        html += '<div class="empty"><div class="empty-text">还没有任务 -- 点右下角 + 创建</div></div>';
    }
    p.tasks.forEach(function(t) {
        html += taskItemHtml(t);
    });
    html += '</div>';

    // Project files — placed at the bottom, after the gantt & task list
    html += filesHTML;

    document.getElementById('project-detail').innerHTML = html;
    setTimeout(ganttAttachHandlers, 0);
    if (window._keepView) { setView(window._keepView); window._keepView = null; }
}

function setView(v) {
    document.getElementById('gantt-view').style.display = v === 'gantt' ? '' : 'none';
    document.getElementById('list-view').style.display = v === 'list' ? '' : 'none';
    document.getElementById('view-gantt-btn').className = 'chip' + (v === 'gantt' ? ' active' : '');
    document.getElementById('view-list-btn').className = 'chip' + (v === 'list' ? ' active' : '');
}

function taskItemHtml(t) {
    var collabCount = t.collaborator_ids ? String(t.collaborator_ids).split(',').filter(Boolean).length : 0;
    var collabBadge = collabCount > 0
        ? ' <span class="collab-badge" title="' + collabCount + ' 位协作者">+' + collabCount + '</span>'
        : '';
    var isDone = t.progress >= 100;
    return '<div class="task-item' + (isDone ? ' task-done' : '') + '" onclick="openTaskDetail(' + t.id + ')">'
        + progressRing(t.progress, 32)
        + '<div class="task-info">'
        + '<div class="task-name"><span class="tag phase-tag" style="background:' + (PHASE_COLORS[t.phase]||'#95A3B3') + ';font-size:10px;padding:1px 6px">'
        + (PHASE_MAP[t.phase]||'') + '</span> ' + esc(t.name) + '</div>'
        + '<div class="task-sub">'
        + (t.assignee_name ? '<span>' + esc(t.assignee_name) + collabBadge + '</span>' : (collabCount > 0 ? '<span>未分配' + collabBadge + '</span>' : ''))
        + '<span>' + (t.start_date||'') + ' ~ ' + (t.end_date||'') + '</span>'
        + '</div></div>'
        + priorityTag(t.priority)
        + '<button class="dash-done-btn' + (isDone ? ' dash-done-btn-reopen' : '') + '" title="' + (isDone ? '重新开启' : '标记完成') + '" '
        + 'onclick="event.stopPropagation();quickCompleteTask(' + t.id + ',' + (isDone ? 0 : 100) + ')">'
        + '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4,10 8,14 16,6"/></svg>'
        + '</button>'
        + '</div>';
}
function quickCompleteTask(tid, progress) {
    api('/api/tasks/' + tid, {progress: progress}, function(){ reloadProject(); toast(progress >= 100 ? '已完成 ✓' : '已重新开启'); }, 'PUT');
}

// ── Gantt ──
function renderGantt(p) {
    if (!p.tasks.length) return '<div class="empty"><div class="empty-text">添加任务后会显示甘特图</div></div>';
    var today = new Date(); today.setHours(0,0,0,0);
    // Find date range
    var minD = null, maxD = null;
    p.tasks.forEach(function(t) {
        var s = parseDate(t.start_date), e = parseDate(t.end_date);
        if (s && (!minD || s < minD)) minD = s;
        if (e && (!maxD || e > maxD)) maxD = e;
    });
    if (!minD) minD = new Date(today);
    if (!maxD) maxD = new Date(today);
    // Pad
    minD = new Date(minD); minD.setDate(minD.getDate() - 3);
    maxD = new Date(maxD); maxD.setDate(maxD.getDate() + 7);
    var colW = ganttZoom === 'day' ? 40 : ganttZoom === 'week' ? 28 : 12;
    var days = [];
    var d = new Date(minD);
    while (d <= maxD) { days.push(new Date(d)); d.setDate(d.getDate() + 1); }
    var LABEL_W = 160;
    // Timeline header
    var tl = '<div class="gantt-timeline" style="padding-left:' + LABEL_W + 'px">';
    days.forEach(function(day) {
        var isToday = day.toDateString() === today.toDateString();
        var isWk = day.getDay() === 0 || day.getDay() === 6;
        var label = ganttZoom === 'month' ? (day.getDate() === 1 ? (day.getMonth()+1)+'月' : '') :
            (ganttZoom === 'week' ? (day.getDay()===1 ? (day.getMonth()+1)+'/'+day.getDate() : day.getDate()) :
            (day.getMonth()+1)+'/'+day.getDate());
        tl += '<div class="gantt-col' + (isToday?' today':'') + (isWk?' weekend':'') + '" style="width:'+colW+'px;min-width:'+colW+'px">' + label + '</div>';
    });
    tl += '</div>';
    // Rows
    var rows = '';
    var todayIdx = -1;
    days.forEach(function(day,i){ if(day.toDateString()===today.toDateString()) todayIdx=i; });
    var taskPos = {};  // id -> {top, left, width, rowIdx}
    var ROW_H = 42;
    var BAR_H = 24;
    var BAR_TOP = 9;
    p.tasks.forEach(function(t, ri) {
        rows += '<div class="gantt-row" data-task-id="' + t.id + '">';
        rows += '<div class="gantt-row-label" onclick="openTaskDetail(' + t.id + ')">' + esc(t.name) + '</div>';
        rows += '<div class="gantt-row-grid">';
        days.forEach(function(day) {
            var isToday = day.toDateString() === today.toDateString();
            var isWk = day.getDay()===0||day.getDay()===6;
            rows += '<div class="gantt-cell' + (isToday?' today':'') + (isWk?' weekend':'') + '" style="width:'+colW+'px;min-width:'+colW+'px"></div>';
        });
        // Bar
        var sd = parseDate(t.start_date), ed = parseDate(t.end_date);
        if (sd && ed) {
            var startOff = Math.round((sd - minD) / 86400000);
            var dur = Math.max(1, Math.round((ed - sd) / 86400000) + 1);
            var left = startOff * colW;
            var w = dur * colW - 4;
            var col = PHASE_COLORS[t.phase] || p.color || '#95A3B3';
            taskPos[t.id] = { rowIdx: ri, left: left, width: w, top: ri * ROW_H + BAR_TOP, color: col };
            rows += '<div class="gantt-bar" '
                + 'data-task-id="' + t.id + '" '
                + 'data-start="' + t.start_date + '" '
                + 'data-end="' + t.end_date + '" '
                + 'style="left:' + left + 'px;width:' + w + 'px;background:' + col + '" '
                + 'title="' + esc(t.name) + ' (' + t.progress + '%) — 拖动移动 · 左右边缘拉伸 · 右侧圆点连线">';
            rows += '<div class="gantt-bar-handle left"></div>';
            rows += '<div class="gantt-bar-inner">';
            if (t.progress > 0) rows += '<div class="gantt-bar-progress" style="width:' + t.progress + '%"></div>';
            if (w > 50) rows += '<span class="gantt-bar-text">' + esc(t.name) + '</span>';
            rows += '</div>';
            rows += '<div class="gantt-bar-handle right"></div>';
            rows += '<div class="gantt-bar-depend" data-task-id="' + t.id + '"></div>';
            rows += '</div>';
        }
        rows += '</div></div>';
    });
    // Today line
    var todayLine = '';
    if (todayIdx >= 0) {
        todayLine = '<div class="gantt-today-line" style="left:' + (LABEL_W + todayIdx * colW + colW/2) + 'px"></div>';
    }

    // Dependency SVG overlay
    var depsSVG = '';
    var totalW = days.length * colW;
    var totalH = p.tasks.length * ROW_H;
    depsSVG = '<svg class="gantt-deps-svg" width="' + totalW + '" height="' + totalH + '" style="position:absolute;left:' + LABEL_W + 'px;top:0;pointer-events:none;z-index:0;overflow:visible">'
        + '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8A97A8"/></marker></defs>';
    var depsHitSVG = '<svg class="gantt-deps-hit-svg" width="' + totalW + '" height="' + totalH + '" style="position:absolute;left:' + LABEL_W + 'px;top:0;pointer-events:none;z-index:20;overflow:visible">';
    p.tasks.forEach(function(t) {
        if (!t.depends_on) return;
        var deps = String(t.depends_on).split(',').map(function(x){return parseInt(x,10);}).filter(Boolean);
        var tgt = taskPos[t.id];
        if (!tgt) return;
        deps.forEach(function(depId) {
            var src = taskPos[depId];
            if (!src) return;
            var x1 = src.left + src.width;
            var y1 = src.top + BAR_H/2;
            var x2 = tgt.left;
            var y2 = tgt.top + BAR_H/2;
            var gutterY = (y2 > y1)
                ? tgt.top - (ROW_H - BAR_H) / 2
                : tgt.top + BAR_H + (ROW_H - BAR_H) / 2;
            var midX = Math.max(x1 + 10, x2 - 14);
            var path = 'M' + x1 + ',' + y1
                     + ' L' + midX + ',' + y1
                     + ' L' + midX + ',' + gutterY
                     + ' L' + (x2 - 4) + ',' + gutterY
                     + ' L' + (x2 - 4) + ',' + y2;
            depsSVG += '<path class="gantt-dep-line" d="' + path + '" fill="none" stroke="#8A97A8" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#arrow)" opacity="0.5" data-from="' + depId + '" data-to="' + t.id + '"/>';
            depsHitSVG += '<path class="gantt-dep-hit" d="' + path + '" fill="none" stroke="transparent" stroke-width="14" data-from="' + depId + '" data-to="' + t.id + '" style="pointer-events:stroke;cursor:pointer"/>';
        });
    });
    depsSVG += '</svg>';
    depsHitSVG += '</svg>';

    // Stash context for drag handlers
    window._ganttCtx = {
        minD: minD, colW: colW, labelW: LABEL_W, rowH: ROW_H, projectId: p.id,
        totalDays: days.length, tasksById: {}
    };
    p.tasks.forEach(function(t){ window._ganttCtx.tasksById[t.id] = t; });

    return '<div class="gantt-wrap"><div class="gantt-header">'
        + '<span style="font-weight:600;color:var(--text2);font-size:13px">甘特图 <span style="color:var(--text3);font-weight:400;font-size:11px;margin-left:6px">拖动移动 · 边缘拉伸 · 圆点连依赖</span></span>'
        + '<div class="gantt-zoom">'
        + '<button class="' + (ganttZoom==='day'?'active':'') + '" onclick="ganttZoom=\'day\';reloadProject()">日</button>'
        + '<button class="' + (ganttZoom==='week'?'active':'') + '" onclick="ganttZoom=\'week\';reloadProject()">周</button>'
        + '<button class="' + (ganttZoom==='month'?'active':'') + '" onclick="ganttZoom=\'month\';reloadProject()">月</button>'
        + '</div></div>'
        + '<div class="gantt-canvas" id="gantt-canvas" style="position:relative">' + tl + '<div class="gantt-rows" id="gantt-rows" style="position:relative">'
        + depsSVG + todayLine + rows + depsHitSVG + '</div></div></div>';
}

// ═══════════════════════════════════════════════════════════
//  Gantt drag: move / resize / dependency — Apple-style
// ═══════════════════════════════════════════════════════════
var ganttDrag = null;

function ganttAttachHandlers() {
    var rows = document.getElementById('gantt-rows');
    if (!rows) return;
    // Use pointerdown for unified mouse+touch
    rows.querySelectorAll('.gantt-bar').forEach(function(bar) {
        bar.addEventListener('pointerdown', ganttBarDown);
    });
    rows.querySelectorAll('.gantt-bar-depend').forEach(function(anchor) {
        anchor.addEventListener('pointerdown', ganttDependDown);
    });
    // Click / hover on dependency lines → highlight + delete-with-undo
    rows.querySelectorAll('.gantt-dep-hit').forEach(function(hit) {
        var fromId = hit.getAttribute('data-from');
        var toId = hit.getAttribute('data-to');
        var visible = rows.querySelector('.gantt-dep-line[data-from="' + fromId + '"][data-to="' + toId + '"]');
        hit.addEventListener('mouseenter', function(){
            if (visible) { visible.setAttribute('stroke', '#E74C3C'); visible.setAttribute('stroke-width', '2'); visible.setAttribute('opacity', '1'); }
        });
        hit.addEventListener('mouseleave', function(){
            if (visible) { visible.setAttribute('stroke', '#8A97A8'); visible.setAttribute('stroke-width', '1.2'); visible.setAttribute('opacity', '0.5'); }
        });
        hit.addEventListener('click', function(ev){
            ev.preventDefault(); ev.stopPropagation();
            ganttRemoveDep(parseInt(fromId, 10), parseInt(toId, 10));
        });
    });
}

// Remove dependency "fromId → toId" with 5s undo toast
function ganttRemoveDep(fromId, toId) {
    var ctx = window._ganttCtx; if (!ctx) return;
    var task = ctx.tasksById[toId]; if (!task) return;
    var deps = String(task.depends_on || '').split(',').map(function(x){return parseInt(x,10);}).filter(Boolean);
    if (deps.indexOf(fromId) < 0) return;
    var remaining = deps.filter(function(x){ return x !== fromId; }).join(',');
    var original = deps.join(',');
    api('/api/tasks/' + toId, { depends_on: remaining }, function(){
        ganttUndoToast('已删除依赖', function(){
            api('/api/tasks/' + toId, { depends_on: original }, function(){ toast('已恢复依赖'); reloadProject(); }, 'PUT');
        });
        reloadProject();
    }, 'PUT');
}

// Apple-style undo toast: auto-dismiss in 5s, click "撤销" to revert
function ganttUndoToast(msg, onUndo) {
    var old = document.getElementById('gantt-undo-toast');
    if (old) old.remove();
    var el = document.createElement('div');
    el.id = 'gantt-undo-toast';
    el.style.cssText = 'position:fixed;bottom:32px;left:50%;transform:translateX(-50%) translateY(20px);' +
        'background:rgba(30,30,32,0.92);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);' +
        'color:#fff;padding:10px 14px 10px 18px;border-radius:14px;font-size:13px;' +
        'display:flex;align-items:center;gap:14px;z-index:9999;opacity:0;' +
        'box-shadow:0 8px 32px rgba(0,0,0,0.24);transition:opacity .25s,transform .35s cubic-bezier(0.34,1.56,0.64,1)';
    el.innerHTML = '<span>' + esc(msg) + '</span>' +
        '<button style="background:rgba(255,255,255,0.14);border:none;color:#6CB4FF;font-size:13px;font-weight:600;padding:5px 12px;border-radius:8px;cursor:pointer">撤销</button>';
    document.body.appendChild(el);
    requestAnimationFrame(function(){ el.style.opacity = '1'; el.style.transform = 'translateX(-50%) translateY(0)'; });
    var dismiss = function(){
        el.style.opacity = '0'; el.style.transform = 'translateX(-50%) translateY(20px)';
        setTimeout(function(){ if (el.parentNode) el.remove(); }, 300);
    };
    var timer = setTimeout(dismiss, 5000);
    el.querySelector('button').addEventListener('click', function(ev){
        ev.stopPropagation(); clearTimeout(timer); dismiss();
        if (typeof onUndo === 'function') onUndo();
    });
}

function fmtDate(d) {
    var y = d.getFullYear(), m = String(d.getMonth()+1).padStart(2,'0'), dd = String(d.getDate()).padStart(2,'0');
    return y + '-' + m + '-' + dd;
}

function dayOffsetToDate(minD, offset) {
    var d = new Date(minD); d.setDate(d.getDate() + offset); d.setHours(0,0,0,0);
    return d;
}

function ganttBarDown(ev) {
    if (ev.button === 2) return;
    ev.preventDefault(); ev.stopPropagation();
    var bar = ev.currentTarget;
    var tid = parseInt(bar.dataset.taskId, 10);
    var ctx = window._ganttCtx; if (!ctx) return;
    var rect = bar.getBoundingClientRect();
    var offsetX = ev.clientX - rect.left;
    var isLeft = offsetX < 8;
    var isRight = offsetX > rect.width - 8;
    var mode = isLeft ? 'resize-left' : (isRight ? 'resize-right' : 'move');
    ganttDrag = {
        type: mode, taskId: tid, startX: ev.clientX, bar: bar,
        origLeft: parseFloat(bar.style.left),
        origWidth: parseFloat(bar.style.width),
        origStart: bar.dataset.start, origEnd: bar.dataset.end,
        ctx: ctx, moved: false, isTouch: ev.pointerType === 'touch',
        longPressTimer: null
    };
    bar.setPointerCapture(ev.pointerId);

    // For touch: require small movement OR 200ms hold before activating (avoid accidental drag on tap)
    if (ganttDrag.isTouch) {
        ganttDrag.pending = true;
        ganttDrag.longPressTimer = setTimeout(function(){
            if (ganttDrag && ganttDrag.pending) {
                ganttDrag.pending = false;
                ganttActivate();
                if (navigator.vibrate) navigator.vibrate(10);
            }
        }, 200);
    } else {
        ganttActivate();
    }
    document.addEventListener('pointermove', ganttBarMove);
    document.addEventListener('pointerup', ganttBarUp, { once: true });
    document.addEventListener('pointercancel', ganttBarUp, { once: true });
}

function ganttActivate() {
    if (!ganttDrag) return;
    ganttDrag.active = true;
    ganttDrag.bar.classList.add('dragging');
    ganttShowTooltip(ganttDrag.origStart, ganttDrag.origEnd, ganttDrag.bar);
    document.body.style.cursor = ganttDrag.type === 'move' ? 'grabbing' : 'ew-resize';
    document.body.style.userSelect = 'none';
}

function ganttBarMove(ev) {
    if (!ganttDrag) return;
    var dx = ev.clientX - ganttDrag.startX;
    if (ganttDrag.pending && Math.abs(dx) > 4) {
        clearTimeout(ganttDrag.longPressTimer);
        ganttDrag.pending = false;
        ganttActivate();
    }
    if (!ganttDrag.active) return;
    ganttDrag.moved = true;
    var colW = ganttDrag.ctx.colW;
    var daysDelta = Math.round(dx / colW);
    if (ganttDrag.type === 'move') {
        var newLeft = ganttDrag.origLeft + daysDelta * colW;
        if (newLeft < 0) { daysDelta = -Math.floor(ganttDrag.origLeft / colW); newLeft = ganttDrag.origLeft + daysDelta * colW; }
        ganttDrag.bar.style.left = newLeft + 'px';
        ganttDrag.newStart = dayOffsetToDate(parseDate(ganttDrag.origStart), daysDelta);
        ganttDrag.newEnd = dayOffsetToDate(parseDate(ganttDrag.origEnd), daysDelta);
    } else if (ganttDrag.type === 'resize-left') {
        var newL = ganttDrag.origLeft + daysDelta * colW;
        var newW = ganttDrag.origWidth - daysDelta * colW;
        if (newW < colW - 4) { daysDelta = Math.round((ganttDrag.origWidth - (colW - 4)) / colW); newL = ganttDrag.origLeft + daysDelta * colW; newW = ganttDrag.origWidth - daysDelta * colW; }
        if (newL < 0) { daysDelta = -Math.floor(ganttDrag.origLeft / colW); newL = ganttDrag.origLeft + daysDelta * colW; newW = ganttDrag.origWidth - daysDelta * colW; }
        ganttDrag.bar.style.left = newL + 'px';
        ganttDrag.bar.style.width = newW + 'px';
        ganttDrag.newStart = dayOffsetToDate(parseDate(ganttDrag.origStart), daysDelta);
        ganttDrag.newEnd = parseDate(ganttDrag.origEnd);
    } else if (ganttDrag.type === 'resize-right') {
        var newW2 = ganttDrag.origWidth + daysDelta * colW;
        if (newW2 < colW - 4) { daysDelta = Math.round(((colW - 4) - ganttDrag.origWidth) / colW); newW2 = ganttDrag.origWidth + daysDelta * colW; }
        ganttDrag.bar.style.width = newW2 + 'px';
        ganttDrag.newStart = parseDate(ganttDrag.origStart);
        ganttDrag.newEnd = dayOffsetToDate(parseDate(ganttDrag.origEnd), daysDelta);
    }
    ganttShowTooltip(fmtDate(ganttDrag.newStart), fmtDate(ganttDrag.newEnd), ganttDrag.bar);
}

function ganttBarUp(ev) {
    document.removeEventListener('pointermove', ganttBarMove);
    if (!ganttDrag) return;
    if (ganttDrag.longPressTimer) clearTimeout(ganttDrag.longPressTimer);
    ganttHideTooltip();
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    if (ganttDrag.active) ganttDrag.bar.classList.remove('dragging');
    var d = ganttDrag;
    ganttDrag = null;
    if (!d.active || !d.moved || !d.newStart || !d.newEnd) return;
    var ns = fmtDate(d.newStart), ne = fmtDate(d.newEnd);
    if (ns === d.origStart && ne === d.origEnd) return;
    // Commit via API
    api('/api/tasks/' + d.taskId, { start_date: ns, end_date: ne }, function(r){
        if (r && r.success) {
            d.bar.dataset.start = ns; d.bar.dataset.end = ne;
            toast('日期已更新');
            reloadProject();
        } else {
            toast('更新失败', true);
            reloadProject();
        }
    }, 'PUT');
}

// ── Dependency draw ──
function ganttDependDown(ev) {
    ev.preventDefault(); ev.stopPropagation();
    var anchor = ev.currentTarget;
    var fromId = parseInt(anchor.dataset.taskId, 10);
    var ctx = window._ganttCtx; if (!ctx) return;
    var rows = document.getElementById('gantt-rows');
    var rowsRect = rows.getBoundingClientRect();
    var svg = rows.querySelector('.gantt-deps-svg');
    var line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    line.setAttribute('stroke', '#5A6A7A');
    line.setAttribute('stroke-width', '2');
    line.setAttribute('stroke-dasharray', '5,3');
    line.setAttribute('fill', 'none');
    line.setAttribute('marker-end', 'url(#arrow)');
    svg.appendChild(line);
    var anchorRect = anchor.getBoundingClientRect();
    var svgRect = svg.getBoundingClientRect();
    var startX = anchorRect.left + anchorRect.width/2 - svgRect.left;
    var startY = anchorRect.top + anchorRect.height/2 - svgRect.top;
    anchor.setPointerCapture(ev.pointerId);
    if (navigator.vibrate) navigator.vibrate(5);

    function update(e) {
        var cx = e.clientX - svgRect.left;
        var cy = e.clientY - svgRect.top;
        var mid = startX + Math.max(12, (cx - startX) / 2);
        line.setAttribute('d', 'M' + startX + ',' + startY + ' C' + mid + ',' + startY + ' ' + mid + ',' + cy + ' ' + cx + ',' + cy);
        // Highlight hovered target bar
        var el = document.elementFromPoint(e.clientX, e.clientY);
        document.querySelectorAll('.gantt-bar.depend-target').forEach(function(b){ b.classList.remove('depend-target'); });
        if (el) {
            var bar = el.closest && el.closest('.gantt-bar');
            if (bar && parseInt(bar.dataset.taskId,10) !== fromId) bar.classList.add('depend-target');
        }
    }
    function up(e) {
        document.removeEventListener('pointermove', update);
        line.remove();
        var hit = document.querySelector('.gantt-bar.depend-target');
        document.querySelectorAll('.gantt-bar.depend-target').forEach(function(b){ b.classList.remove('depend-target'); });
        if (!hit) return;
        var toId = parseInt(hit.dataset.taskId, 10);
        if (toId === fromId) return;
        // Prevent cycle: don't allow if fromId depends on toId directly already (simple check)
        var existing = String(ctx.tasksById[toId] && ctx.tasksById[toId].depends_on || '').split(',').map(function(x){return parseInt(x,10);}).filter(Boolean);
        if (existing.indexOf(fromId) >= 0) {
            var merged = existing.filter(function(x){return x !== fromId;}).join(',');
            api('/api/tasks/' + toId, { depends_on: merged }, function(){ toast('已移除依赖'); reloadProject(); }, 'PUT');
            return;
        }
        if (existing.indexOf(fromId) < 0) existing.push(fromId);
        api('/api/tasks/' + toId, { depends_on: existing.join(',') }, function(r){
            if (r && r.success) { toast('已连接依赖'); reloadProject(); }
            else { toast('连接失败', true); }
        }, 'PUT');
    }
    document.addEventListener('pointermove', update);
    document.addEventListener('pointerup', up, { once: true });
    document.addEventListener('pointercancel', up, { once: true });
}

// ── Tooltip ──
function ganttShowTooltip(start, end, bar) {
    var tip = document.getElementById('gantt-tip');
    if (!tip) {
        tip = document.createElement('div');
        tip.id = 'gantt-tip';
        tip.className = 'gantt-tip';
        document.body.appendChild(tip);
    }
    tip.innerHTML = '<b>' + start + '</b><span style="opacity:.5;margin:0 6px">→</span><b>' + end + '</b>';
    var r = bar.getBoundingClientRect();
    tip.style.left = (r.left + r.width / 2) + 'px';
    tip.style.top = (r.top - 36) + 'px';
    tip.classList.add('visible');
}
function ganttHideTooltip() {
    var tip = document.getElementById('gantt-tip');
    if (tip) tip.classList.remove('visible');
}

// ── Task Detail ──
function openTaskDetail(tid) {
    api('/api/tasks/' + tid, null, function(t) {
        var h = '<div class="modal-title">' + esc(t.name) + '</div>';
        // Phase + Priority + Progress
        h += '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px">'
            + '<span class="tag phase-tag" style="background:' + (PHASE_COLORS[t.phase]||'#95A3B3') + '">' + (PHASE_MAP[t.phase]||'') + '</span>'
            + priorityTag(t.priority)
            + '<span class="text-muted">' + (t.assignee_name || '未分配') + '</span></div>';
        // Progress slider
        h += '<div class="form-group"><label class="form-label">进度 ' + t.progress + '%</label>'
            + '<input type="range" min="0" max="100" step="5" value="' + t.progress + '" style="width:100%;accent-color:var(--main)" '
            + 'onchange="updateTask(' + t.id + ',{progress:parseInt(this.value)})">'
            + '<div class="progress-bar mt-8"><div class="progress-fill" style="width:' + t.progress + '%"></div></div></div>';
        // Dates
        h += '<div class="form-row"><div class="form-group"><label class="form-label">开始</label><input type="date" class="form-input" value="' + (t.start_date||'') + '" onchange="updateTask(' + t.id + ',{start_date:this.value})"></div>'
            + '<div class="form-group"><label class="form-label">截止</label><input type="date" class="form-input" value="' + (t.end_date||'') + '" onchange="updateTask(' + t.id + ',{end_date:this.value})"></div></div>';
        // Times (optional) — leave blank for all-day
        h += '<div class="form-row"><div class="form-group"><label class="form-label">开始时间 <span style="color:var(--text3);font-weight:400;font-size:11px">（可选）</span></label>'
            + '<input type="time" class="form-input" value="' + (t.start_time||'') + '" onchange="updateTask(' + t.id + ',{start_time:this.value})"></div>'
            + '<div class="form-group"><label class="form-label">截止时间 <span style="color:var(--text3);font-weight:400;font-size:11px">（可选）</span></label>'
            + '<input type="time" class="form-input" value="' + (t.end_time||'') + '" onchange="updateTask(' + t.id + ',{end_time:this.value})"></div></div>';
        // Description
        if (t.description) h += '<div class="text-muted mb-8">' + esc(t.description).replace(/\n/g,'<br>') + '</div>';
        h += '<div class="divider"></div>';

        // Subtasks
        h += '<div class="section-title" style="margin-top:8px">子任务</div>';
        t.subtasks.forEach(function(s) {
            h += '<div class="subtask-row">'
                + '<div class="subtask-cb ' + (s.is_done?'done':'') + '" onclick="toggleSubtask(' + s.id + ',' + (s.is_done?0:1) + ',' + t.id + ')"></div>'
                + '<span class="subtask-text ' + (s.is_done?'done':'') + '">' + esc(s.content) + '</span>'
                + '<button class="btn btn-sm btn-ghost" style="padding:2px 6px;font-size:11px" onclick="deleteSubtask(' + s.id + ',' + t.id + ')">x</button>'
                + '</div>';
        });
        h += '<div style="display:flex;gap:8px;margin-top:8px"><input type="text" class="form-input" id="new-subtask" placeholder="添加子任务..." style="flex:1">'
            + '<button class="btn btn-sm btn-primary" onclick="addSubtask(' + t.id + ')">添加</button></div>';

        // Files
        h += '<div class="divider"></div><div class="section-title">附件</div>';
        h += '<div class="file-grid">';
        t.files.forEach(function(f) {
            var ext = f.original_name.split('.').pop().toLowerCase();
            var isImg = ['jpg','jpeg','png','gif','webp'].indexOf(ext) >= 0;
            h += '<div class="file-thumb" onclick="window.open(B+\'/api/uploads/' + t.id + '/' + f.filename + '\')">';
            if (isImg) h += '<img src="' + B + '/api/uploads/' + t.id + '/' + f.filename + '" loading="lazy">';
            else h += '<div class="file-thumb-icon"><span class="ext">' + ext.toUpperCase() + '</span><span>' + esc(f.original_name).slice(0,8) + '</span></div>';
            h += '<button class="file-del" onclick="event.stopPropagation();deleteFile(' + f.id + ',' + t.id + ')">x</button></div>';
        });
        h += '</div>';
        h += '<div style="margin-top:8px"><label class="btn btn-sm btn-ghost" style="cursor:pointer">'
            + '<input type="file" style="display:none" onchange="uploadFile(' + t.id + ',this)">'
            + '上传文件</label></div>';

        // Comments
        h += '<div class="divider"></div><div class="section-title">讨论</div>';
        t.comments.forEach(function(c) {
            var isMine = ME && c.user_id === ME.id;
            h += '<div class="comment-item">'
                + '<div class="comment-avatar">' + (c.user_name||'?').charAt(0) + '</div>'
                + '<div class="comment-body"><span class="comment-name">' + esc(c.user_name||'') + '</span>'
                + '<span class="comment-time">' + timeago(c.created_at) + '</span>'
                + (isMine ? '<button class="comment-del-btn" onclick="deleteComment(' + c.id + ',' + t.id + ')" title="删除">&#x1F5D1;</button>' : '')
                + '<div class="comment-text">' + esc(c.content).replace(/\n/g,'<br>') + '</div></div></div>';
        });
        h += '<div class="comment-input-wrap"><textarea class="form-input comment-textarea" id="new-comment" placeholder="说点什么..." rows="1" oninput="this.style.height=\'auto\';this.style.height=this.scrollHeight+\'px\'"></textarea>'
            + '<button class="btn btn-sm btn-primary" onclick="addComment(' + t.id + ')">发送</button></div>';

        // Actions
        var isDone = t.progress >= 100;
        h += '<div class="divider"></div><div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">';
        if (isDone) {
            h += '<button class="btn btn-sm btn-reopen" onclick="updateTask(' + t.id + ',{progress:0});closeModal()">↩ 重新开启</button>';
        } else {
            h += '<button class="btn btn-sm btn-complete" onclick="updateTask(' + t.id + ',{progress:100});closeModal()">✓ 标记完成</button>';
        }
        h += '<button class="btn btn-sm btn-ghost" onclick="openTaskForm(' + t.id + ')">编辑任务</button>'
            + '<button class="btn btn-sm btn-danger" onclick="if(confirm(\'确定删除?\'))deleteTask(' + t.id + ')">删除</button>'
            + '</div>';
        openModal(h);
    }, 'GET');
}

function updateTask(tid, data) {
    api('/api/tasks/' + tid, data, function(){ reloadProject(); }, 'PUT');
}
function toggleSubtask(sid, val, tid) {
    api('/api/subtasks/' + sid, {is_done:val}, function(){ openTaskDetail(tid); }, 'PUT');
}
function deleteSubtask(sid, tid) {
    api('/api/subtasks/' + sid, {}, function(){ openTaskDetail(tid); }, 'DELETE');
}
function addSubtask(tid) {
    var inp = document.getElementById('new-subtask');
    if (!inp.value.trim()) return;
    api('/api/tasks/' + tid + '/subtasks', {content:inp.value.trim()}, function(){ openTaskDetail(tid); });
}
function addComment(tid) {
    var inp = document.getElementById('new-comment');
    if (!inp.value.trim()) return;
    api('/api/tasks/' + tid + '/comments', {content:inp.value.trim()}, function(){ openTaskDetail(tid); });
}
function deleteComment(cid, tid) {
    confirmDialog('删除这条评论?', function() {
        api('/api/comments/' + cid, {}, function(){ openTaskDetail(tid); }, 'DELETE');
    });
}
function uploadFile(tid, input) {
    if (!input.files.length) return;
    var fd = new FormData();
    fd.append('file', input.files[0]);
    api('/api/tasks/' + tid + '/files', fd, function(){ openTaskDetail(tid); toast('文件已上传'); });
}
function deleteFile(fid, tid) {
    confirmDialog('删除此文件?', function() {
        api('/api/files/' + fid, {}, function(){ openTaskDetail(tid); }, 'DELETE');
    });
}
function uploadProjectFile(pid, input) {
    if (!input.files.length) return;
    var fd = new FormData();
    fd.append('file', input.files[0]);
    api('/api/projects/' + pid + '/files', fd, function(){ reloadProject(); toast('文件已上传'); });
}
function deleteProjectFile(fid) {
    confirmDialog('删除此文件?', function() {
        api('/api/project-files/' + fid, {}, function(){ reloadProject(); }, 'DELETE');
    });
}
function deleteTask(tid) {
    api('/api/tasks/' + tid, {}, function(){ closeModal(); reloadProject(); }, 'DELETE');
}

// ── Org-tree based user visibility selector ──
function loadOrgForVis(cb) {
    fetch(B + '/api/org', { credentials: 'same-origin' })
        .then(function(r){ return r.json(); })
        .then(function(d) {
            if (d && d.id) { cb(d); }
            else if (d && d.org) { cb(d.org); }
            else { document.getElementById('user-select-container').innerHTML = '<div style="color:var(--muted);font-size:13px">暂无组织架构数据</div>'; }
        })
        .catch(function() { document.getElementById('user-select-container').innerHTML = '<div style="color:var(--muted);font-size:13px">加载失败</div>'; });
}
function renderVisTree(node, sel, depth) {
    if (!node) return '';
    depth = depth || 0;
    var hasChildren = (node.children && node.children.length > 0);
    var hasMembers = (node.members && node.members.length > 0);
    var hasContent = hasChildren || hasMembers;
    var h = '<div class="vis-dept">';
    // Department header row
    h += '<div class="vis-dept-row">';
    if (hasContent) {
        h += '<span class="vis-toggle open" onclick="visToggle(this)">▶</span>';
    }
    if (hasMembers) {
        h += '<input type="checkbox" class="vis-dept-check" onchange="visDeptToggle(this)" title="全选/取消本部门">';
    }
    h += '<span>' + esc(node.name) + '</span>';
    if (hasMembers) h += '<span style="color:var(--muted);font-size:11px;margin-left:2px">(' + node.members.length + ')</span>';
    h += '</div>';
    // Members + children container
    if (hasContent) {
        h += '<div class="vis-members">';
        // Members of this node
        if (hasMembers) {
            node.members.forEach(function(m) {
                if (!m.username) return;
                var checked = sel.indexOf(m.username) >= 0;
                h += '<label class="vis-person"><input type="checkbox" class="user-vis-check" value="' + esc(m.username) + '"' + (checked ? ' checked' : '') + ' onchange="visPersonChange(this)"> ' + esc(m.name) + '</label>';
            });
        }
        // Child departments
        if (hasChildren) {
            h += '<div class="vis-children">';
            node.children.forEach(function(c) { h += renderVisTree(c, sel, depth + 1); });
            h += '</div>';
        }
        h += '</div>';
    }
    h += '</div>';
    return h;
}
function visToggle(el) {
    var members = el.closest('.vis-dept').querySelector('.vis-members');
    if (members) { members.classList.toggle('collapsed'); el.classList.toggle('open'); }
}
function visDeptToggle(el) {
    var dept = el.closest('.vis-dept').querySelector('.vis-members');
    if (!dept) return;
    var checks = dept.querySelectorAll('.user-vis-check');
    var allChecked = Array.prototype.every.call(checks, function(c){ return c.checked; });
    checks.forEach(function(c){ c.checked = !allChecked; });
    el.checked = !allChecked;
}
function visPersonChange(el) {
    // Update parent dept checkbox state
    var dept = el.closest('.vis-dept');
    if (!dept) return;
    var deptCheck = dept.querySelector('.vis-dept-check');
    if (!deptCheck) return;
    var members = dept.querySelector('.vis-members');
    var checks = members.querySelectorAll(':scope > .vis-person > .user-vis-check');
    var allChecked = checks.length > 0 && Array.prototype.every.call(checks, function(c){ return c.checked; });
    deptCheck.checked = allChecked;
}
function getSelectedVisibleUsers() {
    var users = [];
    document.querySelectorAll('#user-select-container .user-vis-check:checked').forEach(function(cb) {
        users.push(cb.value);
    });
    return users;
}

// ── Forms ──
function openProjectForm(pid) {
    var p = pid && currentProject && currentProject.id === pid ? currentProject : null;
    var h = '<div class="modal-title">' + (p ? '编辑项目' : '新建项目') + '</div>';
    h += '<div class="form-group"><label class="form-label">项目名称</label><input type="text" class="form-input" id="pf-name" value="' + (p?esc(p.name):'') + '" placeholder="输入项目名称"></div>';
    h += '<div class="form-group"><label class="form-label">描述</label><textarea class="form-input" id="pf-desc" placeholder="简要描述...">' + (p?esc(p.description||''):'') + '</textarea></div>';
    h += '<div class="form-row"><div class="form-group"><label class="form-label">开始日期</label><input type="date" class="form-input" id="pf-start" value="' + (p?p.start_date||'':new Date().toISOString().slice(0,10)) + '"></div>'
        + '<div class="form-group"><label class="form-label">截止日期</label><input type="date" class="form-input" id="pf-deadline" value="' + (p?p.deadline||'':'') + '"></div></div>';
    if (p) {
        h += '<div class="form-group"><label class="form-label">状态</label><select class="form-input" id="pf-status">';
        PROJECT_STATUS.forEach(function(s){
            h += '<option value="' + s[0] + '" ' + (p.status===s[0]?'selected':'') + '>' + s[1] + '</option>';
        });
        h += '</select></div>';
    }
    h += '<div class="form-group"><label class="form-label">颜色</label><div class="color-picker" id="pf-colors">';
    PROJECT_COLORS.forEach(function(c){
        h += '<div class="color-dot ' + ((p?p.color:'#95A3B3')===c?'active':'') + '" style="background:' + c + '" onclick="pickColor(this,\'' + c + '\')"></div>';
    });
    h += '</div><input type="hidden" id="pf-color" value="' + (p?p.color:'#95A3B3') + '"></div>';
    h += '<div class="form-group"><label class="form-label">可见范围 <span style="color:var(--muted);font-size:12px">(不选则仅创建人与任务相关人可见)</span></label>';
    h += '<div class="vis-tree" id="user-select-container"><div style="color:var(--muted);font-size:13px">加载中...</div></div></div>';
    h += '<div style="display:flex;gap:8px;margin-top:16px">'
        + '<button class="btn btn-primary btn-block" onclick="saveProject(' + (pid||'null') + ')">保存</button>';
    if (p) h += '<button class="btn btn-danger" onclick="if(confirm(\'确定删除项目?\'))deleteProject(' + p.id + ')">删除项目</button>';
    h += '</div>';
    openModal(h);
    loadOrgForVis(function(org) {
        var sel = p && p.visible_to ? p.visible_to : [];
        document.getElementById('user-select-container').innerHTML = renderVisTree(org, sel, 0);
    });
}
function pickColor(el, c) {
    document.querySelectorAll('#pf-colors .color-dot').forEach(function(d){ d.classList.remove('active'); });
    el.classList.add('active');
    document.getElementById('pf-color').value = c;
}
function saveProject(pid) {
    var data = {
        name: document.getElementById('pf-name').value,
        description: document.getElementById('pf-desc').value,
        start_date: document.getElementById('pf-start').value,
        deadline: document.getElementById('pf-deadline').value,
        color: document.getElementById('pf-color').value,
        visible_to: getSelectedVisibleUsers(),
    };
    var stEl = document.getElementById('pf-status');
    if (stEl) data.status = stEl.value;
    if (pid) {
        api('/api/projects/' + pid, data, function(){ closeModal(); reloadProject(); toast('已更新'); }, 'PUT');
    } else {
        api('/api/projects', data, function(d){ closeModal(); openProject(d.id); toast('项目已创建'); });
    }
}
function deleteProject(pid) {
    api('/api/projects/' + pid, {}, function(){ closeModal(); switchTab('projects'); toast('项目已删除'); }, 'DELETE');
}

function openTaskForm(tid) {
    var t = null;
    if (tid && currentProject) {
        currentProject.tasks.forEach(function(x){ if(x.id===tid) t=x; });
    }
    var h = '<div class="modal-title">' + (t ? '编辑任务' : '新建任务') + '</div>';
    h += '<div class="form-group"><label class="form-label">任务名称</label><input type="text" class="form-input" id="tf-name" value="' + (t?esc(t.name):'') + '" placeholder="输入任务名称"></div>';
    h += '<div class="form-group"><label class="form-label">描述</label><textarea class="form-input" id="tf-desc" placeholder="任务详情...">' + (t?esc(t.description||''):'') + '</textarea></div>';
    h += '<div class="form-row"><div class="form-group"><label class="form-label">开始</label><input type="date" class="form-input" id="tf-start" value="' + (t?t.start_date||'':new Date().toISOString().slice(0,10)) + '"></div>'
        + '<div class="form-group"><label class="form-label">截止</label><input type="date" class="form-input" id="tf-end" value="' + (t?t.end_date||'':'') + '"></div></div>';
    h += '<div class="form-row"><div class="form-group"><label class="form-label">开始时间 <span style="color:var(--text3);font-weight:400;font-size:11px">（可选·24h）</span></label>'
        + '<input type="time" class="form-input" id="tf-start-time" value="' + (t?t.start_time||'':'') + '"></div>'
        + '<div class="form-group"><label class="form-label">截止时间 <span style="color:var(--text3);font-weight:400;font-size:11px">（可选·24h）</span></label>'
        + '<input type="time" class="form-input" id="tf-end-time" value="' + (t?t.end_time||'':'') + '"></div></div>';
    h += '<div class="form-row"><div class="form-group"><label class="form-label">阶段</label><select class="form-input" id="tf-phase" onchange="onPhaseSelectChange(this)">';
    var _phaseKeys = PHASES.map(function(p){ return p[0]; });
    var _curPhase = t && t.phase ? t.phase : '';
    if (_curPhase && _phaseKeys.indexOf(_curPhase) < 0) {
        h += '<option value="' + esc(_curPhase) + '" selected>' + esc(_curPhase) + ' (自定义)</option>';
    }
    PHASES.forEach(function(p){ h += '<option value="' + p[0] + '" ' + (t&&t.phase===p[0]?'selected':'') +'>' + p[1] + '</option>'; });
    h += '<option value="__custom__" style="font-style:italic;color:var(--accent,#C89D9F)">+ 自定义阶段…</option>';
    h += '</select></div><div class="form-group"><label class="form-label">优先级</label><select class="form-input" id="tf-priority">';
    PRIORITIES.forEach(function(p){ h += '<option value="' + p[0] + '" ' + (t&&t.priority===p[0]?'selected':'') + '>' + p[1] + '</option>'; });
    h += '</select></div></div>';
    h += '<div class="form-group"><label class="form-label">主负责人</label>'
        + '<div id="tf-assignee-wrap" class="chip-field"></div></div>';
    h += '<div class="form-group"><label class="form-label">协作者 <span style="color:var(--text3);font-weight:400;font-size:11px">（可选）</span></label>'
        + '<div id="tf-collab-wrap" class="chip-field"></div></div>';
    if (t) {
        h += '<div class="form-group"><label class="form-label">进度 <span id="tf-prog-val">' + t.progress + '</span>%</label>'
            + '<input type="range" min="0" max="100" step="5" value="' + t.progress + '" id="tf-progress" style="width:100%;accent-color:var(--main)" '
            + 'oninput="document.getElementById(\'tf-prog-val\').textContent=this.value"></div>';
    }
    h += '<button class="btn btn-primary btn-block" onclick="saveTask(' + (tid||'null') + ')" style="margin-top:16px">保存</button>';
    openModal(h);
    // Initialize chip pickers after DOM is in
    setTimeout(function(){
        initAssigneeChip(t);
        initCollabChips(t);
    }, 0);
}
function saveTask(tid) {
    var assigneeId = window._tfAssigneeId || '';
    var assigneeName = '';
    if (assigneeId) {
        var _u = USERS.filter(function(u){ return u.id === assigneeId; })[0];
        if (_u) assigneeName = _u.display_name;
    }
    var collabIds = (window._tfCollabIds || []).join(',');
    var data = {
        name: document.getElementById('tf-name').value,
        description: document.getElementById('tf-desc').value,
        start_date: document.getElementById('tf-start').value,
        end_date: document.getElementById('tf-end').value,
        start_time: (document.getElementById('tf-start-time')||{}).value || '',
        end_time: (document.getElementById('tf-end-time')||{}).value || '',
        phase: (function(){ var v = document.getElementById('tf-phase').value; return v === '__custom__' ? 'concept' : v; })(),
        priority: document.getElementById('tf-priority').value,
        assignee_id: assigneeId,
        assignee_name: assigneeName,
        collaborator_ids: collabIds,
    };
    var progEl = document.getElementById('tf-progress');
    if (progEl) data.progress = parseInt(progEl.value);
    if (tid) {
        api('/api/tasks/' + tid, data, function(){ closeModal(); reloadProject(); toast('任务已更新'); }, 'PUT');
    } else {
        if (!currentProject) return;
        api('/api/projects/' + currentProject.id + '/tasks', data, function(){ closeModal(); reloadProject(); toast('任务已创建'); });
    }
}

// ── Custom phase handler ──
function onPhaseSelectChange(sel) {
    if (sel.value !== '__custom__') return;
    var prev = sel.getAttribute('data-prev') || (sel.options.length > 1 ? sel.options[0].value : '');
    var name = (window.prompt('输入自定义阶段名称（最多 12 字）：', '') || '').trim();
    if (!name) { sel.value = prev; return; }
    if (name.length > 12) name = name.slice(0, 12);
    if (name === '__custom__') { sel.value = prev; return; }
    // If already exists as option, just select it
    for (var i = 0; i < sel.options.length; i++) {
        if (sel.options[i].value === name) { sel.value = name; sel.setAttribute('data-prev', name); return; }
    }
    // Insert new option before the __custom__ entry
    var opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name + ' (自定义)';
    var customOpt = null;
    for (var j = 0; j < sel.options.length; j++) {
        if (sel.options[j].value === '__custom__') { customOpt = sel.options[j]; break; }
    }
    if (customOpt) sel.insertBefore(opt, customOpt); else sel.appendChild(opt);
    sel.value = name;
    sel.setAttribute('data-prev', name);
}

// ── Apple-style assignee chip picker ──
function _userInitial(name){ return (name || '?').trim().charAt(0).toUpperCase(); }
function _userColor(id){
    var s = String(id||'?'); var h = 0;
    for (var i = 0; i < s.length; i++) h = ((h*31) + s.charCodeAt(i)) >>> 0;
    return 'hsl(' + (h % 360) + ', 48%, 60%)';
}
function _chipHTML(user, removable){
    var bg = _userColor(user.id);
    return '<span class="chip chip-user" data-user-id="' + esc(user.id) + '" style="background:' + bg + '1f;color:#2E3338">'
        + '<span class="chip-avatar" style="background:' + bg + '">' + esc(_userInitial(user.display_name)) + '</span>'
        + '<span class="chip-name">' + esc(user.display_name) + '</span>'
        + (removable ? '<span class="chip-x" title="移除">×</span>' : '<span class="chip-caret">⌄</span>')
        + '</span>';
}
function _emptyAssigneeChipHTML(){
    return '<span class="chip chip-empty" title="选择主负责人"><span class="chip-avatar chip-avatar-empty">+</span><span class="chip-name">未分配</span></span>';
}
function _addChipHTML(){
    return '<span class="chip chip-add" title="添加协作者"><span class="chip-avatar chip-avatar-empty">+</span><span class="chip-name">添加</span></span>';
}
function initAssigneeChip(task){
    window._tfAssigneeId = (task && task.assignee_id) ? task.assignee_id : '';
    renderAssigneeChip();
    var wrap = document.getElementById('tf-assignee-wrap');
    if (!wrap) return;
    wrap.addEventListener('click', function(ev){
        ev.stopPropagation();
        openUserPicker(wrap, function(uid){
            window._tfAssigneeId = uid;
            renderAssigneeChip();
        }, { current: window._tfAssigneeId, allowUnassign: true });
    });
}
function renderAssigneeChip(){
    var wrap = document.getElementById('tf-assignee-wrap');
    if (!wrap) return;
    var uid = window._tfAssigneeId;
    if (!uid) { wrap.innerHTML = _emptyAssigneeChipHTML(); return; }
    var u = USERS.filter(function(x){ return x.id === uid; })[0];
    if (!u) { wrap.innerHTML = _emptyAssigneeChipHTML(); window._tfAssigneeId = ''; return; }
    wrap.innerHTML = _chipHTML(u, false);
}
function initCollabChips(task){
    var ids = [];
    if (task && task.collaborator_ids) {
        ids = String(task.collaborator_ids).split(',').map(function(x){return x.trim();}).filter(Boolean);
    }
    window._tfCollabIds = ids;
    renderCollabChips();
    var wrap = document.getElementById('tf-collab-wrap');
    if (!wrap) return;
    wrap.addEventListener('click', function(ev){
        var x = ev.target.closest('.chip-x');
        if (x) {
            var chip = x.closest('.chip-user'); if (!chip) return;
            var rid = chip.getAttribute('data-user-id');
            window._tfCollabIds = window._tfCollabIds.filter(function(i){ return i !== rid; });
            chip.style.transition = 'transform .2s cubic-bezier(0.34,1.56,0.64,1),opacity .2s';
            chip.style.transform = 'scale(0.6)'; chip.style.opacity = '0';
            setTimeout(renderCollabChips, 180);
            return;
        }
        var add = ev.target.closest('.chip-add');
        if (add) {
            ev.stopPropagation();
            openUserPicker(wrap, function(uid){
                if (!uid) return;
                if (window._tfCollabIds.indexOf(uid) >= 0) return;
                if (uid === window._tfAssigneeId) { toast('已是主负责人'); return; }
                window._tfCollabIds.push(uid);
                renderCollabChips();
            }, { exclude: [window._tfAssigneeId].concat(window._tfCollabIds) });
        }
    });
}
function renderCollabChips(){
    var wrap = document.getElementById('tf-collab-wrap');
    if (!wrap) return;
    var html = '';
    (window._tfCollabIds || []).forEach(function(uid){
        var u = USERS.filter(function(x){ return x.id === uid; })[0];
        if (u) html += _chipHTML(u, true);
    });
    html += _addChipHTML();
    wrap.innerHTML = html;
}
function openUserPicker(anchor, onPick, opts){
    opts = opts || {};
    closeUserPicker();
    var rect = anchor.getBoundingClientRect();
    var pop = document.createElement('div');
    pop.id = 'user-picker-pop';
    pop.className = 'user-picker';
    pop.style.cssText = 'position:fixed;z-index:9998;min-width:240px;max-width:280px;' +
        'background:rgba(255,255,255,0.82);backdrop-filter:saturate(180%) blur(28px);-webkit-backdrop-filter:saturate(180%) blur(28px);' +
        'border:1px solid rgba(0,0,0,0.08);border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,0.18);' +
        'padding:8px;opacity:0;transform:translateY(-6px) scale(0.98);transition:opacity .18s,transform .22s cubic-bezier(0.34,1.56,0.64,1)';
    var maxTop = window.innerHeight - 360;
    var top = Math.min(rect.bottom + 6, maxTop);
    pop.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - 320)) + 'px';
    pop.style.top = top + 'px';
    pop.innerHTML = '<input type="text" id="up-q" placeholder="搜索成员…" style="width:100%;padding:8px 10px;border:none;border-radius:8px;background:rgba(0,0,0,0.05);font-size:13px;outline:none;margin-bottom:6px" autofocus>'
        + '<div id="up-list" style="max-height:280px;overflow-y:auto"></div>';
    document.body.appendChild(pop);
    requestAnimationFrame(function(){ pop.style.opacity = '1'; pop.style.transform = 'translateY(0) scale(1)'; });
    var q = pop.querySelector('#up-q');
    var list = pop.querySelector('#up-list');
    var exclude = (opts.exclude || []).filter(Boolean);
    function render(filter){
        var ff = (filter||'').toLowerCase();
        var html = '';
        if (opts.allowUnassign && !ff) {
            html += '<div class="up-row" data-uid="" style="padding:8px 10px;border-radius:8px;cursor:pointer;font-size:13px;color:var(--text2)">未分配</div>';
        }
        USERS.filter(function(u){
            if (exclude.indexOf(u.id) >= 0 && u.id !== opts.current) return false;
            if (!ff) return true;
            return (u.display_name||'').toLowerCase().indexOf(ff) >= 0
                || (u.username||'').toLowerCase().indexOf(ff) >= 0;
        }).forEach(function(u){
            var sel = (u.id === opts.current) ? ' background:rgba(0,122,255,0.08);' : '';
            html += '<div class="up-row" data-uid="' + esc(u.id) + '" style="display:flex;align-items:center;gap:10px;padding:6px 10px;border-radius:8px;cursor:pointer;font-size:13px;' + sel + '">'
                + '<span style="width:24px;height:24px;border-radius:50%;background:' + _userColor(u.id) + ';color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700">' + esc(_userInitial(u.display_name)) + '</span>'
                + '<span>' + esc(u.display_name) + '</span>'
                + '</div>';
        });
        if (!html) html = '<div style="padding:10px;color:var(--text3);font-size:12px;text-align:center">无匹配成员</div>';
        list.innerHTML = html;
    }
    render('');
    q.addEventListener('input', function(){ render(q.value); });
    q.focus();
    list.addEventListener('mouseover', function(ev){
        var row = ev.target.closest('.up-row'); if (!row) return;
        list.querySelectorAll('.up-row').forEach(function(r){ if (r !== row) r.style.background = ''; });
        if (row.getAttribute('data-uid') !== opts.current) row.style.background = 'rgba(0,0,0,0.05)';
    });
    list.addEventListener('click', function(ev){
        var row = ev.target.closest('.up-row'); if (!row) return;
        onPick(row.getAttribute('data-uid') || '');
        closeUserPicker();
    });
    setTimeout(function(){
        document.addEventListener('click', _userPickerOutside, { once: true });
    }, 10);
}
function _userPickerOutside(ev){
    var pop = document.getElementById('user-picker-pop');
    if (pop && !pop.contains(ev.target)) closeUserPicker();
    else document.addEventListener('click', _userPickerOutside, { once: true });
}
function closeUserPicker(){
    var pop = document.getElementById('user-picker-pop');
    if (!pop) return;
    pop.style.opacity = '0'; pop.style.transform = 'translateY(-6px) scale(0.98)';
    setTimeout(function(){ if (pop.parentNode) pop.remove(); }, 200);
}

// ── Calendar ──
function loadCalendar() {
    api('/api/calendar?year=' + calYear + '&month=' + calMonth, null, function(data) {
        renderCalendar(data.events, data.deadlines);
    }, 'GET');
}
function renderCalendar(events, deadlines) {
    var months = ['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月'];
    var html = '<div class="cal-nav">'
        + '<button class="cal-arrow" onclick="calMonth--;if(calMonth<1){calMonth=12;calYear--}loadCalendar()">&lt;</button>'
        + '<span class="cal-month-title">' + calYear + '年 ' + months[calMonth-1] + '</span>'
        + '<button class="cal-arrow" onclick="calMonth++;if(calMonth>12){calMonth=1;calYear++}loadCalendar()">&gt;</button>'
        + '</div>';
    html += '<div class="cal-grid">';
    ['日','一','二','三','四','五','六'].forEach(function(d){ html += '<div class="cal-head">' + d + '</div>'; });
    var firstDay = new Date(calYear, calMonth-1, 1).getDay();
    var daysInMonth = new Date(calYear, calMonth, 0).getDate();
    var todayStr = new Date().toISOString().slice(0,10);
    // Build event map
    var evMap = {};
    events.forEach(function(e){
        if(!evMap[e.event_date]) evMap[e.event_date]=[];
        evMap[e.event_date].push(e);
    });
    deadlines.forEach(function(d){
        var dt = d.end_date;
        if(!evMap[dt]) evMap[dt]=[];
        evMap[dt].push({title:d.name, color:d.project_color||'#E85D5D', event_type:'deadline'});
    });
    // Previous month padding
    var prevDays = new Date(calYear, calMonth-1, 0).getDate();
    for (var i = firstDay-1; i >= 0; i--) {
        html += '<div class="cal-day other-month"><div class="cal-day-num">' + (prevDays-i) + '</div></div>';
    }
    for (var d = 1; d <= daysInMonth; d++) {
        var ds = calYear + '-' + String(calMonth).padStart(2,'0') + '-' + String(d).padStart(2,'0');
        var isToday = ds === todayStr;
        html += '<div class="cal-day' + (isToday?' today':'') + '" onclick="openCalDay(\'' + ds + '\')">'
            + '<div class="cal-day-num">' + d + '</div>';
        if (evMap[ds]) {
            evMap[ds].slice(0,2).forEach(function(e){
                html += '<div class="cal-event-mini" style="background:' + (e.color||'var(--main)') + '">' + esc(e.title).slice(0,6) + '</div>';
            });
            if (evMap[ds].length > 2) html += '<div style="font-size:9px;color:var(--text3);text-align:center">+' + (evMap[ds].length-2) + '</div>';
        }
        html += '</div>';
    }
    // Next month padding
    var totalCells = firstDay + daysInMonth;
    var rem = totalCells % 7;
    if (rem > 0) for (var i = 1; i <= 7-rem; i++) {
        html += '<div class="cal-day other-month"><div class="cal-day-num">' + i + '</div></div>';
    }
    html += '</div>';
    document.getElementById('calendar-container').innerHTML = html;
}
function openCalDay(ds) {
    api('/api/calendar?year=' + ds.slice(0,4) + '&month=' + parseInt(ds.slice(5,7)), null, function(data) {
        var dayEvents = data.events.filter(function(e){ return e.event_date === ds; });
        var dayDeadlines = data.deadlines.filter(function(d){ return d.end_date === ds; });
        var h = '<div class="modal-title">' + ds + '</div>';
        if (!dayEvents.length && !dayDeadlines.length) {
            h += '<div class="empty"><div class="empty-text">这天没有安排</div></div>';
        }
        dayDeadlines.forEach(function(d){
            h += '<div class="task-item" onclick="closeModal();openProject(' + (d.project_id||0) + ')" style="border-left:3px solid #E85D5D">'
                + '<div class="task-info"><div class="task-name" style="color:#E85D5D">截止: ' + esc(d.name) + '</div>'
                + '<div class="task-sub"><span>' + esc(d.project_name||'') + '</span></div></div></div>';
        });
        dayEvents.forEach(function(e){
            h += '<div style="padding:10px;border-radius:8px;border-left:3px solid ' + (e.color||'var(--main)') + ';margin-bottom:8px;background:var(--bg)">'
                + '<div style="font-weight:600">' + esc(e.title) + '</div>'
                + (e.start_time ? '<div class="text-muted">' + e.start_time + (e.end_time?' ~ '+e.end_time:'') + '</div>' : '')
                + (e.description ? '<div class="text-muted mt-8">' + esc(e.description) + '</div>' : '')
                + '<button class="btn btn-sm btn-ghost mt-8" onclick="deleteCalEvent(' + e.id + ')">删除</button>'
                + '</div>';
        });
        h += '<div class="divider"></div><button class="btn btn-primary btn-block" onclick="closeModal();openCalEventForm(\'' + ds + '\')">添加日程</button>';
        openModal(h);
    }, 'GET');
}
function openCalEventForm(ds) {
    var h = '<div class="modal-title">新日程</div>';
    h += '<div class="form-group"><label class="form-label">标题</label><input type="text" class="form-input" id="ce-title" placeholder="会议/提醒..."></div>';
    h += '<div class="form-group"><label class="form-label">日期</label><input type="date" class="form-input" id="ce-date" value="' + (ds||new Date().toISOString().slice(0,10)) + '"></div>';
    h += '<div class="form-row"><div class="form-group"><label class="form-label">开始时间</label><input type="time" class="form-input" id="ce-start"></div>'
        + '<div class="form-group"><label class="form-label">结束时间</label><input type="time" class="form-input" id="ce-end"></div></div>';
    h += '<div class="form-group"><label class="form-label">备注</label><textarea class="form-input" id="ce-desc" placeholder="可选" rows="2"></textarea></div>';
    h += '<button class="btn btn-primary btn-block" onclick="saveCalEvent()">保存</button>';
    openModal(h);
}
function saveCalEvent() {
    api('/api/calendar', {
        title: document.getElementById('ce-title').value,
        event_date: document.getElementById('ce-date').value,
        start_time: document.getElementById('ce-start').value,
        end_time: document.getElementById('ce-end').value,
        description: document.getElementById('ce-desc').value,
    }, function(){ closeModal(); loadCalendar(); toast('日程已添加'); });
}
function deleteCalEvent(eid) {
    api('/api/calendar/' + eid, {}, function(){ closeModal(); loadCalendar(); toast('已删除'); }, 'DELETE');
}

// ── Export: modal with 4 options (list/gantt × download-html/share-image) ──
function exportDoc() {
    if (!currentProject) { toast('请先打开一个项目', true); return; }
    var css = 'style="border:1px solid #D8D5D0;border-radius:12px;background:#fff;padding:18px 12px;text-align:center;cursor:pointer;transition:all .15s;display:block;width:100%"';
    var iconCSS = 'font-family:-apple-system,SF Mono,Menlo,monospace;font-size:17px;font-weight:600;color:#5A6A7A;letter-spacing:-0.5px;display:inline-block;padding:4px 10px;border:1.5px solid #C89D9F;border-radius:6px;margin-bottom:10px;min-width:44px';
    function opt(view, mode, iconText, title, sub) {
        return '<button class="export-opt-btn" onclick="doExport(\'' + view + '\',\'' + mode + '\')" ' + css + '>'
            + '<span style="' + iconCSS + '">' + iconText + '</span>'
            + '<div style="font-size:14px;font-weight:600;color:#3D3D3D;margin-bottom:2px">' + title + '</div>'
            + '<div style="font-size:11px;color:#8A8A8A;line-height:1.4">' + sub + '</div>'
            + '</button>';
    }
    var h = '<div style="padding:4px 2px">'
        + '<div style="font-size:18px;font-weight:700;color:#3D3D3D;margin-bottom:4px">选择导出格式</div>'
        + '<div style="font-size:12px;color:#8A8A8A;margin-bottom:18px;line-height:1.5">HTML 适合电脑端打开，长图适合手机保存和分享</div>'
        + '<div style="font-size:11px;font-weight:600;color:#8A8A8A;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px">任务列表</div>'
        + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:18px">'
        +   opt('list','html','&lt;/&gt;','网页文件','下载 .html 到电脑')
        +   opt('list','image','IMG','长图分享','保存或分享到手机')
        + '</div>'
        + '<div style="font-size:11px;font-weight:600;color:#8A8A8A;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px">甘特图</div>'
        + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:18px">'
        +   opt('gantt','html','&lt;/&gt;','网页文件','下载 .html 到电脑')
        +   opt('gantt','image','IMG','长图分享','保存或分享到手机')
        + '</div>'
        + '<button class="btn btn-ghost btn-block" onclick="closeModal()" style="border-radius:10px;height:44px">取消</button>'
        + '<style>.export-opt-btn:hover{border-color:#C89D9F !important;background:#FDF9F7 !important;transform:translateY(-1px)}.export-opt-btn:active{transform:translateY(0)}</style>'
        + '</div>';
    openModal(h);
}

function doExport(view, mode) {
    closeModal();
    var p = currentProject;
    var html = view === 'gantt' ? buildGanttHTML(p) : buildListHTML(p);
    if (mode === 'html') {
        var suffix = view === 'gantt' ? '-甘特图' : '-任务列表';
        downloadBlob(html, (p.name || 'project') + suffix + '.html', 'text/html;charset=utf-8');
        toast('已下载');
    } else {
        renderAndShare(html, (p.name || 'project') + (view === 'gantt' ? '-甘特图' : '-任务列表'));
    }
}

function downloadBlob(content, filename, mime) {
    var blob = new Blob(['\ufeff' + content], { type: mime });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function(){ URL.revokeObjectURL(url); }, 1000);
}

// Render HTML offscreen, capture with html2canvas, then share or download
function renderAndShare(html, basename) {
    if (typeof html2canvas === 'undefined') { toast('图片库未加载', true); return; }
    toast('生成长图中...');
    // Offscreen container at fixed 948px width
    var host = document.createElement('div');
    host.style.cssText = 'position:fixed;left:-99999px;top:0;width:948px;background:#fff;z-index:-1';
    // Extract <body> inner from the full HTML so styles in <style> still apply via innerHTML
    host.innerHTML = html;
    document.body.appendChild(host);
    // The target is the inner .export-root (present in our templates)
    var target = host.querySelector('.export-root') || host;
    setTimeout(function() {
        html2canvas(target, {
            scale: 2, backgroundColor: '#ffffff', useCORS: true, logging: false,
            width: 948, windowWidth: 948
        }).then(function(canvas) {
            canvas.toBlob(function(blob) {
                document.body.removeChild(host);
                if (!blob) { toast('生成失败', true); return; }
                var filename = basename + '.jpg';
                var file = new File([blob], filename, { type: 'image/jpeg' });
                // Try Web Share API (iOS/Android share sheet)
                if (navigator.canShare && navigator.canShare({ files: [file] })) {
                    navigator.share({ files: [file], title: basename }).then(function(){
                        toast('已分享');
                    }).catch(function(err){
                        if (String(err).indexOf('AbortError') < 0) fallbackDownload(blob, filename);
                    });
                } else {
                    fallbackDownload(blob, filename);
                }
            }, 'image/jpeg', 0.92);
        }).catch(function(err) {
            document.body.removeChild(host);
            console.error(err); toast('生成失败: ' + err.message, true);
        });
    }, 50);
}

function fallbackDownload(blob, filename) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function(){ URL.revokeObjectURL(url); }, 1000);
    toast('已下载图片');
}

// ── Shared style + wrapper ──
function exportWrap(title, inner, footer) {
    var css = 'body{margin:0;background:#f5f3ef;font-family:"PingFang SC","Microsoft YaHei",sans-serif;color:#3D3D3D;-webkit-font-smoothing:antialiased}'
        + '.export-root{width:948px;background:#fff;padding:32px 28px;box-sizing:border-box;margin:0 auto}'
        + '.ex-title{font-size:22px;font-weight:700;color:#3D3D3D;margin:0 0 6px}'
        + '.ex-meta{font-size:12px;color:#8A8A8A;margin-bottom:18px;line-height:1.7}'
        + '.ex-meta b{color:#5A6A7A;font-weight:600}'
        + '.ex-desc{font-size:13px;color:#5A6A7A;background:#F8F5F0;padding:10px 14px;border-radius:8px;margin-bottom:20px;line-height:1.6}'
        + '.ex-h2{font-size:15px;font-weight:700;color:#5A6A7A;border-left:4px solid #C89D9F;padding-left:10px;margin:22px 0 12px}'
        + '.ex-foot{font-size:11px;color:#B0A79C;text-align:center;margin-top:24px;padding-top:14px;border-top:1px solid #EEE8E0}';
    return '<!doctype html><html><head><meta charset="utf-8"><title>' + esc(title) + '</title>'
        + '<meta name="viewport" content="width=948">'
        + '<style>' + css + '</style></head><body><div class="export-root">'
        + inner
        + '<div class="ex-foot">' + (footer || '') + ' · 奈娃咖啡 PM · ' + new Date().toLocaleString('zh-CN') + '</div>'
        + '</div></body></html>';
}

function exportHeader(p) {
    var priMap = {urgent:'紧急',high:'高',medium:'中',low:'低'};
    var h = '<div class="ex-title">' + esc(p.name) + '</div>';
    h += '<div class="ex-meta">'
        + '<b>负责人</b> ' + esc(p.owner_name||'-') + ' &nbsp;·&nbsp; '
        + '<b>周期</b> ' + (p.start_date||'-') + ' 至 ' + (p.deadline||'-') + ' &nbsp;·&nbsp; '
        + '<b>进度</b> ' + (p.avg_progress||0) + '% &nbsp;·&nbsp; '
        + '<b>任务</b> ' + (p.tasks||[]).length + ' 条'
        + '</div>';
    if (p.description) h += '<div class="ex-desc">' + esc(p.description) + '</div>';
    return h;
}

// ── List HTML ──
function buildListHTML(p) {
    var priMap = {urgent:'紧急',high:'高',medium:'中',low:'低'};
    var inner = exportHeader(p);
    inner += '<div class="ex-h2">任务明细</div>';
    inner += '<table style="width:100%;border-collapse:collapse;font-size:12px">'
        + '<thead><tr style="background:#F8F5F0;color:#5A6A7A">'
        + '<th style="padding:10px 8px;text-align:left;border-bottom:2px solid #D8D5D0;width:38%">任务</th>'
        + '<th style="padding:10px 8px;text-align:left;border-bottom:2px solid #D8D5D0">阶段</th>'
        + '<th style="padding:10px 8px;text-align:left;border-bottom:2px solid #D8D5D0">负责人</th>'
        + '<th style="padding:10px 8px;text-align:left;border-bottom:2px solid #D8D5D0">优先级</th>'
        + '<th style="padding:10px 8px;text-align:left;border-bottom:2px solid #D8D5D0">开始</th>'
        + '<th style="padding:10px 8px;text-align:left;border-bottom:2px solid #D8D5D0">截止</th>'
        + '<th style="padding:10px 8px;text-align:left;border-bottom:2px solid #D8D5D0;width:70px">进度</th>'
        + '</tr></thead><tbody>';
    (p.tasks||[]).forEach(function(t, i) {
        var col = PHASE_COLORS[t.phase] || '#95A3B3';
        var bg = i % 2 === 0 ? '#ffffff' : '#FAF8F4';
        inner += '<tr style="background:' + bg + '">'
            + '<td style="padding:9px 8px;border-bottom:1px solid #EEE8E0;word-break:break-all;line-height:1.4">' + esc(t.name) + '</td>'
            + '<td style="padding:9px 8px;border-bottom:1px solid #EEE8E0;white-space:nowrap">'
            +   '<span style="display:inline-block;width:8px;height:8px;background:' + col + ';border-radius:50%;margin-right:5px;vertical-align:middle"></span>'
            +   (PHASE_MAP[t.phase]||'-') + '</td>'
            + '<td style="padding:9px 8px;border-bottom:1px solid #EEE8E0;white-space:nowrap">' + esc(t.assignee_name||'-') + '</td>'
            + '<td style="padding:9px 8px;border-bottom:1px solid #EEE8E0;white-space:nowrap">' + (priMap[t.priority]||t.priority||'-') + '</td>'
            + '<td style="padding:9px 8px;border-bottom:1px solid #EEE8E0;white-space:nowrap;color:#8A8A8A">' + (t.start_date||'-') + '</td>'
            + '<td style="padding:9px 8px;border-bottom:1px solid #EEE8E0;white-space:nowrap;color:#8A8A8A">' + (t.end_date||'-') + '</td>'
            + '<td style="padding:9px 8px;border-bottom:1px solid #EEE8E0;white-space:nowrap">'
            +   '<div style="background:#EEE8E0;border-radius:3px;height:6px;width:60px;position:relative;display:inline-block;vertical-align:middle">'
            +   '<div style="background:' + col + ';height:6px;width:' + (t.progress||0) + '%;border-radius:3px"></div></div>'
            +   ' <span style="color:#5A6A7A;margin-left:4px">' + (t.progress||0) + '%</span>'
            + '</td>'
            + '</tr>';
    });
    inner += '</tbody></table>';
    return exportWrap(p.name + ' - 任务列表', inner, '任务列表');
}

// ── Gantt HTML (long image friendly) ──
function buildGanttHTML(p) {
    // Filter & sort
    var tasks = (p.tasks||[]).filter(function(t){ return parseDate(t.start_date) && parseDate(t.end_date); });
    tasks.sort(function(a,b){ return parseDate(a.start_date) - parseDate(b.start_date); });

    if (!tasks.length) {
        return exportWrap(p.name + ' - 甘特图', exportHeader(p) + '<div class="ex-h2">甘特图</div><div style="color:#8A8A8A;font-size:13px;padding:20px;text-align:center">暂无带日期的任务</div>', '甘特图');
    }

    var minD = null, maxD = null;
    tasks.forEach(function(t){
        var s = parseDate(t.start_date), e = parseDate(t.end_date);
        if (!minD || s < minD) minD = new Date(s);
        if (!maxD || e > maxD) maxD = new Date(e);
    });
    minD.setDate(minD.getDate() - 1);
    maxD.setDate(maxD.getDate() + 1);
    var totalDays = Math.max(1, Math.round((maxD - minD) / 86400000));

    // Adaptive vertical granularity — smaller means more rows (taller image)
    var granularity, unitDays, unitLabel, ROW_H;
    if (totalDays <= 60) { granularity = '日'; unitDays = 1; unitLabel = '每日一行'; ROW_H = 22; }
    else if (totalDays <= 200) { granularity = '周'; unitDays = 7; unitLabel = '每周一行'; ROW_H = 26; }
    else { granularity = '月'; unitDays = 30; unitLabel = '每月一行'; ROW_H = 30; }

    // Build time-unit rows (top-to-bottom)
    var rows = [];
    if (granularity === '日') {
        for (var i = 0; i < totalDays; i++) {
            var d = new Date(minD); d.setDate(d.getDate() + i);
            rows.push({ date: d, label: (d.getMonth()+1) + '/' + d.getDate(), dayIdx: i, days: 1, isWeekend: (d.getDay()===0 || d.getDay()===6), monthMark: d.getDate() === 1 });
        }
    } else if (granularity === '周') {
        var cursor = new Date(minD);
        var dow = (cursor.getDay() + 6) % 7;
        cursor.setDate(cursor.getDate() - dow);
        var dayIdx = Math.round((cursor - minD) / 86400000);
        while (dayIdx < totalDays) {
            var wEnd = new Date(cursor); wEnd.setDate(wEnd.getDate()+6);
            rows.push({ date: new Date(cursor), label: (cursor.getMonth()+1) + '/' + cursor.getDate() + '–' + (wEnd.getMonth()+1) + '/' + wEnd.getDate(), dayIdx: dayIdx, days: 7, isWeekend: false, monthMark: cursor.getDate() <= 7 });
            cursor.setDate(cursor.getDate() + 7);
            dayIdx += 7;
        }
    } else {
        var cur = new Date(minD.getFullYear(), minD.getMonth(), 1);
        while (cur <= maxD) {
            var next = new Date(cur.getFullYear(), cur.getMonth()+1, 1);
            var di = Math.round((cur - minD) / 86400000);
            var dlen = Math.round((next - cur) / 86400000);
            rows.push({ date: new Date(cur), label: (cur.getFullYear()%100) + '年' + (cur.getMonth()+1) + '月', dayIdx: di, days: dlen, isWeekend: false, monthMark: true });
            cur = next;
        }
    }
    var totalRows = rows.length;

    // Build global task numbering (for dependency display)
    var taskNum = {};
    tasks.forEach(function(t, i){ taskNum[t.id] = i + 1; });
    // Circled digits 1-20, fallback to #N for >20
    var CIRCLED = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩','⑪','⑫','⑬','⑭','⑮','⑯','⑰','⑱','⑲','⑳'];
    function numGlyph(n){ return n >= 1 && n <= 20 ? CIRCLED[n-1] : '#' + n; }

    // Page layout: inner area is 948-56 padding = 892px. Left date col 80px, tasks use rest.
    var PAGE_W = 892;
    var DATE_W = 80;
    var COL_MIN = 56;
    var MAX_COLS = Math.floor((PAGE_W - DATE_W - 16) / COL_MIN);  // with inner padding
    if (MAX_COLS < 3) MAX_COLS = 3;

    // Chunk tasks into pages
    var pages = [];
    for (var pi = 0; pi < tasks.length; pi += MAX_COLS) {
        pages.push(tasks.slice(pi, pi + MAX_COLS));
    }

    var inner = exportHeader(p);

    // Legend
    var legend = '<div style="margin:0 0 12px;font-size:11px;color:#5A6A7A">';
    PHASES.forEach(function(ph){
        var c = PHASE_COLORS[ph[0]] || '#95A3B3';
        legend += '<span style="display:inline-block;margin-right:14px;white-space:nowrap">'
            + '<span style="display:inline-block;width:10px;height:10px;background:' + c + ';border-radius:2px;vertical-align:middle;margin-right:4px"></span>'
            + ph[1] + '</span>';
    });
    legend += '</div>';

    inner += '<div class="ex-h2">甘特图 · 纵向时间轴</div>' + legend;

    // Today row index
    var today = new Date(); today.setHours(0,0,0,0);
    var todayRowIdx = -1;
    if (today >= minD && today <= maxD) {
        // find row containing today
        for (var ri = 0; ri < rows.length; ri++) {
            var rStart = new Date(minD); rStart.setDate(rStart.getDate() + rows[ri].dayIdx);
            var rEnd = new Date(rStart); rEnd.setDate(rEnd.getDate() + rows[ri].days);
            if (today >= rStart && today < rEnd) { todayRowIdx = ri; break; }
        }
    }

    // Render each page
    var HEADER_H = 88;  // task name area (includes number + deps chip)
    pages.forEach(function(pageTasks, pageIdx) {
        var NCOLS = pageTasks.length;
        var COL_W = Math.max(COL_MIN, Math.floor((PAGE_W - DATE_W - 16) / NCOLS));
        var chartInnerW = DATE_W + NCOLS * COL_W;
        var chartH = HEADER_H + totalRows * ROW_H;

        var pageLabel = pages.length > 1 ? ' · 第 ' + (pageIdx+1) + '/' + pages.length + ' 组' : '';
        inner += '<div style="font-size:12px;color:#5A6A7A;font-weight:600;margin:' + (pageIdx === 0 ? '0' : '24px') + ' 0 6px">任务组 ' + (pageIdx+1) + pageLabel + ' · ' + NCOLS + ' 条</div>';

        // Chart container
        inner += '<div style="position:relative;width:' + chartInnerW + 'px;height:' + chartH + 'px;border:1px solid #D8D5D0;border-radius:6px;background:#fff;overflow:hidden;box-sizing:border-box">';

        // ── Header: date column label + task name columns ──
        inner += '<div style="position:absolute;left:0;top:0;width:' + DATE_W + 'px;height:' + HEADER_H + 'px;background:#F0EDE8;border-right:1px solid #D8D5D0;border-bottom:2px solid #D8D5D0;line-height:' + HEADER_H + 'px;text-align:center;font-size:11px;font-weight:600;color:#5A6A7A">日期</div>';

        pageTasks.forEach(function(t, ci) {
            var color = PHASE_COLORS[t.phase] || p.color || '#95A3B3';
            var left = DATE_W + ci * COL_W;
            // Dependency chip: show "→ ①②" for upstream tasks
            var depChip = '';
            if (t.depends_on) {
                var depIds = String(t.depends_on).split(',').map(function(x){return parseInt(x,10);}).filter(Boolean);
                var depNums = depIds.map(function(id){ return taskNum[id]; }).filter(function(n){ return n; });
                if (depNums.length) {
                    depChip = '<div style="margin-top:3px;font-size:9px;color:#8A97A8;letter-spacing:0.5px;line-height:1">→ '
                        + depNums.map(numGlyph).join('') + '</div>';
                }
            }
            inner += '<div style="position:absolute;left:' + left + 'px;top:0;width:' + COL_W + 'px;height:' + HEADER_H + 'px;background:#F8F5F0;border-right:1px solid #EEE8E0;border-bottom:2px solid #D8D5D0;box-sizing:border-box;padding:5px 3px 4px;font-size:10px;color:#3D3D3D;line-height:1.25;word-break:break-all;text-align:center;overflow:hidden">'
                + '<div style="display:inline-block;width:18px;height:18px;line-height:18px;border-radius:50%;background:' + color + ';color:#fff;font-size:10px;font-weight:700;margin-bottom:3px">' + (taskNum[t.id] || '') + '</div>'
                + '<div style="font-weight:600;font-size:10px">' + esc(t.name) + '</div>'
                + depChip
                + '</div>';
        });

        // ── Date column: one date label per row ──
        rows.forEach(function(r, ri) {
            var top = HEADER_H + ri * ROW_H;
            var bg = r.isWeekend ? '#F8F5F0' : (ri % 2 ? '#FDFCFA' : '#ffffff');
            var fontW = r.monthMark ? '700' : '500';
            var fontC = r.monthMark ? '#5A6A7A' : '#8A8A8A';
            inner += '<div style="position:absolute;left:0;top:' + top + 'px;width:' + DATE_W + 'px;height:' + ROW_H + 'px;line-height:' + ROW_H + 'px;text-align:center;font-size:10px;font-weight:' + fontW + ';color:' + fontC + ';background:' + bg + ';border-right:1px solid #D8D5D0;border-bottom:1px solid #F0EDE8;box-sizing:border-box">' + esc(r.label) + '</div>';
        });

        // ── Row stripes across task area ──
        rows.forEach(function(r, ri) {
            var top = HEADER_H + ri * ROW_H;
            var bg = r.isWeekend ? '#F8F5F0' : (ri % 2 ? '#FDFCFA' : '#ffffff');
            inner += '<div style="position:absolute;left:' + DATE_W + 'px;top:' + top + 'px;width:' + (NCOLS * COL_W) + 'px;height:' + ROW_H + 'px;background:' + bg + ';border-bottom:1px solid #F0EDE8;box-sizing:border-box"></div>';
        });

        // ── Column separators ──
        for (var cj = 1; cj <= NCOLS; cj++) {
            var cx = DATE_W + cj * COL_W - 1;
            inner += '<div style="position:absolute;left:' + cx + 'px;top:' + HEADER_H + 'px;width:1px;height:' + (totalRows * ROW_H) + 'px;background:#EEE8E0"></div>';
        }

        // ── Today line (full horizontal) ──
        if (todayRowIdx >= 0) {
            var ty = HEADER_H + todayRowIdx * ROW_H + Math.floor(ROW_H/2);
            inner += '<div style="position:absolute;left:0;top:' + ty + 'px;width:' + chartInnerW + 'px;height:2px;background:#E85D5D;z-index:4"></div>';
            inner += '<div style="position:absolute;left:2px;top:' + (ty - 7) + 'px;font-size:9px;color:#fff;background:#E85D5D;padding:1px 5px;border-radius:2px;font-weight:700;z-index:5">今天</div>';
        }

        // ── Task bars (vertical) ──
        pageTasks.forEach(function(t, ci) {
            var s = parseDate(t.start_date), e = parseDate(t.end_date);
            // Find start + end row indices
            var startDayOffset = Math.max(0, Math.round((s - minD) / 86400000));
            var endDayOffset = Math.min(totalDays, Math.round((e - minD) / 86400000) + 1);  // exclusive
            var startRow = 0, endRow = totalRows;
            for (var ri = 0; ri < rows.length; ri++) {
                if (rows[ri].dayIdx + rows[ri].days > startDayOffset) { startRow = ri; break; }
            }
            for (var ri2 = rows.length - 1; ri2 >= 0; ri2--) {
                if (rows[ri2].dayIdx < endDayOffset) { endRow = ri2 + 1; break; }
            }
            if (endRow <= startRow) endRow = startRow + 1;

            var color = PHASE_COLORS[t.phase] || p.color || '#95A3B3';
            var prog = Math.max(0, Math.min(100, t.progress || 0));

            var left = DATE_W + ci * COL_W + 6;
            var barW = COL_W - 12;
            var top = HEADER_H + startRow * ROW_H + 2;
            var barH = (endRow - startRow) * ROW_H - 4;
            if (barH < 12) barH = 12;

            // Progress fill from top, grows downward
            var progH = Math.round(barH * prog / 100);

            // Bar container (rounded). Use single <div>, no flex/transform.
            inner += '<div style="position:absolute;left:' + left + 'px;top:' + top + 'px;width:' + barW + 'px;height:' + barH + 'px;background:' + color + '55;border:1px solid ' + color + ';border-radius:4px;overflow:hidden;box-sizing:border-box;z-index:2">';
            // Progress fill (darker, top-down)
            if (progH > 0) {
                inner += '<div style="position:absolute;left:0;top:0;width:100%;height:' + progH + 'px;background:' + color + '"></div>';
            }
            // Inside-bar label: show progress % at top center
            if (barH >= 18) {
                inner += '<div style="position:absolute;left:0;top:0;width:100%;height:16px;line-height:16px;text-align:center;color:#fff;font-size:10px;font-weight:700;text-shadow:0 1px 1px rgba(0,0,0,0.2)">' + prog + '%</div>';
            }
            inner += '</div>';

            // Start date marker (small triangle/label at top of bar)
            inner += '<div style="position:absolute;left:' + (left) + 'px;top:' + (top - 1) + 'px;width:' + barW + 'px;height:3px;background:' + color + ';z-index:3"></div>';

            // Assignee label below bar if space
            if (barH >= 30 && t.assignee_name) {
                var nameTop = top + Math.max(20, barH - 14);
                inner += '<div style="position:absolute;left:' + left + 'px;top:' + nameTop + 'px;width:' + barW + 'px;height:12px;line-height:12px;text-align:center;color:#fff;font-size:9px;text-shadow:0 1px 1px rgba(0,0,0,0.3);z-index:3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 2px;box-sizing:border-box">' + esc(t.assignee_name) + '</div>';
            }
        });

        inner += '</div>'; // chart container
    });

    // Metadata footer
    inner += '<div style="margin-top:12px;font-size:11px;color:#8A8A8A;text-align:right">'
        + '粒度: ' + unitLabel + ' · 任务 ' + tasks.length + ' 条 · 跨度 ' + totalDays + ' 天'
        + (pages.length > 1 ? ' · 分 ' + pages.length + ' 组显示' : '')
        + '</div>';

    return exportWrap(p.name + ' - 甘特图', inner, '甘特图');
}


// ── Helpers ──
function esc(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
function parseDate(s) {
    if (!s) return null;
    var p = s.split('-');
    if (p.length !== 3) return null;
    return new Date(parseInt(p[0]), parseInt(p[1])-1, parseInt(p[2]));
}
function timeago(dt) {
    if (!dt) return '';
    // Backend stores naive local timestamps; append Z only if no timezone info present
    var normalized = /[Z+\-]\d{2}:?\d{2}$|Z$/.test(dt) ? dt : dt + 'Z';
    var diff = (Date.now() - new Date(normalized).getTime()) / 1000;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return Math.floor(diff/60) + '分钟前';
    if (diff < 86400) return Math.floor(diff/3600) + '小时前';
    if (diff < 604800) return Math.floor(diff/86400) + '天前';
    return dt.slice(0,10);
}
function progressRing(pct, size) {
    var r = (size-6)/2, c = 2*Math.PI*r, off = c - c*pct/100;
    var col = pct >= 100 ? '#82B89C' : pct >= 50 ? '#95A3B3' : pct > 0 ? '#C89D9F' : '#E8E5E0';
    return '<svg class="task-progress-ring" width="'+size+'" height="'+size+'" viewBox="0 0 '+size+' '+size+'">'
        + '<circle cx="'+size/2+'" cy="'+size/2+'" r="'+r+'" fill="none" stroke="#E8E5E0" stroke-width="3"/>'
        + '<circle cx="'+size/2+'" cy="'+size/2+'" r="'+r+'" fill="none" stroke="'+col+'" stroke-width="3" '
        + 'stroke-dasharray="'+c+'" stroke-dashoffset="'+off+'" stroke-linecap="round" transform="rotate(-90 '+size/2+' '+size/2+')"/>'
        + '<text x="'+size/2+'" y="'+size/2+'" text-anchor="middle" dominant-baseline="central" '
        + 'font-size="'+Math.round(size*0.28)+'" font-weight="700" fill="var(--text)">' + pct + '</text></svg>';
}
function priorityTag(p) {
    var labels = {urgent:'紧急',high:'高',medium:'中',low:'低'};
    return '<span class="tag priority-tag priority-' + p + '">' + (labels[p]||p) + '</span>';
}

// ── AI Chat ──
var chatHistory = [];
var chatOpen = false;
var chatStreaming = false;
var chatIntroShown = false;
var lastAIExecLines = null;

function toggleChat() {
    chatOpen = !chatOpen;
    document.getElementById('chat-panel').classList.toggle('open', chatOpen);
    if (chatOpen && !chatIntroShown) {
        chatIntroShown = true;
        appendChatMsg('ai', '你好! 我是奈娃咖啡小助手，一条小鱼。天天创建了我，帮助奈娃咖啡同事可以更好的，更简单，更轻松的完成项目工作，这样以后才能有空带我去钓小鱼。\n\n我可以帮你：\n- 分析项目进度和风险\n- 发现逾期、停滞、未分配的任务\n- 检测阶段依赖和上游阻塞\n- 查看任务附件和图片内容\n- 读取文档文件（PDF/Word/Excel等）\n\n如果你希望我直接改数据，请用：执行: 你的指令（我会先生成提案，需你确认后才执行）\n\n有什么可以帮你的？');
    }
    if (chatOpen) {
        setTimeout(function(){ document.getElementById('chat-input').focus(); }, 300);
    }
}

function appendChatMsg(role, content, isError) {
    var box = document.getElementById('chat-messages');
    var div = document.createElement('div');
    div.className = 'chat-msg ' + role + (isError ? ' error' : '');
    div.textContent = content;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
}

function isChatActionCommand(msg) {
    if (!msg) return false;
    return msg.indexOf('执行:') === 0 || msg.indexOf('执行：') === 0 || msg.indexOf('/exec ') === 0 || msg.indexOf('/apply ') === 0;
}

function injectBatchExecButton(aiDiv, text) {
    if (!aiDiv || !text) return;
    var execInstructions = [];
    text.split('\n').forEach(function(line) {
        var l = line.replace(/^```+\s*/, '').trim();
        if (l.indexOf('执行:') === 0) execInstructions.push(l.slice(3).trim());
        else if (l.indexOf('执行：') === 0) execInstructions.push(l.slice(3).trim());
    });
    var box = document.getElementById('chat-messages');
    var wrapper = document.createElement('div');
    wrapper.style.cssText = 'margin-top:8px;display:flex;flex-wrap:wrap;gap:6px';

    if (execInstructions.length >= 1) {
        lastAIExecLines = execInstructions.slice();
        var btn1 = document.createElement('button');
        btn1.className = 'btn btn-primary';
        btn1.style.cssText = 'padding:6px 12px;font-size:12px';
        btn1.textContent = execInstructions.length === 1 ? '▶ 执行此命令' : '📋 批量执行 (' + execInstructions.length + ' 条)';
        (function(lines) { btn1.onclick = function() { batchExecuteLines(lines, btn1); }; })(execInstructions);
        wrapper.appendChild(btn1);
    }

    // Always offer "从对话提取全部变更" — useful when AI is chatty and didn't emit clean 执行: lines
    var intentHit = /创建|新建|添加|新增|修改|更新|删除|完成|create|add|modify|delete|task|project|任务|项目/i.test(text);
    if (intentHit) {
        var btn2 = document.createElement('button');
        btn2.className = 'btn';
        btn2.style.cssText = 'padding:6px 12px;font-size:12px;background:#10b981;color:white';
        btn2.textContent = '🔄 从整段对话生成变更';
        btn2.onclick = function() { proposeFromConversation(btn2); };
        wrapper.appendChild(btn2);
    }

    if (wrapper.children.length === 0) return;
    box.appendChild(wrapper);
    box.scrollTop = box.scrollHeight;
}

function proposeFromConversation(btn) {
    if (!chatHistory || chatHistory.length === 0) {
        appendChatMsg('ai', '对话为空，没有可提取的内容', true);
        return;
    }
    if (btn) { btn.disabled = true; btn.textContent = '分析对话中...'; }
    fetch(B + '/api/chat/changes/propose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ conversation: chatHistory })
    }).then(function(resp) {
        return resp.json().then(function(j) { return { ok: resp.ok, data: j }; });
    }).then(function(res) {
        if (btn) { btn.disabled = true; btn.textContent = '已生成提案'; }
        lastAIExecLines = null;
        if (!res.ok || (res.data && res.data.error)) {
            appendChatMsg('ai', (res.data && res.data.error) || '生成变更提案失败', true);
            if (btn) { btn.disabled = false; btn.textContent = '🔄 重试'; }
            return;
        }
        if (!res.data || !res.data.count) {
            appendChatMsg('ai', '从对话里没有提取到可执行变更，请补充更具体的信息再试', false);
            if (btn) { btn.disabled = false; btn.textContent = '🔄 重试'; }
            return;
        }
        appendChatProposalCard(res.data);
    }).catch(function() {
        if (btn) { btn.disabled = false; btn.textContent = '🔄 重试'; }
        appendChatMsg('ai', '网络错误，请重试', true);
    });
}

function batchExecuteLines(lines, btn) {
    if (btn) { btn.disabled = true; btn.textContent = '生成提案中...'; }
    var instruction = lines.join('\n');
    fetch(B + '/api/chat/changes/propose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
            instruction: instruction,
            conversation: chatHistory  // include full history as context
        })
    }).then(function(resp) {
        return resp.json().then(function(j) { return { ok: resp.ok, data: j }; });
    }).then(function(res) {
        if (btn) { btn.disabled = true; btn.textContent = '已生成提案'; }
        lastAIExecLines = null;
        if (!res.ok || (res.data && res.data.error)) {
            appendChatMsg('ai', (res.data && res.data.error) || '生成变更提案失败', true);
            return;
        }
        if (!res.data || !res.data.count) {
            appendChatMsg('ai', '没有识别到可执行变更，请补充更具体的信息再试', false);
            return;
        }
        appendChatProposalCard(res.data);
    }).catch(function() {
        if (btn) { btn.disabled = false; btn.textContent = '网络错误，点击重试'; }
        appendChatMsg('ai', '网络错误，请重试', true);
    });
}

function extractChatActionInstruction(msg) {
    if (msg.indexOf('执行:') === 0) return msg.slice(3).trim();
    if (msg.indexOf('执行：') === 0) return msg.slice(3).trim();
    if (msg.indexOf('/exec ') === 0) return msg.slice(6).trim();
    if (msg.indexOf('/apply ') === 0) return msg.slice(7).trim();
    return '';
}

function appendChatProposalCard(batch) {
    var box = document.getElementById('chat-messages');
    var div = document.createElement('div');
    div.className = 'chat-msg ai';

    var lines = [];
    var list = batch.changes || [];
    for (var i = 0; i < list.length && i < 6; i++) {
        var c = list[i] || {};
        lines.push((i + 1) + '. ' + (c.description || (c.change_type || '未命名变更')));
    }
    if (list.length > 6) {
        lines.push('... 另有 ' + (list.length - 6) + ' 条');
    }

    var html = ''
        + '<div style="font-weight:700;margin-bottom:6px">已生成变更提案（' + (batch.count || list.length || 0) + ' 条）</div>'
        + '<div style="white-space:pre-wrap;font-size:12px;line-height:1.5;color:var(--text2);margin-bottom:8px">'
        + esc(lines.join('\n'))
        + '</div>'
        + '<button class="btn btn-primary" style="padding:6px 10px;font-size:12px" onclick="applyChatProposal(' + batch.batch_id + ', this)">确认执行这些变更</button>';
    div.innerHTML = html;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
}

function applyChatProposal(batchId, btn) {
    if (!batchId) return;
    if (btn) btn.disabled = true;
    fetch(B + '/api/chat/changes/' + batchId + '/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({})
    }).then(function(resp) {
        return resp.json().then(function(j){ return { ok: resp.ok, data: j }; });
    }).then(function(res) {
        if (!res.ok || (res.data && res.data.error)) {
            if (btn) btn.disabled = false;
            appendChatMsg('ai', (res.data && res.data.error) || '执行失败，请重试', true);
            return;
        }
        var msg = (res.data && res.data.message) || '变更已执行';
        if (res.data && res.data.errors && res.data.errors.length) {
            msg += '\n部分失败：\n- ' + res.data.errors.join('\n- ');
        }
        appendChatMsg('ai', msg, false);
        loadDashboard();
        loadProjects();
        if (document.getElementById('meetings-list')) loadMeetings();
        if (btn) {
            btn.textContent = '已执行';
            btn.disabled = true;
        }
    }).catch(function() {
        if (btn) btn.disabled = false;
        appendChatMsg('ai', '网络错误，请重试', true);
    });
}

function sendChat() {
    if (chatStreaming) return;
    var input = document.getElementById('chat-input');
    var msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    input.style.height = 'auto';

    chatHistory.push({ role: 'user', content: msg });
    // Auto-flush if history is too large (>80K chars)
    var totalLen = chatHistory.reduce(function(s, m){ return s + (m.content||'').length; }, 0);
    if (totalLen > 80000) {
        chatHistory = [{ role: 'user', content: msg }];
        document.getElementById('chat-messages').innerHTML = '';
        appendChatMsg('ai', '(对话已重置，重新开始)');
    }
    appendChatMsg('user', msg);

    // Typing indicator
    var box = document.getElementById('chat-messages');
    var typing = document.createElement('div');
    typing.className = 'chat-typing';
    typing.id = 'chat-typing';
    typing.innerHTML = '<span></span><span></span><span></span>';
    box.appendChild(typing);
    box.scrollTop = box.scrollHeight;

    chatStreaming = true;
    document.getElementById('chat-send').disabled = true;

    // Handle bare confirmation when there's a pending exec from last AI message
    if (lastAIExecLines && lastAIExecLines.length > 0 && /^(确认|确认执行|全部执行|批量执行|执行全部|ok|好的|执行)$/.test(msg.trim())) {
        var t0b = document.getElementById('chat-typing');
        if (t0b) t0b.remove();
        chatStreaming = false;
        document.getElementById('chat-send').disabled = false;
        batchExecuteLines(lastAIExecLines.slice(), null);
        return;
    }

    if (isChatActionCommand(msg)) {
        var instruction = extractChatActionInstruction(msg);
        if (!instruction) {
            var t0 = document.getElementById('chat-typing');
            if (t0) t0.remove();
            chatStreaming = false;
            document.getElementById('chat-send').disabled = false;
            appendChatMsg('ai', '请在“执行:”后面写清楚要做什么。例如：执行: 给助残咖啡车项目新增任务“改装厂询价”，负责人三多，截止4月25日。', true);
            return;
        }
        fetch(B + '/api/chat/changes/propose', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ instruction: instruction })
        }).then(function(resp) {
            var t = document.getElementById('chat-typing');
            if (t) t.remove();
            return resp.json().then(function(j){ return { ok: resp.ok, data: j }; });
        }).then(function(res) {
            chatStreaming = false;
            document.getElementById('chat-send').disabled = false;
            if (!res.ok || (res.data && res.data.error)) {
                appendChatMsg('ai', (res.data && res.data.error) || '生成变更提案失败', true);
                return;
            }
            if (!res.data || !res.data.count) {
                appendChatMsg('ai', '没有识别到可执行变更。你可以补充更具体的对象、负责人、日期再试。', false);
                return;
            }
            appendChatProposalCard(res.data);
        }).catch(function() {
            var t = document.getElementById('chat-typing');
            if (t) t.remove();
            chatStreaming = false;
            document.getElementById('chat-send').disabled = false;
            appendChatMsg('ai', '网络错误，请重试', true);
        });
        return;
    }

    fetch(B + '/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ messages: chatHistory })
    }).then(function(resp) {
        var t = document.getElementById('chat-typing');
        if (t) t.remove();

        if (!resp.ok) {
            chatStreaming = false;
            document.getElementById('chat-send').disabled = false;
            appendChatMsg('ai', '请求失败，请重试', true);
            return;
        }

        var reader = resp.body.getReader();
        var decoder = new TextDecoder();
        var aiDiv = null;
        var fullText = '';
        var buffer = '';

        function read() {
            reader.read().then(function(result) {
                if (result.done) {
                    if (fullText) chatHistory.push({ role: 'assistant', content: fullText });
                    injectBatchExecButton(aiDiv, fullText);
                    chatStreaming = false;
                    document.getElementById('chat-send').disabled = false;
                    return;
                }
                buffer += decoder.decode(result.value, { stream: true });
                var lines = buffer.split('\n');
                buffer = lines.pop();
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i].trim();
                    if (!line.startsWith('data: ')) continue;
                    var payload = line.slice(6);
                    if (payload === '[DONE]') {
                        if (fullText) chatHistory.push({ role: 'assistant', content: fullText });
                        injectBatchExecButton(aiDiv, fullText);
                        chatStreaming = false;
                        document.getElementById('chat-send').disabled = false;
                        return;
                    }
                    try {
                        var chunk = JSON.parse(payload);
                        if (chunk.error) {
                            appendChatMsg('ai', chunk.error, true);
                            chatStreaming = false;
                            document.getElementById('chat-send').disabled = false;
                            return;
                        }
                        if (chunk.content) {
                            fullText += chunk.content;
                            if (!aiDiv) {
                                aiDiv = appendChatMsg('ai', '');
                            }
                            aiDiv.textContent = fullText;
                            box.scrollTop = box.scrollHeight;
                        }
                    } catch(e) {}
                }
                read();
            }).catch(function() {
                if (!fullText) appendChatMsg('ai', '连接中断', true);
                if (fullText) chatHistory.push({ role: 'assistant', content: fullText });
                chatStreaming = false;
                document.getElementById('chat-send').disabled = false;
            });
        }
        read();
    }).catch(function() {
        var t = document.getElementById('chat-typing');
        if (t) t.remove();
        appendChatMsg('ai', '网络错误，请重试', true);
        chatStreaming = false;
        document.getElementById('chat-send').disabled = false;
    });
}

// ── Meetings ──
var currentMeeting = null;

function loadMeetings() {
    api('/api/meetings', null, function(list) {
        var el = document.getElementById('meetings-list');
        if (!list.length) {
            el.innerHTML = '<div class="empty-state"><p>暂无会议纪要</p><p style="font-size:13px;color:#999">点击 + 导入会议纪要</p></div>';
            return;
        }
        var html = '';
        list.forEach(function(m) {
            var statusMap = { imported: '已导入', analyzed: '已分析', executed: '已执行' };
            var statusClass = m.status === 'executed' ? 'badge-green' : m.status === 'analyzed' ? 'badge-orange' : 'badge-blue';
            html += '<div class="card" onclick="viewMeeting(' + m.id + ')">' +
                '<div class="card-row"><span class="card-title">' + esc(m.title) + '</span>' +
                '<span class="badge ' + statusClass + '">' + (statusMap[m.status] || m.status) + '</span></div>' +
                '<div class="card-meta">' + (m.meeting_date || '') + ' · ' + esc(m.imported_by_name || '') + '</div>' +
                '</div>';
        });
        el.innerHTML = html;
    }, 'GET');
}

function openMeetingImport() {
    // Load projects for selection
    api('/api/projects', null, function(projects) {
        var projOpts = '';
        (projects || []).forEach(function(p) {
            projOpts += '<label class="checkbox-row"><input type="checkbox" value="' + p.id + '"> ' + esc(p.name) + '</label>';
        });

        var html = '<div class="modal-title">导入会议纪要</div>'
            + '<div class="form-group"><label class="form-label">会议标题</label>'
            + '<input type="text" class="form-input" id="mt-title" placeholder="例：产品周会 2026-05-15"></div>'
            + '<div class="form-group"><label class="form-label">会议日期</label>'
            + '<input type="date" class="form-input" id="mt-date" value="' + new Date().toISOString().slice(0,10) + '"></div>'
            + '<div class="form-group">'
            + '<label class="form-label" style="display:flex;align-items:center;justify-content:space-between">'
            + '<span>会议内容</span>'
            + '<button type="button" class="mt-upload-btn" id="mt-upload-btn" title="从文件导入（仅支持 .md .txt .csv）" onclick="document.getElementById(\'mt-file\').click()">'
            + '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>'
            + '<span class="mt-upload-label">导入文件</span>'
            + '</button>'
            + '<input type="file" id="mt-file" accept=".md,.txt,.csv" style="display:none" onchange="handleMeetingFile(this)">'
            + '</label>'
            + '<textarea class="form-input" id="mt-content" rows="10" placeholder="粘贴会议纪要文字内容，或点右上角「导入文件」上传 .md / .txt / .csv"></textarea>'
            + '<div id="mt-file-info" style="font-size:12px;color:var(--text3);margin-top:6px;display:none"></div>'
            + '</div>'
            + '<div class="form-group"><label class="form-label">关联项目 <span style="color:var(--text3);font-size:12px">(可选)</span></label>'
            + '<div class="checkbox-group" id="mt-projects">' + projOpts + '</div></div>'
            + '<button class="btn btn-primary btn-block" onclick="submitMeeting()" style="margin-top:16px">保存</button>';

        document.getElementById('meeting-import-container').innerHTML = html;
        setTitle('导入会议纪要');
        pushPage('meeting-import');
    }, 'GET');
}

function submitMeeting() {
    var title = document.getElementById('mt-title').value.trim();
    var content = document.getElementById('mt-content').value.trim();
    var meetingDate = document.getElementById('mt-date').value;
    if (!title) { toast('请输入会议标题', true); return; }
    if (!content) { toast('请输入会议内容', true); return; }

    var checks = document.querySelectorAll('#mt-projects input:checked');
    var pids = [];
    checks.forEach(function(c){ pids.push(c.value); });

    api('/api/meetings', {
        title: title,
        content: content,
        meeting_date: meetingDate,
        related_projects: pids.join(',')
    }, function(data) {
        toast('会议纪要已保存');
        goBack();
        loadMeetings();
    });
}

function handleMeetingFile(input) {
    var file = input.files && input.files[0];
    if (!file) return;
    var allowed = ['.md', '.txt', '.csv'];
    var name = file.name || '';
    var ext = name.slice(name.lastIndexOf('.')).toLowerCase();
    if (allowed.indexOf(ext) < 0) {
        toast('仅支持 .md .txt .csv', true);
        input.value = '';
        return;
    }
    var btn = document.getElementById('mt-upload-btn');
    var info = document.getElementById('mt-file-info');
    if (btn) btn.classList.add('loading');
    if (info) { info.style.display = 'block'; info.textContent = '解析中…'; }

    var fd = new FormData();
    fd.append('file', file);
    fetch(B + '/api/meetings/extract-file', { method: 'POST', body: fd, credentials: 'same-origin' })
        .then(function(r){ return r.json().then(function(j){ return { ok: r.ok, data: j }; }); })
        .then(function(res){
            if (btn) btn.classList.remove('loading');
            if (!res.ok) {
                var msg = (res.data && res.data.error) || '解析失败';
                if (info) { info.style.color = '#c0504d'; info.textContent = msg; }
                toast(msg, true);
                input.value = '';
                return;
            }
            var d = res.data;
            var ta = document.getElementById('mt-content');
            if (ta) ta.value = d.text || '';
            var tEl = document.getElementById('mt-title');
            if (tEl && !tEl.value.trim() && d.suggested_title) tEl.value = d.suggested_title;
            var dEl = document.getElementById('mt-date');
            if (dEl && d.suggested_date) dEl.value = d.suggested_date;
            if (info) {
                info.style.color = 'var(--text3)';
                info.textContent = '已导入 ' + d.filename + '（' + d.chars + ' 字符' + (d.truncated ? '，已截断至 50 万字' : '') + '）';
            }
            toast('文件已导入');
            input.value = '';
        })
        .catch(function(err){
            if (btn) btn.classList.remove('loading');
            if (info) { info.style.color = '#c0504d'; info.textContent = '上传失败：' + err; }
            toast('上传失败', true);
            input.value = '';
        });
}

function viewMeeting(id) {
    api('/api/meetings/' + id, null, function(m) {
        currentMeeting = m;
        renderMeetingDetail(m);
        setTitle(m.title);
        pushPage('meeting-changes');
    }, 'GET');
}

function renderMeetingDetail(m) {
    var html = '<div class="meeting-detail">';
    html += '<div class="card" style="position:relative">'
        + '<button class="meeting-more-btn" onclick="toggleMeetingMenu(event,' + m.id + ')" title="更多操作" aria-label="更多操作">'
        + '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>'
        + '</button>'
        + '<div class="meeting-more-menu" id="meeting-more-menu-' + m.id + '" style="display:none">'
        + '<button class="meeting-more-item" onclick="analyzeMeeting(' + m.id + ');closeMeetingMenu(' + m.id + ')">重新 AI 分析</button>'
        + '<button class="meeting-more-item danger" onclick="deleteMeeting(' + m.id + ',\'' + esc(m.title).replace(/'/g, "\\'") + '\')">删除会议</button>'
        + '</div>';
    html += '<div class="card-meta">' + (m.meeting_date || '') + ' · ' + esc(m.imported_by_name || '') + '</div>';
    html += '<div class="meeting-content">' + esc(m.content).replace(/\n/g, '<br>') + '</div></div>';

    // Analysis button
    var hasPending = (m.changes || []).some(function(c){ return c.status === 'pending'; });
    if (m.status === 'imported' || !m.changes || !m.changes.length) {
        html += '<button class="btn btn-primary btn-block" id="btn-analyze" onclick="analyzeMeeting(' + m.id + ')" style="margin:16px 0">' +
            '<svg viewBox="0 0 24 24" width="16" height="16" style="vertical-align:middle;margin-right:4px;fill:currentColor"><path d="M12 2a10 10 0 100 20 10 10 0 000-20zm1 17.93c-3.95.49-7.4-2.73-7.9-6.65A7.008 7.008 0 0112 4.07V2a10 10 0 000 19.93v-2z"/></svg>' +
            'AI 分析变更</button>';
    }

    // Changes list
    if (m.changes && m.changes.length) {
        html += '<div class="section-title" style="margin-top:16px">变更建议 (' + m.changes.length + ')</div>';
        if (hasPending) {
            html += '<button class="btn btn-primary btn-block" onclick="confirmAllChanges(' + m.id + ')" style="margin-bottom:12px">全部确认并执行</button>';
        }
        // Group subtasks under their inferred parent create_task.
        // Rule: a create_subtask with task_id=null is treated as a child of the
        // most recent preceding create_task. Subtasks with a valid task_id stay flat.
        var groups = [];
        var lastCreateTaskGroup = null;
        m.changes.forEach(function(c) {
            var nv = {};
            try { nv = c.new_value ? (typeof c.new_value === 'string' ? JSON.parse(c.new_value) : c.new_value) : {}; } catch(e){}
            if (c.change_type === 'create_task') {
                var g = { parent: c, parentNV: nv, children: [] };
                groups.push(g);
                lastCreateTaskGroup = g;
            } else if (c.change_type === 'create_subtask' && (!nv || !nv.task_id) && lastCreateTaskGroup) {
                lastCreateTaskGroup.children.push(c);
            } else {
                groups.push({ parent: c, parentNV: nv, children: [] });
                if (c.change_type !== 'create_task') lastCreateTaskGroup = null;
            }
        });
        groups.forEach(function(g) {
            if (g.children.length) {
                html += '<div class="change-group">';
                html += renderChangeCard(m.id, g.parent, { isParent: true, childCount: g.children.length });
                html += '<div class="change-children">';
                g.children.forEach(function(child) {
                    html += renderChangeCard(m.id, child, { isChild: true, parentName: g.parentNV.name || '' });
                });
                html += '</div></div>';
            } else {
                html += renderChangeCard(m.id, g.parent);
            }
        });
    }

    html += '</div>';
    document.getElementById('meeting-changes-container').innerHTML = html;
}

function renderChangeCard(mid, c, opts) {
    opts = opts || {};
    var typeMap = {
        create_project: '新建项目', modify_project: '修改项目',
        create_task: '新建任务', modify_task: '修改任务', complete_task: '完成任务',
        create_subtask: '新建子任务', add_comment: '添加评论'
    };
    var statusMap = { pending: '待确认', confirmed: '已确认', skipped: '已跳过' };
    var statusClass = c.status === 'confirmed' ? 'badge-green' : c.status === 'skipped' ? 'badge-gray' : 'badge-orange';

    var extraClass = '';
    if (opts.isParent) extraClass = ' change-card-parent';
    if (opts.isChild) extraClass = ' change-card-child';

    var html = '<div class="card change-card' + extraClass + '" id="change-' + c.id + '">' +
        '<div class="card-row">' +
        '<span class="badge badge-blue">' + (typeMap[c.change_type] || c.change_type) + '</span>' +
        '<span class="badge ' + statusClass + '">' + (statusMap[c.status] || c.status) + '</span>' +
        (opts.isParent && opts.childCount ? '<span class="badge badge-gray" style="margin-left:auto">含 ' + opts.childCount + ' 个子任务</span>' : '') +
        (opts.isChild ? '<span class="badge badge-gray" title="父任务：' + esc(opts.parentName || '') + '">↳ 子任务</span>' : '') +
        '</div>' +
        '<div class="change-desc">' + esc(c.description) + '</div>';

    // Show old/new value comparison
    if (c.old_value) {
        try {
            var ov = typeof c.old_value === 'string' ? JSON.parse(c.old_value) : c.old_value;
            if (ov && typeof ov === 'object' && Object.keys(ov).length) {
                html += '<div class="change-diff"><span class="diff-label">变更前:</span> ' + formatChangeValue(ov) + '</div>';
            }
        } catch(e){}
    }
    if (c.new_value) {
        try {
            var nv = typeof c.new_value === 'string' ? JSON.parse(c.new_value) : c.new_value;
            if (nv && typeof nv === 'object' && Object.keys(nv).length) {
                html += '<div class="change-diff"><span class="diff-label">变更后:</span> ' + formatChangeValue(nv) + '</div>';
            }
        } catch(e){}
    }

    if (c.status === 'pending') {
        html += '<div class="change-actions">' +
            '<button class="btn btn-sm btn-primary" onclick="confirmChange(' + mid + ',' + c.id + ')">确认执行</button>' +
            '<button class="btn btn-sm btn-ghost" onclick="skipChange(' + mid + ',' + c.id + ')">跳过</button>' +
            '</div>';
    }
    html += '</div>';
    return html;
}

function formatChangeValue(obj) {
    var fieldMap = {
        name: '名称', description: '描述', deadline: '截止日期', owner_name: '负责人',
        phase: '阶段', progress: '进度', assignee_name: '负责人', priority: '优先级',
        end_date: '截止日期', start_date: '开始日期', content: '内容',
        project_id: '项目ID', task_id: '任务ID', status: '状态'
    };
    var parts = [];
    Object.keys(obj).forEach(function(k) {
        var label = fieldMap[k] || k;
        var val = obj[k];
        if (k === 'phase' && PHASE_MAP[val]) val = PHASE_MAP[val];
        if (k === 'progress') val = val + '%';
        parts.push(label + ': ' + val);
    });
    return parts.join(' | ');
}

function analyzeMeeting(id) {
    var btn = document.getElementById('btn-analyze');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> AI 分析中...';
    }
    api('/api/meetings/' + id + '/analyze', {}, function(data) {
        toast('分析完成，生成 ' + data.count + ' 条变更建议');
        viewMeeting(id);
    });
}

function toggleMeetingMenu(ev, id) {
    if (ev) { ev.stopPropagation(); ev.preventDefault(); }
    var menu = document.getElementById('meeting-more-menu-' + id);
    if (!menu) return;
    var open = menu.style.display !== 'none';
    // 关掉所有同类菜单
    document.querySelectorAll('.meeting-more-menu').forEach(function(m){ m.style.display = 'none'; });
    if (!open) {
        menu.style.display = 'block';
        var hide = function(e) {
            if (menu.contains(e.target)) return;
            menu.style.display = 'none';
            document.removeEventListener('click', hide, true);
        };
        setTimeout(function(){ document.addEventListener('click', hide, true); }, 0);
    }
}

function closeMeetingMenu(id) {
    var menu = document.getElementById('meeting-more-menu-' + id);
    if (menu) menu.style.display = 'none';
}

function deleteMeeting(id, title) {
    closeMeetingMenu(id);
    var msg = '确认删除会议「' + title + '」？\n\n• 会议纪要本体及其全部变更建议都会被删除\n• 已确认并执行到任务/项目的真实数据【不会被回滚】\n\n此操作不可恢复。';
    if (!confirm(msg)) return;
    fetch(B + '/api/meetings/' + id, { method: 'DELETE', credentials: 'same-origin' })
        .then(function(r){ return r.json().then(function(j){ return { ok: r.ok, data: j }; }); })
        .then(function(res){
            if (!res.ok) { toast((res.data && res.data.error) || '删除失败', true); return; }
            toast(res.data.message || '已删除');
            goBack();
            loadMeetings();
        })
        .catch(function(){ toast('网络错误', true); });
}

function confirmChange(mid, cid) {
    api('/api/meetings/' + mid + '/changes/' + cid + '/confirm', {}, function(data) {
        toast(data.message);
        viewMeeting(mid);
    });
}

function skipChange(mid, cid) {
    api('/api/meetings/' + mid + '/changes/' + cid + '/skip', {}, function(data) {
        toast(data.message);
        viewMeeting(mid);
    });
}

function confirmAllChanges(mid) {
    if (!confirm('确定要执行所有待确认的变更吗？')) return;
    api('/api/meetings/' + mid + '/confirm-all', {}, function(data) {
        toast(data.message);
        if (data.errors && data.errors.length) {
            toast('部分变更执行失败', true);
        }
        viewMeeting(mid);
    });
}
// ═══════════════════════════════════════════════════════════
//  Calendar Sync — iCal subscription modal
// ═══════════════════════════════════════════════════════════
function openCalendarSync() {
    fetch(B + '/api/cal/me', { credentials: 'same-origin' })
        .then(function(r){ return r.json(); })
        .then(function(d){ renderCalendarSyncModal(d); })
        .catch(function(){ toast('加载失败', true); });
}

function renderCalendarSyncModal(d) {
    var existing = document.getElementById('cal-sync-modal');
    if (existing) existing.remove();

    var modal = document.createElement('div');
    modal.id = 'cal-sync-modal';
    modal.className = 'cal-sync-bg';
    modal.innerHTML =
        '<div class="cal-sync-card">' +
            '<div class="cal-sync-head">' +
                '<div class="cal-sync-icon">📅</div>' +
                '<div>' +
                    '<div class="cal-sync-title">同步到手机日历</div>' +
                    '<div class="cal-sync-sub">所有分配给你的任务，自动出现在系统日历里</div>' +
                '</div>' +
                '<button class="cal-sync-close" onclick="closeCalSync()">×</button>' +
            '</div>' +

            '<div class="cal-sync-url-row">' +
                '<input id="cal-sync-url" class="cal-sync-url" readonly value="' + escAttr(d.https_url) + '">' +
                '<button class="cal-sync-copy" onclick="copyCalUrl()">复制</button>' +
            '</div>' +
            '<a class="cal-sync-add-btn" href="' + escAttr(d.webcal_url) + '">' +
                '<span style="font-size:18px">📲</span> 在 iPhone / iPad 上一键添加' +
            '</a>' +
            '<div class="cal-sync-hint">在 iPhone Safari 中打开本页面，点上方按钮，系统会自动弹出"添加订阅"对话框</div>' +

            '<div class="cal-tabs">' +
                '<button class="cal-tab active" onclick="switchCalTab(this,\'ios\')">iPhone</button>' +
                '<button class="cal-tab" onclick="switchCalTab(this,\'android\')">安卓</button>' +
                '<button class="cal-tab" onclick="switchCalTab(this,\'hms\')">鸿蒙</button>' +
            '</div>' +

            '<div id="cal-tab-ios" class="cal-tab-body">' +
                '<ol class="cal-steps">' +
                    '<li>用 iPhone Safari 打开 <code>oa.nevermindcoffee.cn/pm</code></li>' +
                    '<li>登录后再次点击导航栏的 📅 图标</li>' +
                    '<li>点 <b>"在 iPhone 上一键添加"</b>，系统弹出 → 点"订阅"</li>' +
                    '<li>完成！打开"日历"App，就能看到所有任务 ☕</li>' +
                '</ol>' +
                '<div class="cal-tip">💡 不在 iPhone 上？复制上方链接 → 设置 → 日历 → 账户 → 添加账户 → 其他 → 添加已订阅的日历 → 粘贴</div>' +
            '</div>' +

            '<div id="cal-tab-android" class="cal-tab-body" style="display:none">' +
                '<ol class="cal-steps">' +
                    '<li>复制上方 URL</li>' +
                    '<li>电脑浏览器登录 <code>calendar.google.com</code></li>' +
                    '<li>左侧"其他日历" → <b>"+"</b> → "通过网址添加"</li>' +
                    '<li>粘贴 URL → 添加日历</li>' +
                    '<li>手机 Google 日历 App 会自动同步</li>' +
                '</ol>' +
                '<div class="cal-tip">💡 用三星日历？设置 → 添加新日历 → 网络日历，同样粘贴 URL</div>' +
            '</div>' +

            '<div id="cal-tab-hms" class="cal-tab-body" style="display:none">' +
                '<ol class="cal-steps">' +
                    '<li>复制上方 URL</li>' +
                    '<li>华为日历 App → 我 → 设置 → 添加日历账户</li>' +
                    '<li>选 <b>CalDAV / 订阅日历</b> → 粘贴 URL</li>' +
                    '<li>命名为"奈娃 PM"，完成</li>' +
                '</ol>' +
                '<div class="cal-tip">💡 鸿蒙日历支持 webcal 订阅，刷新频率约 1 小时</div>' +
            '</div>' +

            '<div class="cal-sync-foot">' +
                '<div class="cal-sync-info">🔒 链接含你的私人 token，请勿分享。每小时自动刷新。</div>' +
                '<button class="cal-sync-regen" onclick="regenCalToken()">重置链接</button>' +
            '</div>' +
        '</div>';
    document.body.appendChild(modal);
    modal.addEventListener('click', function(e){
        if (e.target === modal) closeCalSync();
    });
}

function closeCalSync() {
    var m = document.getElementById('cal-sync-modal');
    if (m) m.remove();
}

function copyCalUrl() {
    var input = document.getElementById('cal-sync-url');
    if (!input) return;
    input.select();
    input.setSelectionRange(0, 99999);
    try {
        navigator.clipboard.writeText(input.value).then(function(){
            toast('已复制 ✓');
        }, function(){ document.execCommand('copy'); toast('已复制 ✓'); });
    } catch(e) {
        document.execCommand('copy');
        toast('已复制 ✓');
    }
}

function switchCalTab(btn, key) {
    document.querySelectorAll('.cal-tab').forEach(function(b){ b.classList.remove('active'); });
    btn.classList.add('active');
    ['ios','android','hms'].forEach(function(k){
        var el = document.getElementById('cal-tab-' + k);
        if (el) el.style.display = k === key ? 'block' : 'none';
    });
}

function regenCalToken() {
    if (!confirm('确定重置链接吗？旧的订阅会失效，需要在手机上重新添加。')) return;
    fetch(B + '/api/cal/regenerate', { method: 'POST', credentials: 'same-origin' })
        .then(function(r){ return r.json(); })
        .then(function(){ toast('已重置，请重新订阅'); openCalendarSync(); });
}

function escAttr(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
}
