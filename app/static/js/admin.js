const token = localStorage.getItem('token');
const isAdmin = localStorage.getItem('isAdmin');
if (!token || isAdmin !== 'true') {
    window.location.href = '/login.html';
}

const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
};

function logout() {
    localStorage.clear();
    window.location.href = '/login.html';
}

function formatCost(cents) {
    return `$${(cents / 100).toFixed(2)}`;
}

function formatTokens(n) {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
    return n.toString();
}

function formatTime(ts) {
    const d = new Date(ts + 'Z');
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

async function loadUsers() {
    try {
        const res = await fetch('/api/admin/users', { headers });
        if (res.status === 401) { logout(); return; }
        const users = await res.json();

        let totalCost = 0;
        const tbody = document.getElementById('users-table');
        tbody.innerHTML = '';

        for (const u of users) {
            totalCost += u.total_cost_cents;
            const remaining = u.spending_limit_cents - u.total_cost_cents;
            const isOver = remaining < 0;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${u.username}</td>
                <td>${u.name || '-'}</td>
                <td>
                    ${u.is_admin ? '<span class="badge badge-admin">admin</span> ' : ''}
                    <span class="badge ${u.is_active ? 'badge-active' : 'badge-inactive'}">${u.is_active ? 'active' : 'disabled'}</span>
                </td>
                <td class="cost">${formatCost(u.spending_limit_cents)}</td>
                <td class="text-end cost">${formatCost(u.total_cost_cents)}</td>
                <td class="text-end cost ${isOver ? 'text-danger fw-bold' : ''}">${formatCost(remaining)}</td>
            `;
            tbody.appendChild(tr);
        }

        document.getElementById('stat-users').textContent = users.length;
        document.getElementById('stat-cost').textContent = formatCost(totalCost);
    } catch (e) {
        console.error('Failed to load users:', e);
    }
}

async function loadUsage() {
    try {
        const res = await fetch('/api/admin/usage', { headers });
        if (res.status === 401) { logout(); return; }
        const usage = await res.json();

        let totalQueries = 0;
        let totalTokens = 0;

        const tbody = document.getElementById('usage-table');
        tbody.innerHTML = '';

        for (const u of usage.slice(0, 100)) {
            totalQueries++;
            totalTokens += (u.input_tokens || 0) + (u.output_tokens || 0);

            const tr = document.createElement('tr');
            tr.className = 'usage-row';
            tr.innerHTML = `
                <td>${formatTime(u.created_at || u.timestamp)}</td>
                <td>${u.username || u.name || '-'}</td>
                <td class="text-end">${formatTokens(u.input_tokens || 0)}</td>
                <td class="text-end">${formatTokens(u.output_tokens || 0)}</td>
                <td class="text-end">${formatTokens(u.cache_read_tokens || 0)}</td>
                <td class="text-end cost">${formatCost(u.cost_cents || 0)}</td>
            `;
            tbody.appendChild(tr);
        }

        document.getElementById('stat-queries').textContent = totalQueries;
        document.getElementById('stat-tokens').textContent = formatTokens(totalTokens);
    } catch (e) {
        console.error('Failed to load usage:', e);
    }
}

// Create user form
document.getElementById('create-user-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const successEl = document.getElementById('create-success');
    const errorEl = document.getElementById('create-error');
    successEl.style.display = 'none';
    errorEl.style.display = 'none';

    const username = document.getElementById('new-username').value.trim();
    const name = document.getElementById('new-name').value.trim();
    const password = document.getElementById('new-password').value;
    const limitDollars = parseFloat(document.getElementById('new-limit').value) || 10;

    try {
        const res = await fetch('/api/admin/users', {
            method: 'POST',
            headers,
            body: JSON.stringify({
                username,
                name,
                password,
                spending_limit_cents: Math.round(limitDollars * 100),
            }),
        });

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || 'Failed to create user');
        }

        successEl.textContent = `Created user: ${username}`;
        successEl.style.display = 'block';
        document.getElementById('create-user-form').reset();
        document.getElementById('new-limit').value = '10';
        loadUsers();
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.style.display = 'block';
    }
});

// CSV bulk upload
document.getElementById('csv-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const successEl = document.getElementById('csv-success');
    const errorEl = document.getElementById('csv-error');
    successEl.style.display = 'none';
    errorEl.style.display = 'none';

    const fileInput = document.getElementById('csv-file');
    if (!fileInput.files.length) return;

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const res = await fetch('/api/admin/users/bulk', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData,
        });
        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || 'Upload failed');
        }
        const data = await res.json();
        let msg = `Created ${data.created.length} user(s).`;
        if (data.skipped.length) msg += ` Skipped ${data.skipped.length} (already exist).`;
        successEl.textContent = msg;
        successEl.style.display = 'block';
        fileInput.value = '';
        loadUsers();
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.style.display = 'block';
    }
});

// Load data on page load
loadUsers();
loadUsage();
