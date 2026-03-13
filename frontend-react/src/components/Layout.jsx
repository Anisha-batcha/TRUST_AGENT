import logo from "../assets/logo.png";

export default function Layout({ title, subtitle, user, onLogout, children }) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-center-wrap">
          <div className="brand">
            <img src={logo} alt="TrustAgent" className="brand-logo" />
            <div>
              <h1>{title}</h1>
              <p>{subtitle}</p>
            </div>
          </div>
        </div>
        {user ? (
          <div className="session-box">
            <span>{user}</span>
            <button className="btn-outline" onClick={onLogout}>Logout</button>
          </div>
        ) : null}
      </header>
      <main className="main-content">{children}</main>
    </div>
  );
}
