import Navbar from './Navbar';
import Footer from './Footer';
import './AppLayout.css';

export default function AppLayout({ activePage, children }) {
    return (
        <div className="app-shell">
            <Navbar currentPage={activePage} />
            {children}
            <Footer />
        </div>
    );
}
