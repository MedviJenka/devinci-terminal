const assert = require("node:assert/strict");
const { test } = require("node:test");

const {
  actionForClick,
  applyAction,
  createDefaultPipeline,
  advancePipeline,
  createAgent,
  renderFrame,
  createEventLog,
  parseSgrMouse,
  stripAnsi,
} = require("../index.js");

test("createDefaultPipeline builds an agent orchestration pipeline with a single active stage", () => {
  const pipeline = createDefaultPipeline();

  assert.deepEqual(
    pipeline.stages.map((stage) => stage.status),
    ["active", "pending", "pending", "pending", "pending", "pending"],
  );
  assert.equal(pipeline.stages[0].name, "Intake");
  assert.equal(pipeline.stages.at(-1).name, "Ship");
});

test("advancePipeline completes the current stage and activates the next stage", () => {
  const pipeline = createDefaultPipeline();

  const next = advancePipeline(pipeline);

  assert.deepEqual(
    next.stages.map((stage) => stage.status),
    ["done", "active", "pending", "pending", "pending", "pending"],
  );
  assert.equal(next.cursor, 1);
  assert.equal(pipeline.cursor, 0);
});

test("advancePipeline leaves a completed pipeline stable", () => {
  let pipeline = createDefaultPipeline();
  for (let i = 0; i < 10; i += 1) pipeline = advancePipeline(pipeline);

  assert.deepEqual(
    pipeline.stages.map((stage) => stage.status),
    ["done", "done", "done", "done", "done", "done"],
  );
  assert.equal(pipeline.cursor, 5);
});

test("createAgent assigns distinct roles and ready status", () => {
  assert.deepEqual(createAgent(2), {
    id: "A03",
    name: "Agent 3",
    role: "Reviewer",
    status: "ready",
  });
});

test("renderFrame exposes pipeline, agents, event log, colored gradients, and clickable buttons", () => {
  const pipeline = advancePipeline(createDefaultPipeline());
  const agents = [createAgent(0), createAgent(1)];
  const events = createEventLog(["Spawned Planner", "Moved to Spawn"]);

  const frame = renderFrame({ pipeline, agents, events, width: 88, height: 24 });
  const plain = stripAnsi(frame);

  assert.match(plain, /Agent Orchestration Pipeline/);
  assert.match(plain, /✓ Intake/);
  assert.match(plain, /▶ Spawn/);
  assert.match(plain, /A01/);
  assert.match(plain, /Spawned Planner/);
  assert.match(plain, /\[n\] Next/);
  assert.match(frame, /\x1b\[38;2;/);
  assert.ok(plain.split("\n").every((line) => line.length <= 88));
});

test("actionForClick maps the rendered next button to the next action", () => {
  const frame = stripAnsi(renderFrame({ pipeline: createDefaultPipeline(), agents: [], events: [], width: 88, height: 24 }));
  const lines = frame.split("\n");
  const buttonRow = lines.length - 1;
  const nextColumn = lines[buttonRow].indexOf("[n] Next") + 1;

  assert.equal(actionForClick({ col: nextColumn, row: buttonRow }, 88, 24), "next");
});

test("parseSgrMouse decodes terminal click reports into zero-based coordinates", () => {
  assert.deepEqual(parseSgrMouse("\x1b[<0;14;24M"), {
    button: 0,
    col: 13,
    row: 23,
    pressed: true,
  });
});

test("applyAction advances the same state used by keyboard and mouse controls", () => {
  const state = {
    pipeline: createDefaultPipeline(),
    agents: [createAgent(0)],
    events: createEventLog(["Pipeline initialized"]),
  };

  const next = applyAction(state, "next");

  assert.equal(next.pipeline.cursor, 1);
  assert.match(next.events.at(-1).message, /Intake completed/);
});
