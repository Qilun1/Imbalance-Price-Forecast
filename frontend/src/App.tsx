import { useEffect, useState } from "react";

import { getMeta, type Meta } from "./api/client";

/** Wiring check only: proves the frontend reaches the API. The dashboard itself is not designed yet. */
export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMeta().then(setMeta).catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p>API not reachable: {error}</p>;
  if (!meta) return <p>Connecting to the API</p>;
  return <p>API connected ({meta.mode} data). {meta.note}</p>;
}
