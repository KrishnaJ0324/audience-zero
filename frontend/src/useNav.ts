import { useCallback, useEffect, useState } from "react";

export type Route =
  | { view: "projects" }
  | { view: "personas" }
  | { view: "project"; id: string }
  | { view: "episode"; id: string }
  | { view: "run"; id: string; sweep?: boolean }
  | { view: "shared"; token: string };

function parse(): Route {
  const hash = window.location.hash.replace(/^#/, "");
  const [path, query] = hash.split("?");
  const parts = path.split("/").filter(Boolean); // ["run","run_x"]
  const q = new URLSearchParams(query);
  if (parts[0] === "personas") return { view: "personas" };
  if (parts[0] === "project" && parts[1]) return { view: "project", id: parts[1] };
  if (parts[0] === "episode" && parts[1]) return { view: "episode", id: parts[1] };
  if (parts[0] === "run" && parts[1]) return { view: "run", id: parts[1], sweep: q.get("sweep") === "1" };
  if (parts[0] === "shared" && parts[1]) return { view: "shared", token: parts[1] };
  return { view: "projects" };
}

export function useNav() {
  const [route, setRoute] = useState<Route>(parse());

  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const go = useCallback((to: string) => {
    window.location.hash = to;
  }, []);

  return { route, go };
}
