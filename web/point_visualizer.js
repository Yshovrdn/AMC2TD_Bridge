const canvas = document.getElementById("viewport");
const context = canvas.getContext("2d");

const fileInput = document.getElementById("fileInput");
const statusText = document.getElementById("statusText");
const playButton = document.getElementById("playButton");
const resetViewButton = document.getElementById("resetViewButton");
const fpsInput = document.getElementById("fpsInput");
const fpsOutput = document.getElementById("fpsOutput");
const speedInput = document.getElementById("speedInput");
const speedOutput = document.getElementById("speedOutput");
const loopInput = document.getElementById("loopInput");
const pointSizeInput = document.getElementById("pointSizeInput");
const pointSizeOutput = document.getElementById("pointSizeOutput");
const labelModeInput = document.getElementById("labelModeInput");
const gridInput = document.getElementById("gridInput");
const axesInput = document.getElementById("axesInput");
const searchInput = document.getElementById("searchInput");
const pointList = document.getElementById("pointList");
const timelineInput = document.getElementById("timelineInput");
const dropOverlay = document.getElementById("dropOverlay");
const fileNameValue = document.getElementById("fileNameValue");
const pointCountValue = document.getElementById("pointCountValue");
const frameCountValue = document.getElementById("frameCountValue");
const frameValue = document.getElementById("frameValue");
const showAllPointsButton = document.getElementById("showAllPointsButton");
const hideAllPointsButton = document.getElementById("hideAllPointsButton");
const showAllLabelsButton = document.getElementById("showAllLabelsButton");
const hideAllLabelsButton = document.getElementById("hideAllLabelsButton");

const state = {
  fileName: "",
  frameIds: [],
  pointNames: [],
  frames: [],
  bounds: {
    minX: -1,
    minY: -1,
    minZ: -1,
    maxX: 1,
    maxY: 1,
    maxZ: 1,
  },
  pointVisibility: new Map(),
  labelVisibility: new Map(),
  currentFrameIndex: 0,
  hoveredPointName: null,
  projectedPoints: [],
  playing: false,
  lastTime: 0,
  frameAccumulator: 0,
  camera: {
    yaw: 0.7,
    pitch: 0.42,
    distance: 180,
    target: { x: 0, y: 0, z: 0 },
  },
  drag: {
    active: false,
    pointerId: null,
    mode: "orbit",
    startX: 0,
    startY: 0,
  },
};

