import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import logo from "../assets/logo.png";

export default function LandingPage() {
  const navigate = useNavigate();
  const [leaving, setLeaving] = useState(false);

  const headline = useMemo(() => "TrustAgent AI", []);
  const kicker = useMemo(() => "The Anti-Scam Layer", []);
  const sub = useMemo(() => "The autonomous reputation engine for digital era", []);

  const go = async () => {
    setLeaving(true);
    window.setTimeout(() => navigate("/auth"), 320);
  };

  return (
    <div className="landing-shell">
      <div className="landing-bg-grid" aria-hidden="true" />
      <div className="landing-bg-shimmer" aria-hidden="true" />
      <motion.div
        className="landing-orb orb-1"
        aria-hidden="true"
        animate={{ y: [0, -12, 0], opacity: [0.55, 0.8, 0.55] }}
        transition={{ duration: 6.5, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="landing-orb orb-2"
        aria-hidden="true"
        animate={{ y: [0, 10, 0], opacity: [0.35, 0.65, 0.35] }}
        transition={{ duration: 7.5, repeat: Infinity, ease: "easeInOut", delay: 0.6 }}
      />

      <motion.main
        className="landing-card"
        initial={{ opacity: 0, y: 18, scale: 0.985 }}
        animate={leaving ? { opacity: 0, y: -6, scale: 0.98 } : { opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.45, ease: "easeOut" }}
      >
        <motion.img
          src={logo}
          alt="TrustAgent"
          className="landing-logo"
          initial={{ opacity: 0, y: 12, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
        />

        <motion.h1
          className="landing-title"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: "easeOut", delay: 0.08 }}
        >
          {headline}
        </motion.h1>

        <motion.h2
          className="landing-kicker"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: "easeOut", delay: 0.14 }}
        >
          {kicker}
        </motion.h2>

        <motion.p
          className="landing-subtitle"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: "easeOut", delay: 0.16 }}
        >
          {sub}
        </motion.p>

        <motion.div
          className="landing-actions"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: "easeOut", delay: 0.24 }}
        >
          <button className="btn-primary" type="button" onClick={go} disabled={leaving}>
            Get Started
          </button>
        </motion.div>
      </motion.main>
    </div>
  );
}
