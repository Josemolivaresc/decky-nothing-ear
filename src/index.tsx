import {
  ButtonItem,
  ConfirmModal,
  DialogButton,
  DropdownItem,
  Field,
  Focusable,
  PanelSection,
  PanelSectionRow,
  SliderField,
  ToggleField,
  showModal,
  staticClasses,
} from "@decky/ui";
import {
  addEventListener,
  removeEventListener,
  callable,
  definePlugin,
  toaster,
} from "@decky/api";
import { ReactNode, useEffect, useRef, useState } from "react";
import {
  MdBolt,
  MdExpandLess,
  MdExpandMore,
  MdGraphicEq,
  MdHeadphones,
  MdHearing,
  MdNoiseAware,
  MdNoiseControlOff,
  MdNotificationsActive,
  MdRefresh,
  MdSensors,
  MdSpatialAudio,
  MdSportsEsports,
  MdSurroundSound,
} from "react-icons/md";

// ---------------------------------------------------------------- tipos

type Battery = { level: number; charging: boolean };
type Option<T> = { value: T; label: string };
type Gesture = {
  id: string;
  group: string;
  group_label: string;
  label: string;
  options: Option<number>[];
};

type Caps = {
  anc_modes: string[];
  personalized_anc: boolean;
  low_latency: boolean;
  eq_presets: Option<string>[];
  custom_eq: boolean;
  bass_levels: number;
  in_ear: boolean;
  spatial: boolean;
  ring: null | "legacy" | "single" | "dual";
  gestures: Gesture[];
};

type State = {
  connected: boolean;
  name: string | null;
  model: string | null;
  model_name: string | null;
  firmware: string | null;
  serial: string | null;
  error: string | null;
  caps: Caps;
  battery: { left?: Battery; right?: Battery; case?: Battery; single?: Battery };
  anc: string | null;
  personalized_anc: boolean | null;
  low_latency: boolean | null;
  eq_preset: string | null;
  custom_eq: [number, number, number] | null;
  bass: { enabled: boolean; level: number } | null;
  in_ear: boolean | null;
  spatial: boolean | null;
  ring: { left: boolean; right: boolean; single: boolean };
  gestures: Record<string, number>;
};

const getState = callable<[], State>("get_state");
const reconnect = callable<[], State>("reconnect");
const setOption = callable<[key: string, value: unknown], State>("set");

// ---------------------------------------------------------------- estilos

const RED = "#D71921"; // el rojo de Nothing

const CSS = `
.ne-batt { display: flex; gap: 6px; width: 100%; }
.ne-tile {
  flex: 1; border-radius: 10px; padding: 8px 6px 7px;
  background: rgba(255,255,255,0.06); text-align: center;
}
.ne-tile-label { font-size: 10px; letter-spacing: 1px; text-transform: uppercase; opacity: 0.6; }
.ne-tile-value {
  font-size: 22px; font-weight: 600; line-height: 1.2;
  display: flex; align-items: center; justify-content: center; gap: 2px;
}
.ne-tile-value small { font-size: 12px; font-weight: 400; opacity: 0.7; }
.ne-bar { height: 3px; border-radius: 2px; background: rgba(255,255,255,0.12); margin-top: 5px; overflow: hidden; }
.ne-bar > div { height: 100%; border-radius: 2px; background: #fff; }
.ne-row { display: flex; gap: 5px; width: 100%; }
.ne-row .ne-btn {
  flex: 1 1 0; min-width: 0 !important; width: auto !important; padding: 8px 3px 7px !important;
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  border-radius: 10px !important; overflow: hidden;
  background: rgba(255,255,255,0.06) !important; color: #dcdedf !important;
}
.ne-row .ne-btn span {
  display: block; max-width: 100%; font-size: 10px; line-height: 1.15;
  letter-spacing: -0.1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ne-row .ne-btn svg { font-size: 22px; }
.ne-row .ne-btn.ne-on { background: #fff !important; color: #111 !important; }
.ne-row .ne-chip {
  flex: 1 1 0; min-width: 0 !important; width: auto !important; padding: 6px 2px !important;
  font-size: 10px; line-height: 1.15; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  border-radius: 14px !important; background: rgba(255,255,255,0.06) !important;
  color: #dcdedf !important;
}
.ne-row .ne-chip.ne-on { background: #fff !important; color: #111 !important; }
.ne-ring.ne-on { background: ${RED} !important; color: #fff !important; }
.ne-sub { font-size: 11px; opacity: 0.6; margin: 2px 0 4px; }
.ne-dot { display: inline-block; width: 6px; height: 6px; border-radius: 3px; background: ${RED}; margin-right: 6px; vertical-align: middle; }
`;

