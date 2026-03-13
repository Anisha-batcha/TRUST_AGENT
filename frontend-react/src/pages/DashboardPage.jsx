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

  const [investigateInput, setInvestigateInput] = useState({ target: "", category: "instagram" });
  const [investigation, setInvestigation] = useState(null);

  const [compareInput, setCompareInput] = useState({ leftTarget: "", leftCategory: "instagram", rightTarget: "", rightCategory: "instagram" });
  const [comparison, setComparison] = useState(null);

  const [history, setHistory] = useState([]);
  const [analytics, setAnalytics] = useState([]);

  const runInvestigate = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.post("/investigate", investigateInput, { timeout: 120000 });
      setInvestigation(res.data);
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
          transition={{ duration: 0.65, ease: "easeOut" }}
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
              <motion.div className="metric-card" variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}><span>Trust Score</span><strong>{investigation.trust_score}</strong></motion.div>
              <motion.div className="metric-card" variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}><span>Risk</span><strong>{investigation.risk_level}</strong></motion.div>
              <motion.div className="metric-card" variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}><span>Confidence</span><strong>{Math.round((investigation.confidence_score || 0) * 100)}%</strong></motion.div>
              <motion.div className="metric-card" variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}><span>ML Score</span><strong>{investigation.ml_score}</strong></motion.div>
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