function resizeCanvas() {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;

  canvas.width = Math.max(1, Math.floor(width * ratio));
  canvas.height = Math.max(1, Math.floor(height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function formatNumber(value) {
  if (!Number.isFinite(value)) {
    return "";
  }
  return Number(value).toFixed(3).replace(/\.?0+$/, "");
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];

    if (character === '"') {
      const nextCharacter = text[index + 1];
      if (inQuotes && nextCharacter === '"') {
        cell += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (character === "," && !inQuotes) {
      row.push(cell);
      cell = "";
      continue;
    }

    if ((character === "\n" || character === "\r") && !inQuotes) {
      if (character === "\r" && text[index + 1] === "\n") {
        index += 1;
      }
      row.push(cell);
      if (row.some((value) => value.trim() !== "")) {
        rows.push(row);
      }
      row = [];
      cell = "";
      continue;
    }

    cell += character;
  }

  row.push(cell);
  if (row.some((value) => value.trim() !== "")) {
    rows.push(row);
  }

  return rows;
}

function inferPointColumns(headers) {
  const groups = new Map();
  const axisTokens = {
    x: "x",
    y: "y",
    z: "z",
    tx: "x",
    ty: "y",
    tz: "z",
  };

  headers.forEach((header, index) => {
    const cleanHeader = header.trim();
    const match = cleanHeader.match(/^(.*?)[_.-](tx|ty|tz|x|y|z)$/i);

    if (!match || !match[1]) {
      return;
    }

    const baseName = match[1].replace(/[_\-.]+$/, "");
    const axis = axisTokens[match[2].toLowerCase()];

    if (!baseName || !axis) {
      return;
    }

    if (!groups.has(baseName)) {
      groups.set(baseName, { name: baseName, indices: {}, firstIndex: index });
    }

    const group = groups.get(baseName);
    group.indices[axis] = index;
    group.firstIndex = Math.min(group.firstIndex, index);
  });

  return Array.from(groups.values())
    .filter((group) => group.indices.x !== undefined && group.indices.y !== undefined && group.indices.z !== undefined)
    .sort((left, right) => left.firstIndex - right.firstIndex);
}

function detectRotationalChannels(headers) {
  return headers.filter((header) => /_(rx|ry|rz)$/i.test(header)).length;
}

function loadCsvText(text, fileName) {
  const rows = parseCsv(text);
  if (rows.length < 2) {
    throw new Error("The CSV needs a header row and at least one data row.");
  }

  const headers = rows[0];
  const pointColumns = inferPointColumns(headers);
  const rotationalChannelCount = detectRotationalChannels(headers);
  const frameIndex = headers.findIndex((header) => header.trim().toLowerCase() === "frame");

  if (pointColumns.length === 0) {
    let message = "No complete point triplets were found. Expected columns like name_x, name_y, name_z.";
    if (rotationalChannelCount > 0) {
      message += " This CSV mostly contains rotations, which need a skeleton definition to become 3D joint positions.";
    }
    throw new Error(message);
  }

  const frameIds = [];
  const frames = [];
  const bounds = {
    minX: Infinity,
    minY: Infinity,
    minZ: Infinity,
    maxX: -Infinity,
    maxY: -Infinity,
    maxZ: -Infinity,
  };

  for (let rowIndex = 1; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex];
    const frameId = frameIndex >= 0 ? row[frameIndex] || String(rowIndex) : String(rowIndex);
    frameIds.push(frameId);

    const framePoints = pointColumns.map((pointColumn) => {
      const x = Number.parseFloat(row[pointColumn.indices.x]);
      const y = Number.parseFloat(row[pointColumn.indices.y]);
      const z = Number.parseFloat(row[pointColumn.indices.z]);
      const valid = Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z);

      if (valid) {
        bounds.minX = Math.min(bounds.minX, x);
        bounds.minY = Math.min(bounds.minY, y);
        bounds.minZ = Math.min(bounds.minZ, z);
        bounds.maxX = Math.max(bounds.maxX, x);
        bounds.maxY = Math.max(bounds.maxY, y);
        bounds.maxZ = Math.max(bounds.maxZ, z);
      }

      return {
        name: pointColumn.name,
        x,
        y,
        z,
        valid,
      };
    });

    frames.push(framePoints);
  }

  if (!Number.isFinite(bounds.minX)) {
    throw new Error("The CSV loaded, but none of the point columns contained valid numeric coordinates.");
  }

  state.fileName = fileName;
  state.frameIds = frameIds;
  state.pointNames = pointColumns.map((pointColumn) => pointColumn.name);
  state.frames = frames;
  state.bounds = bounds;
  state.currentFrameIndex = 0;
  state.hoveredPointName = null;
  state.projectedPoints = [];
  state.playing = false;
  state.lastTime = 0;
  state.frameAccumulator = 0;
  state.pointVisibility = new Map(state.pointNames.map((name) => [name, true]));
  state.labelVisibility = new Map(state.pointNames.map((name) => [name, true]));

  timelineInput.max = String(Math.max(0, state.frames.length - 1));
  timelineInput.value = "0";
  pointCountValue.textContent = String(state.pointNames.length);
  frameCountValue.textContent = String(state.frames.length);
  fileNameValue.textContent = fileName;

  if (rotationalChannelCount > 0 && pointColumns.length <= 1) {
    setStatus(
      "Loaded the CSV. Only a small number of point triplets were found, and the file also contains many rotations. For full-body AMC playback, you will need the matching .asf skeleton."
    );
  } else {
    setStatus(`Loaded ${fileName} with ${state.pointNames.length} point sets across ${state.frames.length} frames.`);
  }

  buildPointList();
  resetCamera();
  updateUiForCurrentFrame();
}

function setStatus(message) {
  statusText.textContent = message;
}

function resetCamera() {
  const bounds = state.bounds;
  const currentFrame = state.frames[state.currentFrameIndex] || [];
  const validPoints = currentFrame.filter((point) => point.valid);
  const center = validPoints.length
    ? validPoints.reduce(
        (accumulator, point, index) => ({
          x: accumulator.x + point.x / validPoints.length,
          y: accumulator.y + point.y / validPoints.length,
          z: accumulator.z + point.z / validPoints.length,
        }),
        { x: 0, y: 0, z: 0 }
      )
    : {
        x: (bounds.minX + bounds.maxX) * 0.5,
        y: (bounds.minY + bounds.maxY) * 0.5,
        z: (bounds.minZ + bounds.maxZ) * 0.5,
      };
  const spanX = bounds.maxX - bounds.minX;
  const spanY = bounds.maxY - bounds.minY;
  const spanZ = bounds.maxZ - bounds.minZ;
  const span = Math.max(spanX, spanY, spanZ, 1);

  state.camera.target = center;
  state.camera.distance = span * 2.4;
  state.camera.yaw = 0.7;
  state.camera.pitch = 0.42;
}

function updateUiForCurrentFrame() {
  timelineInput.value = String(state.currentFrameIndex);
  const frameId = state.frameIds[state.currentFrameIndex] ?? 0;
  frameValue.textContent = String(frameId);
}

function buildPointList() {
  pointList.innerHTML = "";
  const filter = searchInput.value.trim().toLowerCase();

  state.pointNames
    .filter((name) => name.toLowerCase().includes(filter))
    .forEach((name) => {
      const row = document.createElement("div");
      row.className = "point-row";

      const nameLabel = document.createElement("div");
      nameLabel.className = "point-name";
      nameLabel.textContent = name;
      row.appendChild(nameLabel);

      const pointToggleLabel = document.createElement("label");
      const pointToggle = document.createElement("input");
      pointToggle.type = "checkbox";
      pointToggle.checked = state.pointVisibility.get(name) !== false;
      pointToggle.addEventListener("change", () => {
        state.pointVisibility.set(name, pointToggle.checked);
      });
      pointToggleLabel.appendChild(pointToggle);
      pointToggleLabel.appendChild(document.createTextNode("Point"));
      row.appendChild(pointToggleLabel);

      const labelToggleLabel = document.createElement("label");
      const labelToggle = document.createElement("input");
      labelToggle.type = "checkbox";
      labelToggle.checked = state.labelVisibility.get(name) !== false;
      labelToggle.addEventListener("change", () => {
        state.labelVisibility.set(name, labelToggle.checked);
      });
      labelToggleLabel.appendChild(labelToggle);
      labelToggleLabel.appendChild(document.createTextNode("Label"));
      row.appendChild(labelToggleLabel);

      pointList.appendChild(row);
    });
}

function setAllVisibility(map, value) {
  state.pointNames.forEach((name) => {
    map.set(name, value);
  });
  buildPointList();
}

function getCameraVectors() {
  const { yaw, pitch, distance, target } = state.camera;
  const cameraPosition = {
    x: target.x + distance * Math.cos(pitch) * Math.sin(yaw),
    y: target.y + distance * Math.sin(pitch),
    z: target.z + distance * Math.cos(pitch) * Math.cos(yaw),
  };

  const forward = normalize({
    x: target.x - cameraPosition.x,
    y: target.y - cameraPosition.y,
    z: target.z - cameraPosition.z,
  });

  let right = cross(forward, { x: 0, y: 1, z: 0 });
  if (length(right) < 1e-6) {
    right = { x: 1, y: 0, z: 0 };
  } else {
    right = normalize(right);
  }

  const up = normalize(cross(right, forward));

  return { cameraPosition, forward, right, up };
}

function length(vector) {
  return Math.hypot(vector.x, vector.y, vector.z);
}

function normalize(vector) {
  const vectorLength = length(vector) || 1;
  return {
    x: vector.x / vectorLength,
    y: vector.y / vectorLength,
    z: vector.z / vectorLength,
  };
}

function cross(left, right) {
  return {
    x: left.y * right.z - left.z * right.y,
    y: left.z * right.x - left.x * right.z,
    z: left.x * right.y - left.y * right.x,
  };
}

function dot(left, right) {
  return left.x * right.x + left.y * right.y + left.z * right.z;
}

function projectPoint(point, cameraVectors) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.width / ratio;
  const height = canvas.height / ratio;
  const relative = {
    x: point.x - cameraVectors.cameraPosition.x,
    y: point.y - cameraVectors.cameraPosition.y,
    z: point.z - cameraVectors.cameraPosition.z,
  };
  const cameraX = dot(relative, cameraVectors.right);
  const cameraY = dot(relative, cameraVectors.up);
  const cameraZ = dot(relative, cameraVectors.forward);

  if (cameraZ <= 0.01) {
    return null;
  }

  const focalLength = Math.min(width, height) * 0.92;
  const scale = focalLength / cameraZ;

  return {
    screenX: width * 0.5 + cameraX * scale,
    screenY: height * 0.5 - cameraY * scale,
    depth: cameraZ,
  };
}

