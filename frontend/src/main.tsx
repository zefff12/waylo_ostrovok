import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { SupportAdmin } from "./components/Support";
import "./styles.css";

// /support-admin — страница сотрудника поддержки, остальное — приложение
const admin = location.pathname.startsWith("/support-admin");
createRoot(document.getElementById("root")!).render(<StrictMode>{admin ? <SupportAdmin /> : <App />}</StrictMode>);
