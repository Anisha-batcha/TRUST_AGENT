import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import Layout from "../components/Layout";
import SlowLoader from "../components/SlowLoader";
import { useAuth } from "../context/AuthContext";

export default function AuthPage() {
  const navigate = useNavigate();
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      if (mode === "register") {
        if (password !== confirmPassword) {
          throw new Error("Passwords do not match");
        }
        await register(username.trim(), password);
        setMessage("Registration successful. You can login now.");
        setMode("login");
      } else {
        await login(username.trim(), password);
        navigate("/", { replace: true });
      }
    } catch (err) {
      const text = err?.response?.data?.detail || err.message || "Operation failed";
      setMessage(String(text));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout
      title="TrustAgent"
      subtitle="Digital Trust Verification"
    >
      {loading ? <SlowLoader label={mode === "login" ? "Authenticating" : "Creating Account"} /> : null}
      <motion.section
        className="card auth-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
      >
        <div className="switch-tabs">
          <button className={mode === "login" ? "tab active" : "tab"} onClick={() => setMode("login")}>Login</button>
          <button className={mode === "register" ? "tab active" : "tab"} onClick={() => setMode("register")}>Register</button>
        </div>
        <form onSubmit={submit} className="form-grid">
          <label>Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} required minLength={3} />
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />
          {mode === "register" ? (
            <>
              <label>Confirm Password</label>
              <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required minLength={6} />
            </>
          ) : null}
          <button className="btn-primary" type="submit" disabled={loading}>
            {mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>
        {message ? <p className="msg-text">{message}</p> : null}
      </motion.section>
    </Layout>
  );
}