function drawLine3D(start, end, cameraVectors, strokeStyle, lineWidth = 1) {
  const projectedStart = projectPoint(start, cameraVectors);
  const projectedEnd = projectPoint(end, cameraVectors);

  if (!projectedStart || !projectedEnd) {
    return;
  }

  context.beginPath();
  context.moveTo(projectedStart.screenX, projectedStart.screenY);
  context.lineTo(projectedEnd.screenX, projectedEnd.screenY);
  context.strokeStyle = strokeStyle;
  context.lineWidth = lineWidth;
  context.stroke();
}

function drawGrid(cameraVectors) {
  if (!gridInput.checked) {
    return;
  }

  const bounds = state.bounds;
  const floorY = bounds.minY;
  const spanX = Math.max(bounds.maxX - bounds.minX, 1);
  const spanZ = Math.max(bounds.maxZ - bounds.minZ, 1);
  const extent = Math.max(spanX, spanZ) * 0.75 + 20;
  const centerX = (bounds.minX + bounds.maxX) * 0.5;
  const centerZ = (bounds.minZ + bounds.maxZ) * 0.5;
  const divisions = 10;

  for (let step = -divisions; step <= divisions; step += 1) {
    const t = (step / divisions) * extent;
    drawLine3D(
      { x: centerX - extent, y: floorY, z: centerZ + t },
      { x: centerX + extent, y: floorY, z: centerZ + t },
      cameraVectors,
      "rgba(23, 22, 20, 0.08)"
    );
    drawLine3D(
      { x: centerX + t, y: floorY, z: centerZ - extent },
      { x: centerX + t, y: floorY, z: centerZ + extent },
      cameraVectors,
      "rgba(23, 22, 20, 0.08)"
    );
  }
}

