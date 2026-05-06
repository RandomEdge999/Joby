"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import BrandLogo from "../_components/BrandLogo";

type Preset = { key: string; name: string; preset: string };

export default function Onboarding() {
  const router = useRouter();
  const [presets, setPresets] = useState<Preset[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    api<{ presets: Preset[] }>("/api/profile/presets").then((r) => setPresets(r.presets));
  }, []);

  async function choose(key: string) {
    setSelected(key);
    setSaving(true);
    setError("");
    try {
      const profile = await api<any>(`/api/profile/presets/${key}`);
      await api("/api/profile", { method: "PUT", body: JSON.stringify(profile) });
      router.push("/settings");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-4 max-w-4xl mx-auto">
      <div className="rounded-[28px] border border-white/70 bg-white/75 p-6 shadow-card backdrop-blur-xl">
      <div className="flex flex-col gap-3">
        <BrandLogo className="h-14 w-auto" priority />
        <div>
          <h1 className="text-2xl font-semibold">Choose a starting profile</h1>
          <p className="text-slate-600">Pick a preset to get started. You can fine-tune everything later in Settings.</p>
        </div>
      </div>
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        {presets.map((p) => (
          <button key={p.key} disabled={saving}
                  onClick={() => choose(p.key)}
                  className={`card text-left hover:bg-slate-50 ${selected === p.key ? "ring-2 ring-slate-800" : ""}`}>
            <div className="font-medium">{p.name}</div>
            <div className="text-xs text-slate-500 mt-1">{p.preset}</div>
          </button>
        ))}
      </div>

      {error && <div className="text-rose-700 text-sm">{error}</div>}
      {saving && <div className="text-slate-600 text-sm">Saving profile…</div>}
    </div>
  );
}
