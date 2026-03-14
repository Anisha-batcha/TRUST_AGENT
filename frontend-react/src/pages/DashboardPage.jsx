import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  RadialBarChart,
  RadialBar,
} from "recharts";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";
import Layout from "../components/Layout";
import SlowLoader from "../components/SlowLoader";

const CATEGORIES = {
  Instagram: "instagram",
  "X (Twitter)": "x",
  LinkedIn: "linkedin",
  YouTube: "youtube",
  Facebook: "facebook",
  Telegram: "telegram",
  Website: "website",
  Startup: "startup",
  Freelancer: "freelancer",
  "Mobile App": "mobile_app",
};

const DOMAIN_CATEGORY_MAP = {
  "instagram.com": "instagram",
  "x.com": "x",
  "twitter.com": "x",
  "linkedin.com": "linkedin",
  "youtube.com": "youtube",
  "youtu.be": "youtube",
  "facebook.com": "facebook",
  "t.me": "telegram",
  "telegram.me": "telegram",
};

const inferCategoryFromTarget = (target = "") => {
  const t = String(target || "").trim().toLowerCase();
  if (!t) return null;

  if (t.startsWith("http://") || t.startsWith("https://")) {
    try {
      const u = new URL(t);
      let host = (u.hostname || "").toLowerCase();
      if (host.startsWith("www.")) host = host.slice(4);
      for (const [domain, cat] of Object.entries(DOMAIN_CATEGORY_MAP)) {
        if (host === domain || host.endsWith(`.${domain}`)) return cat;
      }
      return "website";
    } catch {
      return null;
    }
  }

  if (t.includes(".") && !t.includes(" ") && !t.includes("/")) return "website";
  return null;
};

const validateTargetMatchesCategory = (target, category) => {
  const inferred = inferCategoryFromTarget(target);
  if (!inferred) return null;
  const selected = String(category || "").trim().toLowerCase();
  if (!selected) return null;
  if (inferred !== selected) {
    return `Invalid: this looks like a '${inferred}' target. Please select '${inferred}' category.`;
  }
  return null;
};

const POLICY_CHECKS = {
  instagram: [
    "Engagement-to-follower consistency",
    "Review spike anomaly",
    "Account age and profile completeness",
  ],
  x: [
    "Interaction quality baseline",
    "Review/comment burst behavior",
    "Profile completion confidence",
  ],
  linkedin: [
    "Professional profile completeness",
    "Identity maturity signal",
    "Review integrity and sentiment consistency",
  ],
  youtube: [
    "View-to-engagement authenticity",
    "Channel maturity and continuity",
    "Comment/review spike behavior",
  ],
  facebook: [
    "Comment/review burst detection",
    "Profile integrity quality",
    "Behavioral anomaly cross-check",
  ],
  telegram: [
    "Channel metadata completeness",
    "Engagement consistency",
    "History longevity signal",
  ],
  mobile_app: [
    "App-store rating confidence",
    "Permission risk mismatch",
    "Publisher maturity and brand impersonation",
  ],
  startup: [
    "Founder/team visibility",
    "Funding-claim corroboration",
    "Traffic consistency with growth claims",
  ],
  freelancer: [
    "Review concentration and burst checks",
    "Profile completeness and trust baseline",
    "Account maturity signal",
  ],
  website: [
    "Domain-age trust history",
    "Engagement and sentiment coherence",
    "Review velocity anomaly checks",
  ],
};

const clamp = (value, lower, upper) => Math.max(lower, Math.min(upper, value));

const followerAuthenticityBreakdown = (metrics = {}) => {
  const engagement = metrics.engagement_rate || 0.02;
  const reviewSpike = metrics.review_spike_ratio || 0.3;
  const profileCompleteness = metrics.profile_completeness || 0.8;

  const botScore =
    0.55 * (1 - clamp(engagement / 0.12, 0, 1)) +
    0.3 * clamp(reviewSpike, 0, 1) +
    0.15 * (1 - clamp(profileCompleteness, 0, 1));

  const likelyBot = Math.round(clamp(botScore, 0.05, 0.95) * 100);
  return [
    { name: "Likely Bot", value: likelyBot, color: "#d4632d" },
    { name: "Authentic", value: 100 - likelyBot, color: "#2643d5" },
  ];
};

