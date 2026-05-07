import { Navigate, useLocation } from "react-router-dom";
import { useApiSettings } from "../context/ApiSettingsContext";

export function ProtectedRoute({ children }: { children: JSX.Element }) {
  const {
    settings: { token },
  } = useApiSettings();
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }

  return children;
}
