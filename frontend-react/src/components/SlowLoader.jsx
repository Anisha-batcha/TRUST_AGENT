import { motion } from "framer-motion";

export default function SlowLoader({ label = "Loading TrustAgent" }) {
  return (
    <div className="loader-wrap">
      <motion.div
        className="loader-orbit"
        animate={{ rotate: 360 }}
        transition={{ repeat: Infinity, duration: 3.4, ease: "linear" }}
      >
        <motion.div
          className="loader-dot"
          animate={{ scale: [1, 1.5, 1], opacity: [0.8, 1, 0.8] }}
          transition={{ repeat: Infinity, duration: 1.7, ease: "easeInOut" }}
        />
      </motion.div>
      <motion.p
        className="loader-text"
        initial={{ opacity: 0.2 }}
        animate={{ opacity: [0.2, 1, 0.2] }}
        transition={{ repeat: Infinity, duration: 2.4, ease: "easeInOut" }}
      >
        {label}
      </motion.p>
    </div>
  );
}