const sentimentBreakdown = (metrics = {}) => {
  const sentiment = clamp(metrics.sentiment_score || 0.6, 0, 1);
  const reviewSpike = clamp(metrics.review_spike_ratio || 0.3, 0, 1);
  const total = 100;
  let positive = Math.round((0.35 + 0.6 * sentiment - 0.2 * reviewSpike) * total);
  let neutral = Math.round((0.2 + 0.25 * (1 - Math.abs(sentiment - 0.5) * 2)) * total);
  positive = clamp(positive, 0, total);
  neutral = clamp(neutral, 0, total - positive);
  const negative = total - positive - neutral;

  return [
    { name: "Negative", value: negative, fill: "#b43a3a" },
    { name: "Neutral", value: neutral, fill: "#d4632d" },
    { name: "Positive", value: positive, fill: "#2643d5" },
  ];
};

const riskGaugeColor = (score) => {
  if (score < 40) return "#b43a3a";
  if (score < 70) return "#d4632d";
  return "#2643d5";
};

const confidenceBand = (confidenceScore = 0) => {
  if (confidenceScore >= 0.8) return "High";
  if (confidenceScore >= 0.6) return "Medium";
  return "Low";
};

const buildXaiContributions = (xai) => {
  const contributions = Array.isArray(xai?.contributions) ? xai.contributions : [];
  const cleaned = contributions
    .filter((c) => c && Number.isFinite(Number(c.delta)) && c.factor)
    .map((c) => ({
      factor: String(c.factor),
      delta: Number(c.delta),
      confidence: String(c.confidence || "medium"),
      source: String(c.source || "rules.v1"),
    }));
  return cleaned.slice(0, 8).reverse();
};

const buildXaiConfidencePie = (xai, contributions = []) => {
  const counts = xai?.confidence_counts || null;
  const fallback = contributions.reduce(
    (acc, item) => {
      const band = String(item.confidence || "medium").toLowerCase();
      if (band === "high") acc.high += 1;
      else if (band === "low") acc.low += 1;
      else acc.medium += 1;
      return acc;
    },
    { high: 0, medium: 0, low: 0 }
  );
  const finalCounts = counts && typeof counts === "object" ? counts : fallback;
  return [
    { name: "High", value: Number(finalCounts.high || 0), fill: "#2643d5" },
    { name: "Medium", value: Number(finalCounts.medium || 0), fill: "#d4632d" },
    { name: "Low", value: Number(finalCounts.low || 0), fill: "#b43a3a" },
  ].filter((d) => d.value > 0);
};

const buildXaiScoreBars = (result, xai) => {
  return [
    { name: "Rules", score: Number(xai?.rules_score ?? result?.trust_score ?? 0) },
    { name: "ML", score: Number(result?.ml_score ?? 0) },
    { name: "Final", score: Number(result?.trust_score ?? 0) },
  ];
};

const buildUserFriendlyExplanation = (result) => {
  if (!result) return null;
  const trustScore = result.trust_score || 0;
  const riskLevel = result.risk_level || "UNKNOWN";
  const confidence = Math.round((result.confidence_score || 0) * 100);
  const negatives = result?.why_score?.top_negative_factors || [];
  const positives = result?.why_score?.top_positive_factors || [];
  const redFlags = result.red_flags || [];

  const summary =
    riskLevel === "HIGH"
      ? "This profile currently looks risky. Important trust signals are weak."
      : riskLevel === "MEDIUM"
        ? "This profile looks moderately safe, but there are warning signals to verify."
        : "This profile looks relatively safe based on current signals.";

  const mainReason =
    negatives.length > 0
      ? `Main concern: ${negatives[0].factor}.`
      : positives.length > 0
        ? `Main strength: ${positives[0].factor}.`
        : "No strong reason drivers were detected.";

  const actions = [];
  if (redFlags.some((f) => f.toLowerCase().includes("review"))) {
    actions.push("Verify recent reviews manually for sudden or fake activity.");
  }
  if (redFlags.some((f) => f.toLowerCase().includes("follower"))) {
    actions.push("Check follower quality and remove inorganic audience sources.");
  }
  if (redFlags.some((f) => f.toLowerCase().includes("account"))) {
    actions.push("Confirm account history and identity details before trusting.");
  }
  if (actions.length === 0) {
    actions.push("Continue monitoring this target weekly for sudden changes.");
  }

  return {
    summary,
    mainReason,
    meta: `Trust Score: ${trustScore}/100 | Risk: ${riskLevel} | Confidence: ${confidence}% (${confidenceBand(
      result.confidence_score || 0
    )})`,
    actions,
  };
};

