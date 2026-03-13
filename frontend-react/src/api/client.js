import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 45000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("trustagent_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err?.response?.status;
    const detail = err?.response?.data?.detail;
    if (status === 401 && typeof detail === "string" && detail.toLowerCase().includes("token")) {
      localStorage.removeItem("trustagent_token");
      localStorage.removeItem("trustagent_user");
      // Force UI back to auth flow if an expired/invalid token was cached.
      if (typeof window !== "undefined") {
        window.location.href = "/";
      }
    }
    return Promise.reject(err);
  }
);

export default api;