function drawAxes(cameraVectors) {
  if (!axesInput.checked) {
    return;
  }

  const span = Math.max(
    state.bounds.maxX - state.bounds.minX,
    state.bounds.maxY - state.bounds.minY,
    state.bounds.maxZ - state.bounds.minZ,
    1
  ) * 0.18;
  const origin = state.camera.target;

  drawLine3D(origin, { x: origin.x + span, y: origin.y, z: origin.z }, cameraVectors, "rgba(198, 76, 76, 0.85)", 1.5);
  drawLine3D(origin, { x: origin.x, y: origin.y + span, z: origin.z }, cameraVectors, "rgba(88, 148, 88, 0.85)", 1.5);
  drawLine3D(origin, { x: origin.x, y: origin.y, z: origin.z + span }, cameraVectors, "rgba(66, 122, 196, 0.85)", 1.5);
}

function shouldDrawLabel(name) {
  const mode = labelModeInput.value;
  if (mode === "none") {
    return false;
  }
  if (mode === "hover") {
    return state.hoveredPointName === name;
  }
  if (mode === "all") {
    return true;
  }
  return state.labelVisibility.get(name) !== false;
}

function renderScene() {
  resizeCanvas();
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.width / ratio;
  const height = canvas.height / ratio;

  context.clearRect(0, 0, width, height);
  context.fillStyle = "#f6f4ee";
  context.fillRect(0, 0, width, height);

  if (!state.frames.length) {
    drawEmptyState(width, height);
    return;
  }

  const cameraVectors = getCameraVectors();
  drawGrid(cameraVectors);
  drawAxes(cameraVectors);

  const frame = state.frames[state.currentFrameIndex] || [];
  state.projectedPoints = frame
    .filter((point) => point.valid && state.pointVisibility.get(point.name) !== false)
    .map((point) => {
      const projected = projectPoint(point, cameraVectors);
      return projected ? { ...point, ...projected } : null;
    })
    .filter(Boolean)
    .sort((left, right) => right.depth - left.depth);

  const pointSize = Number(pointSizeInput.value);

  state.projectedPoints.forEach((point) => {
    const radius = pointSize * (0.65 + 45 / (point.depth + 45));
    const isHovered = point.name === state.hoveredPointName;

    context.beginPath();
    context.arc(point.screenX, point.screenY, radius, 0, Math.PI * 2);
    context.fillStyle = isHovered ? "rgba(31, 111, 235, 0.95)" : "rgba(23, 22, 20, 0.88)";
    context.fill();

    context.beginPath();
    context.arc(point.screenX, point.screenY, radius + 2, 0, Math.PI * 2);
    context.strokeStyle = isHovered ? "rgba(31, 111, 235, 0.22)" : "rgba(23, 22, 20, 0.08)";
    context.lineWidth = 4;
    context.stroke();

    if (shouldDrawLabel(point.name)) {
      drawLabel(point, radius);
    }
  });
}