const topReasonLine = (sideData) => {
  const negatives = sideData?.why_score?.top_negative_factors || [];
  const positives = sideData?.why_score?.top_positive_factors || [];
  const leadNegative = negatives[0];
  const leadPositive = positives[0];

  if (leadNegative && leadPositive) {
    return `Main risk: ${leadNegative.factor}. Strength signal: ${leadPositive.factor}.`;
  }
  if (leadNegative) {
    return `Main risk driver: ${leadNegative.factor}.`;
  }
  if (leadPositive) {
    return `Main strength driver: ${leadPositive.factor}.`;
  }
  return "No strong factor variance detected.";
};

export default function DashboardPage() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState("investigate");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [compareXaiSide, setCompareXaiSide] = useState("left");
  const [feedbackStatus, setFeedbackStatus] = useState("");
  const [feedbackNotes, setFeedbackNotes] = useState("");

  const [investigateInput, setInvestigateInput] = useState({ target: "", category: "website" });
  const [investigation, setInvestigation] = useState(null);

  const [compareInput, setCompareInput] = useState({ leftTarget: "", leftCategory: "website", rightTarget: "", rightCategory: "website" });
  const [comparison, setComparison] = useState(null);

  const [history, setHistory] = useState([]);
  const [analytics, setAnalytics] = useState([]);

  const runInvestigate = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    setFeedbackStatus("");
    const invalid = validateTargetMatchesCategory(investigateInput.target, investigateInput.category);
    if (invalid) {
      setError(invalid);
      setBusy(false);
      return;
    }
    try {
      const res = await api.post("/investigate", investigateInput, { timeout: 120000 });
      setInvestigation(res.data);
      setFeedbackNotes("");
    } catch (err) {
      setError(err?.response?.data?.detail || "Investigation failed");
    } finally {
      setBusy(false);
    }
  };

  const runCompare = async (e) => {
    e.preventDefault();
    const leftTarget = compareInput.leftTarget.trim();
    const rightTarget = compareInput.rightTarget.trim();
    if (!leftTarget || !rightTarget) {
      setError("Both left and right targets are required.");
      return;
    }
    const invalidLeft = validateTargetMatchesCategory(leftTarget, compareInput.leftCategory);
    if (invalidLeft) {
      setError(`Left target: ${invalidLeft}`);
      return;
    }
    const invalidRight = validateTargetMatchesCategory(rightTarget, compareInput.rightCategory);
    if (invalidRight) {
      setError(`Right target: ${invalidRight}`);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await api.post("/compare", {
        left: { target: leftTarget, category: compareInput.leftCategory },
        right: { target: rightTarget, category: compareInput.rightCategory },
        persist: true,
      }, { timeout: 120000 });
      setComparison(res.data);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const message = err?.message;
      setError(detail || message || "Comparison failed");
    } finally {
      setBusy(false);
    }
  };

  const loadHistory = async () => {
    setBusy(true);
    setError("");
    try {
      const [hRes, aRes] = await Promise.all([
        api.get("/history", { params: { limit: 30 } }),
        api.get("/analytics", { params: { limit: 10 } }),
      ]);
      setHistory(hRes.data.timeline || []);
      setAnalytics(aRes.data.top_risky_targets || []);
    } catch (err) {
      setError(err?.response?.data?.detail || "History load failed");
    } finally {
      setBusy(false);
    }
  };

  const categoryOptions = useMemo(() => Object.entries(CATEGORIES), []);
  const easyExplain = useMemo(
    () => buildUserFriendlyExplanation(investigation),
    [investigation]
  );
  const xai = investigation?.xai || null;
  const xaiContributions = useMemo(() => {
    return buildXaiContributions(xai);
  }, [xai]);
  const xaiConfidencePie = useMemo(() => {
    return buildXaiConfidencePie(xai, xaiContributions);
  }, [xai, xaiContributions]);
  const xaiScoreBars = useMemo(() => {
    if (!investigation) return [];
    return buildXaiScoreBars(investigation, xai);
  }, [investigation, xai]);

  const submitFeedback = async (label) => {
    if (!investigation?.scan_id) {
      setFeedbackStatus("Run an investigation first to submit feedback.");
      return;
    }
    setFeedbackStatus("Saving feedback...");
    try {
      await api.post("/feedback", {
        scan_id: investigation.scan_id,
        label,
        notes: feedbackNotes || undefined,
      });
      setFeedbackStatus(`Saved as '${label}'. Thanks!`);
    } catch (err) {
      setFeedbackStatus(err?.response?.data?.detail || "Feedback save failed");
    }
  };

  return (
    <Layout title="TrustAgent Console" subtitle="Behavioral Trust Intelligence" user={user} onLogout={logout}>
      {busy ? <SlowLoader label="Analyzing signals slowly and deeply" /> : null}
      <section className="tab-row">
        <button className={tab === "investigate" ? "tab active" : "tab"} onClick={() => setTab("investigate")}>Investigate</button>
        <button className={tab === "compare" ? "tab active" : "tab"} onClick={() => setTab("compare")}>Compare</button>
        <button className={tab === "history" ? "tab active" : "tab"} onClick={() => setTab("history")}>History</button>
        <button className={tab === "policies" ? "tab active" : "tab"} onClick={() => setTab("policies")}>Policies</button>
      </section>

      {error ? <p className="error-text">{error}</p> : null}

      {tab === "investigate" ? (
        <motion.section
          className="card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
        >
          <h2>Single Target Investigation</h2>
          <form className="form-grid" onSubmit={runInvestigate}>
            <label>Target URL/Handle</label>
            <input
              value={investigateInput.target}
              onChange={(e) => setInvestigateInput((p) => ({ ...p, target: e.target.value }))}
              placeholder="@brand_or_url"
              required
            />
            <label>Category</label>
            <select value={investigateInput.category} onChange={(e) => setInvestigateInput((p) => ({ ...p, category: e.target.value }))}>
              {categoryOptions.map(([label, value]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <button type="submit" className="btn-primary">Run Investigation</button>
          </form>

          {investigation ? (
            <motion.div
              className="result-grid"
              initial="hidden"
              animate="show"
              variants={{
                hidden: {},
                show: {
                  transition: {
                    staggerChildren: 0.08,
                  },
                },
              }}
            >
              {investigation.category_warning ? (
                <motion.div className="wide-card" variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}>
                  <h3>Category Notice</h3>
                  <p>{investigation.category_warning}</p>
                </motion.div>
              ) : null}
              <motion.div className="metric-card" variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}><span>Trust Score</span><strong>{investigation.trust_score}</strong></motion.div>
              <motion.div className="metric-card" variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}><span>Risk</span><strong>{investigation.risk_level}</strong></motion.div>
              <motion.div className="metric-card" variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}><span>Confidence</span><strong>{Math.round((investigation.confidence_score || 0) * 100)}%</strong></motion.div>
              <motion.div
                className="metric-card"
                title={(investigation.agent_pipeline?.collector?.notes || []).join(" | ")}
                variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              >
                <span>Collector Mode</span>
                <strong>{investigation.agent_pipeline?.collector?.mode || "unknown"}</strong>
              </motion.div>
              <motion.div className="metric-card" variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}><span>ML Score</span><strong>{investigation.ml_score}</strong></motion.div>
              {investigation.feedback_meta?.total ? (
                <motion.div
                  className="metric-card"
                  title={`Legit=${investigation.feedback_meta.legit || 0} | Scam=${investigation.feedback_meta.scam || 0} | Unknown=${investigation.feedback_meta.unknown || 0}`}
                  variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
                >
                  <span>Community Delta</span>
                  <strong>{investigation.feedback_meta.applied_delta >= 0 ? `+${investigation.feedback_meta.applied_delta}` : investigation.feedback_meta.applied_delta}</strong>
                </motion.div>
              ) : null}
              <motion.div className="wide-card" variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}>
                <h3>Easy XAI Summary</h3>
                <p>{investigation.investigation_report}</p>
              </motion.div>
              {easyExplain ? (
                <motion.div className="wide-card" variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}>
                  <h3>User-Friendly Explanation</h3>
                  <p>{easyExplain.summary}</p>
                  <p><strong>{easyExplain.mainReason}</strong></p>
                  <p>{easyExplain.meta}</p>
                  <h4>What You Should Do Next</h4>
                  <ul>
                    {easyExplain.actions.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ul>
                </motion.div>
              ) : null}

              {Array.isArray(investigation.scam_patterns) && investigation.scam_patterns.length ? (
                <motion.div className="wide-card" variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}>
                  <h3>Scam Pattern Signals</h3>
                  <p className="chart-note">These are keyword/pattern matches found in the scraped content. They do not directly change the score; they help you triage quickly.</p>
                  <ul className="pattern-list">
                    {investigation.scam_patterns.map((p) => (
                      <li key={p.pattern_id} className="pattern-item">
                        <span className={`sev sev-${p.severity}`}>{String(p.severity || "").toUpperCase()}</span>
                        <span className="pattern-label">{p.label}</span>
                        <span className="pattern-desc">{p.description}</span>
                      </li>
                    ))}
                  </ul>
                </motion.div>
              ) : null}

              {investigation.scan_id ? (
                <motion.div className="wide-card" variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}>
                  <h3>User Feedback (Improve accuracy)</h3>
                  <p className="chart-note">Mark the scan as legit/scam so we can build a labeled dataset for future calibration.</p>
                  <div className="feedback-row">
                    <button type="button" className="btn-outline" onClick={() => submitFeedback("legit")}>Mark Legit</button>
                    <button type="button" className="btn-outline" onClick={() => submitFeedback("scam")}>Mark Scam</button>
                    <button type="button" className="btn-outline" onClick={() => submitFeedback("unknown")}>Unknown</button>
                  </div>
                  <textarea
                    className="feedback-notes"
                    value={feedbackNotes}
                    onChange={(e) => setFeedbackNotes(e.target.value)}
                    placeholder="Optional notes (why you marked it)"
                    rows={3}
                  />
                  {feedbackStatus ? <p className="msg-text">{feedbackStatus}</p> : null}
                </motion.div>
              ) : null}
              <motion.div className="wide-card" variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}>
                <h3>Trust Visuals</h3>
                <div className="mini-charts-grid">
                  <div className="chart-wrap">
                    <h4 className="chart-title">Gauge Meter</h4>
                    <ResponsiveContainer width="100%" height={230}>
                      <RadialBarChart
                        cx="50%"
                        cy="62%"
                        innerRadius="56%"
                        outerRadius="92%"
                        barSize={18}
                        data={[{ name: "Trust Score", value: investigation.trust_score, fill: riskGaugeColor(investigation.trust_score) }]}
                        startAngle={210}
                        endAngle={-30}
                      >
                        <RadialBar background clockWise dataKey="value" cornerRadius={10} />
                        <text x="50%" y="56%" textAnchor="middle" dominantBaseline="middle" className="gauge-score-text">
                          {investigation.trust_score}
                        </text>
                      </RadialBarChart>
                    </ResponsiveContainer>
                  </div>

                  <div className="chart-wrap">
                    <h4 className="chart-title">Follower Authenticity</h4>
                    <ResponsiveContainer width="100%" height={230}>
                      <PieChart>
                        <Pie
                          data={followerAuthenticityBreakdown(investigation.metrics)}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          outerRadius={78}
                          innerRadius={42}
                          label
                        >
                          {followerAuthenticityBreakdown(investigation.metrics).map((entry) => (
                            <Cell key={entry.name} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>

                  <div className="chart-wrap">
                    <h4 className="chart-title">Sentiment Analysis</h4>
                    <ResponsiveContainer width="100%" height={230}>
                      <BarChart data={sentimentBreakdown(investigation.metrics)}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#d9d4c8" />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                          {sentimentBreakdown(investigation.metrics).map((entry) => (
                            <Cell key={entry.name} fill={entry.fill} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </motion.div>

              {xai ? (
                <motion.div className="wide-card" variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}>
                  <h3>XAI Breakdown (What moved the score)</h3>
                  <p>
                    These charts show which signals pushed the score up/down, how consistent the evidence confidence is, and how the rules score compares to ML and final trust score.
                  </p>
                  <div className="xai-meta-row">
                    <div className="xai-pill">Base: {xai.base_score}</div>
                    <div className="xai-pill">Rules: {xai.rules_score}</div>
                    <div className="xai-pill">ML: {investigation.ml_score}</div>
                    <div className="xai-pill">Final: {investigation.trust_score}</div>
                    <div className="xai-pill">Coverage: {xai.signal_coverage_percent}%</div>
                  </div>
                  <div className="xai-why">
                    <h4>Why this score?</h4>
                    <ul>
                      {(xai.contributions || []).slice(0, 5).map((c) => (
                        <li key={`${c.factor}-${c.signal || ""}`}>
                          <strong>{c.delta >= 0 ? `+${c.delta}` : c.delta}</strong> {c.factor} — {c.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="mini-charts-grid">
                    <div className="chart-wrap">
                      <h4 className="chart-title">Feature Contributions</h4>
                      <p className="chart-note">Bars to the right increase trust; bars to the left reduce trust.</p>
                      <ResponsiveContainer width="100%" height={260}>
                        <BarChart data={xaiContributions} layout="vertical" margin={{ left: 20, right: 18, top: 8, bottom: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.14)" />
                          <XAxis type="number" />
                          <YAxis type="category" dataKey="factor" width={140} />
                          <Tooltip />
                          <Bar dataKey="delta" radius={[8, 8, 8, 8]}>
                            {xaiContributions.map((row) => (
                              <Cell key={row.factor} fill={row.delta >= 0 ? "#2643d5" : "#b43a3a"} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>

                    <div className="chart-wrap">
                      <h4 className="chart-title">Evidence Confidence</h4>
                      <p className="chart-note">Higher confidence means the factor was verified more strongly.</p>
                      <ResponsiveContainer width="100%" height={260}>
                        <PieChart>
                          <Pie data={xaiConfidencePie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={84} innerRadius={46} label>
                            {xaiConfidencePie.map((entry) => (
                              <Cell key={entry.name} fill={entry.fill} />
                            ))}
                          </Pie>
                          <Tooltip />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>

                    <div className="chart-wrap">
                      <h4 className="chart-title">Rules vs ML vs Final</h4>
                      <p className="chart-note">Final score blends rules + ML (calibration).</p>
                      <ResponsiveContainer width="100%" height={260}>
                        <BarChart data={xaiScoreBars}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.14)" />
                          <XAxis dataKey="name" />
                          <YAxis domain={[0, 100]} />
                          <Tooltip />
                          <Bar dataKey="score" fill="#d4632d" radius={[8, 8, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </motion.div>
              ) : null}
            </motion.div>
          ) : null}
        </motion.section>
      ) : null}

      {tab === "compare" ? (
        <motion.section
          className="card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, ease: "easeOut" }}
        >
          <h2>Compare Two Targets</h2>
          <form className="compare-grid" onSubmit={runCompare}>
            <div>
              <label>Left Target</label>
              <input value={compareInput.leftTarget} onChange={(e) => setCompareInput((p) => ({ ...p, leftTarget: e.target.value }))} required />
              <select value={compareInput.leftCategory} onChange={(e) => setCompareInput((p) => ({ ...p, leftCategory: e.target.value }))}>
                {categoryOptions.map(([label, value]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>
            <div>
              <label>Right Target</label>
              <input value={compareInput.rightTarget} onChange={(e) => setCompareInput((p) => ({ ...p, rightTarget: e.target.value }))} required />
              <select value={compareInput.rightCategory} onChange={(e) => setCompareInput((p) => ({ ...p, rightCategory: e.target.value }))}>
                {categoryOptions.map(([label, value]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>
            <button type="submit" className="btn-primary">Run Compare</button>
          </form>

          {comparison ? (
            <div className="result-grid">
              <div className="metric-card"><span>Verdict</span><strong>{comparison.verdict}</strong></div>
              <div className="metric-card"><span>Score Delta</span><strong>{comparison.score_delta}</strong></div>
              <div className="metric-card"><span>Left</span><strong>{comparison.left?.trust_score}</strong></div>
              <div className="metric-card"><span>Right</span><strong>{comparison.right?.trust_score}</strong></div>
              <div className="wide-card">
                <h3>Compare XAI Summary</h3>
                <div className="compare-insight-grid">
                  <article className="compare-insight-card">
                    <h4>Left Target Reason</h4>
                    <p>{topReasonLine(comparison.left)}</p>
                    <ul>
                      {(comparison.left?.why_score?.top_negative_factors || []).slice(0, 2).map((f) => (
                        <li key={`left-neg-${f.factor}`}>Risk: {f.factor} ({f.delta})</li>
                      ))}
                      {(comparison.left?.why_score?.top_positive_factors || []).slice(0, 2).map((f) => (
                        <li key={`left-pos-${f.factor}`}>Strength: {f.factor} (+{f.delta})</li>
                      ))}
                    </ul>
                    <div className="chart-wrap">
                      <h4 className="chart-title">Left Gauge</h4>
                      <ResponsiveContainer width="100%" height={220}>
                        <RadialBarChart
                          cx="50%"
                          cy="62%"
                          innerRadius="56%"
                          outerRadius="92%"
                          barSize={18}
                          data={[{ name: "Left Score", value: comparison.left?.trust_score || 0, fill: riskGaugeColor(comparison.left?.trust_score || 0) }]}
                          startAngle={210}
                          endAngle={-30}
                        >
                          <RadialBar background clockWise dataKey="value" cornerRadius={10} />
                          <text x="50%" y="56%" textAnchor="middle" dominantBaseline="middle" className="gauge-score-text">
                            {comparison.left?.trust_score || 0}
                          </text>
                        </RadialBarChart>
                      </ResponsiveContainer>
                    </div>
                  </article>

                  <article className="compare-insight-card">
                    <h4>Right Target Reason</h4>
                    <p>{topReasonLine(comparison.right)}</p>
                    <ul>
                      {(comparison.right?.why_score?.top_negative_factors || []).slice(0, 2).map((f) => (
                        <li key={`right-neg-${f.factor}`}>Risk: {f.factor} ({f.delta})</li>
                      ))}
                      {(comparison.right?.why_score?.top_positive_factors || []).slice(0, 2).map((f) => (
                        <li key={`right-pos-${f.factor}`}>Strength: {f.factor} (+{f.delta})</li>
                      ))}
                    </ul>
                    <div className="chart-wrap">
                      <h4 className="chart-title">Right Gauge</h4>
                      <ResponsiveContainer width="100%" height={220}>
                        <RadialBarChart
                          cx="50%"
                          cy="62%"
                          innerRadius="56%"
                          outerRadius="92%"
                          barSize={18}
                          data={[{ name: "Right Score", value: comparison.right?.trust_score || 0, fill: riskGaugeColor(comparison.right?.trust_score || 0) }]}
                          startAngle={210}
                          endAngle={-30}
                        >
                          <RadialBar background clockWise dataKey="value" cornerRadius={10} />
                          <text x="50%" y="56%" textAnchor="middle" dominantBaseline="middle" className="gauge-score-text">
                            {comparison.right?.trust_score || 0}
                          </text>
                        </RadialBarChart>
                      </ResponsiveContainer>
                    </div>
                  </article>
                </div>
              </div>

              {(comparison.left?.xai || comparison.right?.xai) ? (
                <div className="wide-card">
                  <h3>Compare XAI Breakdown</h3>
                  <p>Pick a side to see contributions, confidence, and score composition.</p>
                  <div className="switch-tabs center">
                    <button className={compareXaiSide === "left" ? "tab active" : "tab"} onClick={() => setCompareXaiSide("left")} type="button">
                      Left XAI
                    </button>
                    <button className={compareXaiSide === "right" ? "tab active" : "tab"} onClick={() => setCompareXaiSide("right")} type="button">
                      Right XAI
                    </button>
                  </div>

                  {(() => {
                    const sideResult = compareXaiSide === "right" ? comparison.right : comparison.left;
                    const sideXai = sideResult?.xai || null;
                    if (!sideXai) return <p className="chart-note">No XAI payload available for this side.</p>;

                    const contributions = buildXaiContributions(sideXai);
                    const confidencePie = buildXaiConfidencePie(sideXai, contributions);
                    const scoreBars = buildXaiScoreBars(sideResult, sideXai);

                    return (
                      <div className="mini-charts-grid">
                        <div className="chart-wrap">
                          <h4 className="chart-title">Feature Contributions</h4>
                          <p className="chart-note">Bars to the right increase trust; bars to the left reduce trust.</p>
                          <ResponsiveContainer width="100%" height={260}>
                            <BarChart data={contributions} layout="vertical" margin={{ left: 20, right: 18, top: 8, bottom: 8 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.14)" />
                              <XAxis type="number" />
                              <YAxis type="category" dataKey="factor" width={140} />
                              <Tooltip />
                              <Bar dataKey="delta" radius={[8, 8, 8, 8]}>
                                {contributions.map((row) => (
                                  <Cell key={row.factor} fill={row.delta >= 0 ? "#2643d5" : "#b43a3a"} />
                                ))}
                              </Bar>
                            </BarChart>
                          </ResponsiveContainer>
                        </div>

                        <div className="chart-wrap">
                          <h4 className="chart-title">Evidence Confidence</h4>
                          <p className="chart-note">Higher confidence means the factor was verified more strongly.</p>
                          <ResponsiveContainer width="100%" height={260}>
                            <PieChart>
                              <Pie data={confidencePie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={84} innerRadius={46} label>
                                {confidencePie.map((entry) => (
                                  <Cell key={entry.name} fill={entry.fill} />
                                ))}
                              </Pie>
                              <Tooltip />
                            </PieChart>
                          </ResponsiveContainer>
                        </div>

                        <div className="chart-wrap">
                          <h4 className="chart-title">Rules vs ML vs Final</h4>
                          <p className="chart-note">Final score blends rules + ML (calibration).</p>
                          <ResponsiveContainer width="100%" height={260}>
                            <BarChart data={scoreBars}>
                              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.14)" />
                              <XAxis dataKey="name" />
                              <YAxis domain={[0, 100]} />
                              <Tooltip />
                              <Bar dataKey="score" fill="#d4632d" radius={[8, 8, 0, 0]} />
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              ) : null}
            </div>
          ) : null}
        </motion.section>
      ) : null}

      {tab === "history" ? (
        <motion.section
          className="card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, ease: "easeOut" }}
        >
          <div className="history-head">
            <h2>History & Analytics</h2>
            <button className="btn-primary" onClick={loadHistory}>Refresh</button>
          </div>

          {history.length ? (
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#ccd8d2" />
                  <XAxis dataKey="created_at" hide />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="trust_score" stroke="#0a7f6f" strokeWidth={3} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : null}

          {analytics.length ? (
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={analytics}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#ccd8d2" />
                  <XAxis dataKey="target" hide />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="avg_score" fill="#d87434" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : null}
        </motion.section>
      ) : null}

      {tab === "policies" ? (
        <motion.section
          className="card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, ease: "easeOut" }}
        >
          <h2>Category Policies</h2>
          <div className="policy-grid">
            {Object.entries(POLICY_CHECKS).map(([key, checks]) => (
              <article key={key} className="policy-card">
                <h3>{key.toUpperCase()}</h3>
                <ol>
                  {checks.map((check) => (
                    <li key={check}>{check}</li>
                  ))}
                </ol>
              </article>
            ))}
          </div>
        </motion.section>
      ) : null}
    </Layout>
  );
}