// ---------------------------------------------------------------- piezas

function BatteryTile({ label, b }: { label: string; b?: Battery }) {
  const low = b && !b.charging && b.level <= 20;
  return (
    <div className="ne-tile">
      <div className="ne-tile-label">{label}</div>
      <div className="ne-tile-value" style={low ? { color: RED } : undefined}>
        {b ? (
          <>
            {b.level}
            <small>%</small>
            {b.charging && <MdBolt style={{ fontSize: 15 }} />}
          </>
        ) : (
          <small>—</small>
        )}
      </div>
      <div className="ne-bar">
        <div style={{ width: `${b?.level ?? 0}%`, background: low ? RED : "#fff" }} />
      </div>
    </div>
  );
}

function ButtonRow({ children }: { children: ReactNode }) {
  return (
    <Focusable className="ne-row" flow-children="right" style={{ display: "flex" }}>
      {children}
    </Focusable>
  );
}

const ANC_MAIN: { key: string; label: string; icon: ReactNode }[] = [
  { key: "off", label: "Apagado", icon: <MdNoiseControlOff /> },
  { key: "transparency", label: "Transparencia", icon: <MdHearing /> },
  { key: "anc", label: "Cancelación", icon: <MdNoiseAware /> },
];

const ANC_LEVELS: Option<string>[] = [
  { value: "adaptive", label: "Adaptativa" },
  { value: "high", label: "Alta" },
  { value: "mid", label: "Media" },
  { value: "low", label: "Baja" },
];

// Hacer sonar los auriculares es muy fuerte: dos avisos antes de empezar
function confirmRing(label: string): Promise<boolean> {
  const ask = (props: { title: string; text: ReactNode; ok: string }) =>
    new Promise<boolean>((resolve) => {
      let done = false;
      const finish = (v: boolean) => {
        if (!done) {
          done = true;
          resolve(v);
        }
      };
      showModal(
        <ConfirmModal
          strTitle={props.title}
          strDescription={props.text}
          strOKButtonText={props.ok}
          strCancelButtonText="Cancelar"
          onOK={() => finish(true)}
          onCancel={() => finish(false)}
        />
      );
    });

  return ask({
    title: "⚠️ Sonido muy fuerte",
    text: (
      <>
        El auricular va a emitir un pitido <b>a todo volumen</b> para que puedas
        encontrarlo. Si alguien lo lleva puesto puede dañarle el oído.
      </>
    ),
    ok: "Entendido",
  }).then(
    (first) =>
      first &&
      ask({
        title: "¿Seguro que nadie lo lleva puesto?",
        text: `Confirma que el auricular (${label.toLowerCase()}) no está en el oído de nadie.`,
        ok: "Hacer sonar",
      })
  );
}

const isCancelMode = (m: string | null) =>
  m !== null && m !== "off" && m !== "transparency";

// ---------------------------------------------------------------- panel