function drawEmptyState(width, height) {
  context.fillStyle = "rgba(23, 22, 20, 0.72)";
  context.font = '500 18px "SF Pro Text", "Segoe UI", sans-serif';
  context.textAlign = "center";
  context.fillText("Load a CSV to begin", width / 2, height / 2 - 6);
  context.fillStyle = "rgba(110, 103, 94, 0.9)";
  context.font = '400 14px "SF Pro Text", "Segoe UI", sans-serif';
  context.fillText("Expected point triplets such as marker_x, marker_y, marker_z.", width / 2, height / 2 + 20);
}

function drawLabel(point, radius) {
  const text = `${point.name}  (${formatNumber(point.x)}, ${formatNumber(point.y)}, ${formatNumber(point.z)})`;
  context.font = '500 12px "SF Pro Text", "Segoe UI", sans-serif';
  const metrics = context.measureText(text);
  const paddingX = 10;
  const paddingY = 7;
  const x = point.screenX + radius + 10;
  const y = point.screenY - radius - 8;
  const width = metrics.width + paddingX * 2;
  const height = 26;

  context.fillStyle = "rgba(255, 255, 255, 0.92)";
  roundRect(context, x, y - height + paddingY, width, height, 10);
  context.fill();
  context.strokeStyle = "rgba(23, 22, 20, 0.12)";
  context.lineWidth = 1;
  context.stroke();

  context.fillStyle = "rgba(23, 22, 20, 0.9)";
  context.textAlign = "left";
  context.textBaseline = "alphabetic";
  context.fillText(text, x + paddingX, y);
}

function roundRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function updatePlayback(time) {
  if (!state.playing || state.frames.length <= 1) {
    state.lastTime = time;
    return;
  }

  if (!state.lastTime) {
    state.lastTime = time;
    return;
  }

  const fps = Number(fpsInput.value);
  const speed = Number(speedInput.value) / 100;
  const frameDuration = 1000 / fps;
  const elapsed = time - state.lastTime;
  state.lastTime = time;
  state.frameAccumulator += elapsed * speed;

  while (state.frameAccumulator >= frameDuration) {
    state.frameAccumulator -= frameDuration;
    if (state.currentFrameIndex >= state.frames.length - 1) {
      if (loopInput.checked) {
        state.currentFrameIndex = 0;
      } else {
        state.currentFrameIndex = state.frames.length - 1;
        state.playing = false;
        playButton.textContent = "Play";
        break;
      }
    } else {
      state.currentFrameIndex += 1;
    }
  }

  updateUiForCurrentFrame();
}

function animationLoop(time) {
  updatePlayback(time);
  renderScene();
  requestAnimationFrame(animationLoop);
}

function getHoveredPoint(mouseX, mouseY) {
  let closest = null;
  let closestDistance = 18;

  state.projectedPoints.forEach((point) => {
    const distance = Math.hypot(point.screenX - mouseX, point.screenY - mouseY);
    if (distance < closestDistance) {
      closest = point.name;
      closestDistance = distance;
    }
  });

  return closest;
}

function updateHover(event) {
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  state.hoveredPointName = getHoveredPoint(x, y);
}

function readFile(file) {
  if (!file) {
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    try {
      loadCsvText(String(reader.result), file.name);
    } catch (error) {
      setStatus(error.message);
      state.frames = [];
      pointCountValue.textContent = "0";
      frameCountValue.textContent = "0";
      frameValue.textContent = "0";
      fileNameValue.textContent = file.name;
    }
  };
  reader.readAsText(file);
}

