import React from "react";
import { NavLink } from "react-router-dom";

function Sidebar() {
  const navItems = [
    { label: "Approvals", path: "/approvals" },
    { label: "Disbursements", path: "/disbursements" },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <h2>Nexus</h2>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              isActive ? "nav-link active" : "nav-link"
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

export default Sidebar;