function Content() {
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [showGestures, setShowGestures] = useState(false);
  const eqTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    getState().then(setState);
    const listener = addEventListener<[State]>("state", (s) => setState(s));
    return () => {
      removeEventListener("state", listener);
      window.clearTimeout(eqTimer.current);
    };
  }, []);

  if (!state) return null;

  // Cambia el panel al momento y luego aplica lo que diga el auricular
  const change = async (key: string, value: unknown, local: Partial<State>) => {
    setState((s) => (s ? { ...s, ...local } : s));
    try {
      setState(await setOption(key, value));
    } catch (e) {
      toaster.toast({ title: "Nothing", body: String(e).replace(/^Error: /, "") });
      getState().then(setState);
    }
  };

  if (!state.connected) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <div className="ne-sub" style={{ padding: "4px 0" }}>
            {state.error ?? "Sin auriculares Nothing conectados"}. El panel aparecerá en
            cuanto se conecten.
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                setState(await reconnect());
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Buscando…" : "Buscar ahora"}
          </ButtonItem>
        </PanelSectionRow>
        <style>{CSS}</style>
      </PanelSection>
    );
  }

  const { caps, battery: b } = state;

  // Cancelación: botones principales según lo que admita el modelo
  const levels = ANC_LEVELS.filter((l) => caps.anc_modes.includes(l.value));
  const singleAnc = caps.anc_modes.includes("anc");
  const mainButtons = ANC_MAIN.filter((m) =>
    m.key === "anc" ? singleAnc || levels.length > 0 : caps.anc_modes.includes(m.key)
  );
  const currentMain = isCancelMode(state.anc) ? "anc" : state.anc;
  const pickMain = (key: string) => {
    if (key !== "anc") return change("anc", key, { anc: key });
    if (singleAnc) return change("anc", "anc", { anc: "anc" });
    const level = isCancelMode(state.anc) ? state.anc! : levels[0].value;
    return change("anc", level, { anc: level });
  };

  const eq = state.custom_eq ?? [0, 0, 0];
  const setEqBand = (i: number, v: number) => {
    const next = [...eq] as [number, number, number];
    next[i] = v;
    setState((s) => (s ? { ...s, custom_eq: next } : s));
    // Espera a que se suelte el slider para no saturar el Bluetooth
    window.clearTimeout(eqTimer.current);
    eqTimer.current = window.setTimeout(() => change("custom_eq", next, {}), 500);
  };

  const gestureGroups = caps.gestures.reduce<Record<string, Gesture[]>>((acc, g) => {
    (acc[g.group_label] ??= []).push(g);
    return acc;
  }, {});

  const ringButtons =
    caps.ring === "dual"
      ? [
          { target: "left", label: "Izquierdo" },
          { target: "right", label: "Derecho" },
        ]
      : caps.ring
        ? [{ target: "single", label: "Hacer sonar" }]
        : [];

  return (
    <>
      <style>{CSS}</style>

      {/* ---- Batería */}
      <PanelSection title={state.name ?? state.model_name ?? "Nothing"}>
        <PanelSectionRow>
          <div className="ne-batt">
            {b.single ? (
              <BatteryTile label="Batería" b={b.single} />
            ) : (
              <>
                <BatteryTile label="Izq." b={b.left} />
                <BatteryTile label="Estuche" b={b.case} />
                <BatteryTile label="Der." b={b.right} />
              </>
            )}
          </div>
        </PanelSectionRow>
      </PanelSection>

      {/* ---- Control de ruido */}
      {mainButtons.length > 0 && (
        <PanelSection title="Control de ruido">
          <PanelSectionRow>
            <ButtonRow>
              {mainButtons.map((m) => (
                <DialogButton
                  key={m.key}
                  className={`ne-btn ${currentMain === m.key ? "ne-on" : ""}`}
                  onClick={() => pickMain(m.key)}
                >
                  {m.icon}
                  <span>{m.label}</span>
                </DialogButton>
              ))}
            </ButtonRow>
          </PanelSectionRow>
          {isCancelMode(state.anc) && levels.length > 0 && (
            <PanelSectionRow>
              <div style={{ marginTop: 8 }}>
                <ButtonRow>
                  {levels.map((l) => (
                    <DialogButton
                      key={l.value}
                      className={`ne-chip ${state.anc === l.value ? "ne-on" : ""}`}
                      onClick={() => change("anc", l.value, { anc: l.value })}
                    >
                      {l.label}
                    </DialogButton>
                  ))}
                </ButtonRow>
              </div>
            </PanelSectionRow>
          )}
        </PanelSection>
      )}

      {/* ---- Juego */}
      {(caps.low_latency || caps.spatial) && (
        <PanelSection title="Juego">
          {caps.low_latency && (
            <PanelSectionRow>
              <ToggleField
                icon={<MdSportsEsports />}
                label="Baja latencia"
                description="Reduce el retardo del audio"
                checked={!!state.low_latency}
                onChange={(v) => change("low_latency", v, { low_latency: v })}
              />
            </PanelSectionRow>
          )}
          {caps.spatial && (
            <PanelSectionRow>
              <ToggleField
                icon={<MdSpatialAudio />}
                label="Audio espacial"
                checked={!!state.spatial}
                onChange={(v) => change("spatial", v, { spatial: v })}
              />
            </PanelSectionRow>
          )}
        </PanelSection>
      )}

      {/* ---- Sonido */}
      {(caps.eq_presets.length > 0 || caps.bass_levels > 0) && (
        <PanelSection title="Sonido">
          {caps.eq_presets.length > 0 && (
            <PanelSectionRow>
              <DropdownItem
                label={
                  <span>
                    <MdGraphicEq style={{ verticalAlign: "middle", marginRight: 6 }} />
                    Ecualizador
                  </span>
                }
                rgOptions={caps.eq_presets.map((p) => ({ data: p.value, label: p.label }))}
                selectedOption={state.eq_preset}
                onChange={(o) => change("eq_preset", o.data, { eq_preset: o.data })}
              />
            </PanelSectionRow>
          )}
          {caps.custom_eq &&
            state.eq_preset === "custom" &&
            ["Graves", "Medios", "Agudos"].map((band, i) => (
              <PanelSectionRow key={band}>
                <SliderField
                  label={band}
                  value={eq[i]}
                  min={-6}
                  max={6}
                  step={0.5}
                  showValue
                  valueSuffix=" dB"
                  resetValue={0}
                  notchCount={3}
                  notchLabels={[
                    { notchIndex: 0, label: "-6" },
                    { notchIndex: 1, label: "0" },
                    { notchIndex: 2, label: "+6" },
                  ]}
                  onChange={(v) => setEqBand(i, v)}
                />
              </PanelSectionRow>
            ))}
          {caps.bass_levels > 0 && (
            <>
              <PanelSectionRow>
                <ToggleField
                  icon={<MdSurroundSound />}
                  label="Realce de graves"
                  checked={!!state.bass?.enabled}
                  onChange={(v) =>
                    change("bass", { enabled: v }, {
                      bass: { enabled: v, level: state.bass?.level ?? 1 },
                    })
                  }
                />
              </PanelSectionRow>
              {state.bass?.enabled && (
                <PanelSectionRow>
                  <SliderField
                    label="Intensidad"
                    value={state.bass.level}
                    min={1}
                    max={caps.bass_levels}
                    step={1}
                    notchCount={caps.bass_levels}
                    notchTicksVisible
                    showValue
                    onChange={(v) =>
                      change("bass", { level: v }, { bass: { enabled: true, level: v } })
                    }
                  />
                </PanelSectionRow>
              )}
            </>
          )}
        </PanelSection>
      )}

      {/* ---- Ajustes */}
      {(caps.in_ear || caps.ring) && (
        <PanelSection title="Ajustes">
          {caps.in_ear && (
            <PanelSectionRow>
              <ToggleField
                icon={<MdSensors />}
                label="Detección en el oído"
                description="Pausa al quitártelos"
                checked={!!state.in_ear}
                onChange={(v) => change("in_ear", v, { in_ear: v })}
              />
            </PanelSectionRow>
          )}
          {caps.ring && (
            <PanelSectionRow>
              <Field
                label={
                  <span>
                    <MdNotificationsActive style={{ verticalAlign: "middle", marginRight: 6 }} />
                    Buscar auriculares
                  </span>
                }
                childrenLayout="below"
                bottomSeparator="none"
              >
                <ButtonRow>
                  {ringButtons.map(({ target, label }) => {
                    const on = state.ring[target as keyof State["ring"]];
                    return (
                      <DialogButton
                        key={target}
                        className={`ne-chip ne-ring ${on ? "ne-on" : ""}`}
                        onClick={async () => {
                          if (!on && !(await confirmRing(label))) return;
                          change("ring", { target, playing: !on }, {
                            ring: { ...state.ring, [target]: !on },
                          });
                        }}
                      >
                        {on ? "■ Parar" : label}
                      </DialogButton>
                    );
                  })}
                </ButtonRow>
              </Field>
            </PanelSectionRow>
          )}
        </PanelSection>
      )}

      {/* ---- Gestos */}
      {caps.gestures.length > 0 && (
        <PanelSection title="Gestos">
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => setShowGestures((v) => !v)}>
              <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
                {showGestures ? <MdExpandLess /> : <MdExpandMore />}
                {showGestures ? "Ocultar gestos" : "Configurar gestos"}
              </span>
            </ButtonItem>
          </PanelSectionRow>
          {showGestures &&
            Object.entries(gestureGroups).map(([group, gestures]) => (
              <div key={group}>
                <PanelSectionRow>
                  <div className="ne-sub" style={{ marginTop: 8 }}>
                    <span className="ne-dot" />
                    {group}
                  </div>
                </PanelSectionRow>
                {gestures.map((g) => {
                  const current = state.gestures[g.id];
                  const known = g.options.some((o) => o.value === current);
                  const options = g.options.map((o) => ({ data: o.value, label: o.label }));
                  if (current !== undefined && !known)
                    options.unshift({ data: current, label: "Otra acción" });
                  return (
                    <PanelSectionRow key={g.id}>
                      <DropdownItem
                        label={g.label}
                        rgOptions={options}
                        selectedOption={current ?? null}
                        onChange={(o) =>
                          change("gesture", { id: g.id, action: o.data }, {
                            gestures: { ...state.gestures, [g.id]: o.data },
                          })
                        }
                      />
                    </PanelSectionRow>
                  );
                })}
              </div>
            ))}
        </PanelSection>
      )}

      {/* ---- Dispositivo */}
      <PanelSection title="Dispositivo">
        <PanelSectionRow>
          <Field label="Modelo" bottomSeparator="none" padding="compact">
            {state.model_name ?? state.model ?? "—"}
          </Field>
        </PanelSectionRow>
        {state.firmware && (
          <PanelSectionRow>
            <Field label="Firmware" bottomSeparator="none" padding="compact">
              {state.firmware}
            </Field>
          </PanelSectionRow>
        )}
        {state.serial && (
          <PanelSectionRow>
            <Field label="Nº de serie" bottomSeparator="none" padding="compact">
              {state.serial}
            </Field>
          </PanelSectionRow>
        )}
        {!state.model_name && (
          <PanelSectionRow>
            <div className="ne-sub">Modelo no reconocido: solo se muestra la batería.</div>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                setState(await reconnect());
              } finally {
                setBusy(false);
              }
            }}
          >
            <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
              <MdRefresh /> Reconectar
            </span>
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  // Aviso al conectar o desconectar, aunque el panel esté cerrado
  let wasConnected: boolean | null = null;
  const listener = addEventListener<[State]>("state", (s) => {
    if (wasConnected !== null && s.connected !== wasConnected) {
      const b = s.battery;
      const level = b.single?.level ?? (b.left && b.right ? Math.min(b.left.level, b.right.level) : undefined);
      toaster.toast({
        title: s.name ?? s.model_name ?? "Nothing",
        body: s.connected ? `Conectados${level !== undefined ? ` · ${level}%` : ""}` : "Desconectados",
        icon: <MdHeadphones />,
      });
    }
    wasConnected = s.connected;
  });
  getState().then((s) => (wasConnected = s.connected));

  return {
    name: "Nothing Ear",
    titleView: <div className={staticClasses.Title}>Nothing Ear</div>,
    content: <Content />,
    icon: <MdHeadphones />,
    onDismount() {
      removeEventListener("state", listener);
    },
  };
});