async function loadCsvFromUrl(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Could not load CSV from ${url}`);
  }
  const text = await response.text();
  const fileName = url.split("/").pop() || url;
  loadCsvText(text, fileName);
}

function setDropOverlayVisible(visible) {
  dropOverlay.classList.toggle("visible", visible);
}

window.addEventListener("resize", resizeCanvas);

fileInput.addEventListener("change", () => {
  const [file] = fileInput.files;
  readFile(file);
});

playButton.addEventListener("click", () => {
  state.playing = !state.playing;
  state.lastTime = 0;
  state.frameAccumulator = 0;
  playButton.textContent = state.playing ? "Pause" : "Play";
});

resetViewButton.addEventListener("click", resetCamera);

fpsInput.addEventListener("input", () => {
  fpsOutput.textContent = fpsInput.value;
});

speedInput.addEventListener("input", () => {
  speedOutput.textContent = `${(Number(speedInput.value) / 100).toFixed(2)}x`;
});

pointSizeInput.addEventListener("input", () => {
  pointSizeOutput.textContent = pointSizeInput.value;
});

timelineInput.addEventListener("input", () => {
  state.currentFrameIndex = Number(timelineInput.value);
  updateUiForCurrentFrame();
});

searchInput.addEventListener("input", buildPointList);

showAllPointsButton.addEventListener("click", () => setAllVisibility(state.pointVisibility, true));
hideAllPointsButton.addEventListener("click", () => setAllVisibility(state.pointVisibility, false));
showAllLabelsButton.addEventListener("click", () => setAllVisibility(state.labelVisibility, true));
hideAllLabelsButton.addEventListener("click", () => setAllVisibility(state.labelVisibility, false));

canvas.addEventListener("pointerdown", (event) => {
  state.drag.active = true;
  state.drag.pointerId = event.pointerId;
  state.drag.startX = event.clientX;
  state.drag.startY = event.clientY;
  state.drag.mode = event.shiftKey || event.button === 1 ? "pan" : "orbit";
  canvas.setPointerCapture(event.pointerId);
  canvas.classList.add("dragging");
});

canvas.addEventListener("pointermove", (event) => {
  updateHover(event);

  if (!state.drag.active || event.pointerId !== state.drag.pointerId) {
    return;
  }

  const deltaX = event.clientX - state.drag.startX;
  const deltaY = event.clientY - state.drag.startY;
  state.drag.startX = event.clientX;
  state.drag.startY = event.clientY;

  if (state.drag.mode === "orbit") {
    state.camera.yaw -= deltaX * 0.01;
    state.camera.pitch = clamp(state.camera.pitch - deltaY * 0.01, -1.45, 1.45);
    return;
  }

  const cameraVectors = getCameraVectors();
  const panScale = state.camera.distance * 0.0016;
  state.camera.target.x -= cameraVectors.right.x * deltaX * panScale;
  state.camera.target.y -= cameraVectors.right.y * deltaX * panScale;
  state.camera.target.z -= cameraVectors.right.z * deltaX * panScale;
  state.camera.target.x += cameraVectors.up.x * deltaY * panScale;
  state.camera.target.y += cameraVectors.up.y * deltaY * panScale;
  state.camera.target.z += cameraVectors.up.z * deltaY * panScale;
});

function finishPointerInteraction(event) {
  if (event.pointerId !== state.drag.pointerId) {
    return;
  }
  state.drag.active = false;
  state.drag.pointerId = null;
  canvas.classList.remove("dragging");
}

canvas.addEventListener("pointerup", finishPointerInteraction);
canvas.addEventListener("pointercancel", finishPointerInteraction);
canvas.addEventListener("mouseleave", () => {
  if (!state.drag.active) {
    state.hoveredPointName = null;
  }
});

canvas.addEventListener("wheel", (event) => {
  event.preventDefault();
  const zoomFactor = Math.exp(event.deltaY * 0.0012);
  state.camera.distance = clamp(state.camera.distance * zoomFactor, 0.5, 100000);
}, { passive: false });

canvas.addEventListener("contextmenu", (event) => {
  event.preventDefault();
});

["dragenter", "dragover"].forEach((eventName) => {
  window.addEventListener(eventName, (event) => {
    event.preventDefault();
    setDropOverlayVisible(true);
  });
});

["dragleave", "drop"].forEach((eventName) => {
  window.addEventListener(eventName, (event) => {
    event.preventDefault();
    if (eventName === "drop") {
      const [file] = event.dataTransfer.files;
      readFile(file);
    }
    setDropOverlayVisible(false);
  });
});

fpsOutput.textContent = fpsInput.value;
speedOutput.textContent = `${(Number(speedInput.value) / 100).toFixed(2)}x`;
pointSizeOutput.textContent = pointSizeInput.value;
updateUiForCurrentFrame();

const autoLoadSource = new URLSearchParams(window.location.search).get("src");
if (autoLoadSource) {
  loadCsvFromUrl(autoLoadSource).catch((error) => {
    setStatus(error.message);
  });
}

requestAnimationFrame(animationLoop);
