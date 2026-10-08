// Global helper to check login status
function checkAuth() {
    const user = JSON.parse(localStorage.getItem('user'));
    const path = window.location.pathname;

    // Protect admin page
    if (path.includes('admin')) {
        if (!user || user.role !== 'admin') {
            alert('Access denied. Admins only.');
            window.location.href = '/login';
        }
    }
}
checkAuth();

// Render navigation bar dynamically based on user session
function renderNavbar() {
    const user = JSON.parse(localStorage.getItem('user'));
    const nav = document.getElementById('navbar');
    if (!nav) return;

    let html = `<a href="/">Home</a>`;
    if (user) {
        if (user.role === 'customer') {
            html += `<a href="/cart">Cart</a>`;
            html += `<a href="/orders">My Orders</a>`;
        }
        if (user.role === 'admin') {
            html += `<a href="/admin">Admin Dashboard</a>`;
        }
        html += `<a href="#" onclick="logout()">Logout (${user.username})</a>`;
    } else {
        html += `<a href="/login">Login / Register</a>`;
    }
    nav.innerHTML = html;
}

function logout() {
    localStorage.removeItem('user');
    window.location.href = '/login';
}

document.addEventListener('DOMContentLoaded', renderNavbar);