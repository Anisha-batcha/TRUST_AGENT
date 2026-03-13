import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import AuthPage from "./pages/AuthPage";
import DashboardPage from "./pages/DashboardPage";
import SlowLoader from "./components/SlowLoader";

export default function App() {
  const { isAuthenticated } = useAuth();
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setBooting(false), 2200);
    return () => clearTimeout(timer);
  }, []);

  if (booting) {
    return <SlowLoader label="Initializing TrustAgent Console" />;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.9, ease: "easeOut" }}
    >
      <Routes>
        <Route path="/auth" element={<AuthPage />} />
        <Route
          path="/"
          element={isAuthenticated ? <DashboardPage /> : <Navigate to="/auth" replace />}
        />
      </Routes>
    </motion.div>
  );
}
