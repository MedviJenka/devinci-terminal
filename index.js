#!/usr/bin/env node
"use strict";

const readline = require("node:readline");

const PIPELINE_STAGES = Object.freeze([
  { name: "Intake", description: "Capture goal, constraints, and acceptance criteria" },
  { name: "Spawn", description: "Assign agents by role and slice independent work" },
  { name: "Execute", description: "Run slice work while streaming status and logs" },
  { name: "Review", description: "Challenge outputs, resolve conflicts, and verify evidence" },
  { name: "Consensus", description: "Promote agreed findings and surface dissent" },
  { name: "Ship", description: "Package final artifact with verification notes" },
]);

const AGENT_ROLES = Object.freeze(["Planner", "Builder", "Reviewer", "Verifier", "Scribe"]);
const MAX_EVENTS = 8;

const CONTROL_ACTIONS = Object.freeze([
  { action: "next", key: "n", label: "Next" },
  { action: "agent", key: "a", label: "Agent" },
  { action: "flag", key: "f", label: "Flag" },
  { action: "reset", key: "r", label: "Reset" },
  { action: "quit", key: "q", label: "Quit" },
]);

const ANSI_PATTERN = /\x1b\[[0-?]*[ -/]*[@-~]/g;
const RESET = "\x1b[0m";
const BOLD = "\x1b[1m";
const DIM = "\x1b[2m";
const OH_MY_PI = Object.freeze({
  cyan: [74, 222, 255],
  violet: [168, 85, 247],
  pink: [236, 72, 153],
  lime: [163, 230, 53],
  amber: [251, 191, 36],
  red: [248, 113, 113],
  slate: [148, 163, 184],
});

function rgb([r, g, b]) {
  return `\x1b[38;2;${r};${g};${b}m`;
}

function bgRgb([r, g, b]) {
  return `\x1b[48;2;${r};${g};${b}m`;
}

function paint(text, fg, { bold = false, dim = false, bg } = {}) {
  const prefix = `${bold ? BOLD : ""}${dim ? DIM : ""}${fg ? rgb(fg) : ""}${bg ? bgRgb(bg) : ""}`;
  return prefix ? `${prefix}${text}${RESET}` : text;
}

function stripAnsi(text) {
  return String(text).replace(ANSI_PATTERN, "");
}

function visibleLength(text) {
  return stripAnsi(text).length;
}

function gradient(text, from, to) {
  const chars = [...String(text)];
  const span = Math.max(1, chars.length - 1);
  return chars
    .map((char, index) => {
      if (char === " ") return char;
      const color = from.map((start, channel) => Math.round(start + ((to[channel] - start) * index) / span));
      return `${rgb(color)}${char}`;
    })
    .join("") + RESET;
}

function createDefaultPipeline() {
  return {
    cursor: 0,
    stages: PIPELINE_STAGES.map((stage, index) => ({
      ...stage,
      status: index === 0 ? "active" : "pending",
    })),
  };
}

function advancePipeline(pipeline) {
  const nextStages = pipeline.stages.map((stage) => ({ ...stage }));
  const activeIndex = nextStages.findIndex((stage) => stage.status === "active" || stage.status === "failed");

  if (activeIndex === -1) {
    return {
      cursor: nextStages.length - 1,
      stages: nextStages,
    };
  }

  nextStages[activeIndex].status = "done";
  const nextIndex = activeIndex + 1;
  if (nextIndex < nextStages.length) {
    nextStages[nextIndex].status = "active";
  }

  return {
    cursor: Math.min(nextIndex, nextStages.length - 1),
    stages: nextStages,
  };
}

function failCurrentStage(pipeline) {
  const nextStages = pipeline.stages.map((stage) => ({ ...stage }));
  const activeIndex = nextStages.findIndex((stage) => stage.status === "active");
  if (activeIndex !== -1) {
    nextStages[activeIndex].status = "failed";
    return { cursor: activeIndex, stages: nextStages };
  }
  return { cursor: pipeline.cursor, stages: nextStages };
}

function createAgent(index) {
  return {
    id: `A${String(index + 1).padStart(2, "0")}`,
    name: `Agent ${index + 1}`,
    role: AGENT_ROLES[index % AGENT_ROLES.length],
    status: "ready",
  };
}

function createEventLog(seed = []) {
  return seed.slice(-MAX_EVENTS).map((message, index) => ({
    id: index + 1,
    message,
  }));
}

function pushEvent(events, message) {
  const nextId = events.length > 0 ? events.at(-1).id + 1 : 1;
  return [...events, { id: nextId, message }].slice(-MAX_EVENTS);
}

function statusIcon(status) {
  if (status === "done") return "✓";
  if (status === "active") return "▶";
  if (status === "failed") return "!";
  return "○";
}

function statusLabel(status) {
  if (status === "done") return "done";
  if (status === "active") return "active";
  if (status === "failed") return "blocked";
  return "pending";
}

function clampWidth(width) {
  return Math.max(40, Number.isFinite(width) ? Math.floor(width) : 88);
}

function clampHeight(height) {
  return Math.max(16, Number.isFinite(height) ? Math.floor(height) : 24);
}

function fit(text, width) {
  const value = String(text);
  const length = visibleLength(value);
  if (length === width) return value;
  if (length < width) return `${value}${" ".repeat(width - length)}`;

  const plain = stripAnsi(value);
  if (width <= 1) return plain.slice(0, width);
  return `${plain.slice(0, width - 1)}…`;
}

function center(text, width) {
  const value = String(text);
  const length = visibleLength(value);
  if (length >= width) return fit(value, width);
  const left = Math.floor((width - length) / 2);
  return fit(`${" ".repeat(left)}${value}`, width);
}

function section(title, width, colors = true) {
  const label = ` ${title} `;
  const side = Math.max(0, width - label.length);
  const line = fit(`${label}${"─".repeat(side)}`, width);
  return colors ? paint(line, OH_MY_PI.violet, { dim: true }) : line;
}

function statusColor(status) {
  if (status === "done") return OH_MY_PI.lime;
  if (status === "active") return OH_MY_PI.cyan;
  if (status === "failed") return OH_MY_PI.red;
  return OH_MY_PI.slate;
}

function actionButtonText(control, index, colors = true) {
  const plain = `[${control.key}] ${control.label}`;
  if (!colors) return plain;
  const palette = [OH_MY_PI.cyan, OH_MY_PI.violet, OH_MY_PI.pink, OH_MY_PI.amber, OH_MY_PI.lime];
  return paint(plain, palette[index % palette.length], { bold: true });
}

function actionLayout(width, row) {
  const controls = CONTROL_ACTIONS.map((control) => ({ ...control, text: `[${control.key}] ${control.label}` }));
  const raw = controls.map((control) => control.text).join("  ");
  const leftPadding = Math.max(0, Math.floor((width - raw.length) / 2));
  let cursor = leftPadding;
  const hitboxes = [];

  for (const control of controls) {
    const left = cursor;
    const right = Math.min(width - 1, cursor + control.text.length - 1);
    if (left < width) hitboxes.push({ action: control.action, key: control.key, row, left, right });
    cursor += control.text.length + 2;
  }

  return { leftPadding, hitboxes };
}

function renderActionBar(width, row, colors = true) {
  const { leftPadding } = actionLayout(width, row);
  const buttons = CONTROL_ACTIONS.map((control, index) => actionButtonText(control, index, colors)).join(colors ? paint("  ", OH_MY_PI.slate, { dim: true }) : "  ");
  return fit(`${" ".repeat(leftPadding)}${buttons}`, width);
}

function actionForClick(mouse, width, height) {
  if (mouse.pressed === false || (Number.isInteger(mouse.button) && mouse.button !== 0)) return undefined;

  const columns = clampWidth(width);
  const rows = clampHeight(height);
  const actionRow = rows - 1;
  if (mouse.row !== actionRow) return undefined;

  const { hitboxes } = actionLayout(columns, actionRow);
  const hit = hitboxes.find((box) => mouse.col >= box.left && mouse.col <= box.right);
  return hit?.action;
}

function parseSgrMouse(data) {
  const match = /^\x1b\[<(\d+);(\d+);(\d+)([Mm])/.exec(String(data));
  if (!match) return null;

  return {
    button: Number(match[1]),
    col: Math.max(0, Number(match[2]) - 1),
    row: Math.max(0, Number(match[3]) - 1),
    pressed: match[4] === "M",
  };
}

function renderFrame({ pipeline, agents, events, width = 88, height = 24, colors = true }) {
  const columns = clampWidth(width);
  const rows = clampHeight(height);
  const actionRow = rows - 1;
  const lines = [];

  const title = "Agent Orchestration Pipeline";
  lines.push(center(colors ? gradient(title, OH_MY_PI.cyan, OH_MY_PI.pink) : title, columns));
  lines.push(colors ? gradient("─".repeat(columns), OH_MY_PI.cyan, OH_MY_PI.violet) : fit("─".repeat(columns), columns));
  lines.push(section("Pipeline", columns, colors));

  for (const stage of pipeline.stages) {
    const icon = statusIcon(stage.status);
    const label = `${icon} ${stage.name.padEnd(10)} ${statusLabel(stage.status).padEnd(8)} ${stage.description}`;
    lines.push(colors ? paint(fit(label, columns), statusColor(stage.status), { bold: stage.status === "active" }) : fit(label, columns));
  }

  lines.push(fit("", columns));
  lines.push(section("Agents", columns, colors));
  if (agents.length === 0) {
    const empty = "No agents spawned. Click Agent or press a to add the next role.";
    lines.push(colors ? paint(fit(empty, columns), OH_MY_PI.slate, { dim: true }) : fit(empty, columns));
  } else {
    for (const agent of agents) {
      const label = `${agent.id}  ${agent.name.padEnd(12)} ${agent.role.padEnd(10)} ${agent.status}`;
      lines.push(colors ? paint(fit(label, columns), OH_MY_PI.amber) : fit(label, columns));
    }
  }

  lines.push(fit("", columns));
  lines.push(section("Events", columns, colors));
  if (events.length === 0) {
    lines.push(colors ? paint(fit("No events yet.", columns), OH_MY_PI.slate, { dim: true }) : fit("No events yet.", columns));
  } else {
    for (const event of events) {
      const label = `#${String(event.id).padStart(2, "0")} ${event.message}`;
      lines.push(colors ? paint(fit(label, columns), OH_MY_PI.slate) : fit(label, columns));
    }
  }

  const visible = lines.slice(0, actionRow);
  while (visible.length < actionRow) visible.push(fit("", columns));
  visible.push(renderActionBar(columns, actionRow, colors));
  return visible.map((line) => fit(line, columns)).join("\n");
}

function actionFromKeyName(name) {
  const normalized = String(name || "").toLowerCase();
  return CONTROL_ACTIONS.find((control) => control.key === normalized)?.action;
}

function applyAction(state, action) {
  if (action === "next") {
    const current = state.pipeline.stages[state.pipeline.cursor];
    return {
      ...state,
      pipeline: advancePipeline(state.pipeline),
      events: pushEvent(state.events, `${current.name} completed`),
    };
  }

  if (action === "agent") {
    const agent = createAgent(state.agents.length);
    return {
      ...state,
      agents: [...state.agents, agent],
      events: pushEvent(state.events, `${agent.id} ${agent.role} joined`),
    };
  }

  if (action === "flag") {
    const current = state.pipeline.stages[state.pipeline.cursor];
    return {
      ...state,
      pipeline: failCurrentStage(state.pipeline),
      events: pushEvent(state.events, `${current.name} flagged for review`),
    };
  }

  if (action === "reset") {
    return {
      pipeline: createDefaultPipeline(),
      agents: [createAgent(0), createAgent(1)],
      events: createEventLog(["Pipeline reset"]),
    };
  }

  return state;
}

function terminalSize() {
  return {
    width: process.stdout.columns || 88,
    height: process.stdout.rows || 24,
  };
}

function renderToTerminal(state) {
  const { width, height } = terminalSize();
  const frame = renderFrame({ ...state, width, height: Math.max(16, height - 1) });
  process.stdout.write(`\x1b[H\x1b[2J${frame}`);
}

function runInteractive() {
  let state = {
    pipeline: createDefaultPipeline(),
    agents: [createAgent(0), createAgent(1)],
    events: createEventLog(["Pipeline initialized", "Planner and Builder ready"]),
  };

  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    process.stdout.write(`${renderFrame({ ...state, ...terminalSize() })}\n`);
    return;
  }

  readline.emitKeypressEvents(process.stdin);
  process.stdin.setRawMode(true);
  process.stdout.write("\x1b[?25l\x1b[?1000h\x1b[?1006h");

  const handleAction = (action) => {
    if (action === "quit") {
      cleanup();
      process.exit(0);
    }
    if (action) {
      state = applyAction(state, action);
      rerender();
    }
  };

  const handleMouseData = (chunk) => {
    const rawInput = chunk.toString("utf8");
    if (!rawInput.startsWith("\x1b[<")) return;

    const mouse = parseSgrMouse(rawInput);
    if (!mouse) return;

    const { width, height } = terminalSize();
    handleAction(actionForClick(mouse, width, Math.max(16, height - 1)));
  };

  const handleKeypress = (_str, key = {}) => {
    if (key.ctrl && key.name === "c") {
      cleanup();
      process.exit(0);
    }

    handleAction(actionFromKeyName(key.name));
  };

  const cleanup = () => {
    process.stdout.write("\x1b[?1000l\x1b[?1006l\x1b[?25h\x1b[0m\n");
    process.stdin.setRawMode(false);
    process.stdin.removeListener("data", handleMouseData);
    process.stdin.removeListener("keypress", handleKeypress);
  };

  const rerender = () => renderToTerminal(state);
  rerender();

  process.stdin.on("data", handleMouseData);
  process.stdin.on("keypress", handleKeypress);

  process.on("SIGINT", () => {
    cleanup();
    process.exit(0);
  });
}

function runSmoke() {
  const pipeline = advancePipeline(advancePipeline(createDefaultPipeline()));
  const agents = [createAgent(0), createAgent(1), createAgent(2)];
  const events = createEventLog(["Pipeline initialized", "Intake completed", "Spawn completed", "Reviewer joined"]);
  process.stdout.write(`${renderFrame({ pipeline, agents, events, width: 88, height: 24 })}\n`);
}

function printHelp() {
  process.stdout.write(`devinci agent orchestration TUI\n\nUsage:\n  node index.js            Start interactive TUI\n  node index.js --smoke    Render a deterministic smoke frame\n  node index.js --help     Show this help\n`);
}

if (require.main === module) {
  const args = new Set(process.argv.slice(2));
  if (args.has("--help") || args.has("-h")) {
    printHelp();
  } else if (args.has("--smoke") || args.has("--scripted-smoke")) {
    runSmoke();
  } else {
    runInteractive();
  }
}

module.exports = {
  actionForClick,
  applyAction,
  advancePipeline,
  createAgent,
  createDefaultPipeline,
  createEventLog,
  failCurrentStage,
  parseSgrMouse,
  pushEvent,
  renderFrame,
  runInteractive,
  runSmoke,
  stripAnsi,
};
