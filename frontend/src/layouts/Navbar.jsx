import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export const PAGE_LINKS = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'inventory', label: 'Inventory', roles: ['admin', 'manager', 'store_manager', 'staff'] },
    { id: 'requests', label: 'Requests', roles: ['admin', 'manager', 'store_manager', 'staff'] },
    { id: 'procurement', label: 'Procurement', roles: ['admin', 'manager', 'store_manager'] },
    { id: 'approvals', label: 'Approvals', roles: ['admin', 'manager'] },
    { id: 'disbursements', label: 'Disbursements', roles: ['admin', 'manager'] },
    { id: 'projects', label: 'Projects', roles: ['admin', 'manager', 'store_manager', 'staff'] },
    { id: 'notifications', label: 'Notifications', roles: ['admin', 'manager', 'store_manager', 'staff'] },
    { id: 'admin', label: 'Admin', roles: ['admin'] },
];

export default function Navbar({ currentPage }) {
    const navigate = useNavigate();
    const { user, logout } = useAuth();
    const visibleLinks = PAGE_LINKS.filter((page) => !page.roles || page.roles.includes(user?.role));

    const handleLogout = () => {
        logout();
        navigate('/login', { replace: true });
    };

    return (
        <header className="app-header">
            <div className="header-inner">
                <span className="brand">NEXUS</span>
                <nav className="primary-nav" aria-label="Main navigation">
                    {visibleLinks.map((page) => page.id === currentPage ? (
                        <span className="nav-item nav-item-current" aria-current="page" key={page.id}>
                            {page.label}
                        </span>
                    ) : (
                        <Link className="nav-item" to={`/${page.id}`} key={page.id}>
                            {page.label}
                        </Link>
                    ))}
                </nav>

                {user && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <span style={{ color: '#cbd5e1' }}>{user.name}</span>
                        <button type="button" onClick={handleLogout} style={{ padding: '8px 12px', borderRadius: '8px' }}>
                            Logout
                        </button>
                    </div>
                )}
            </div>
        </header>
    );
}