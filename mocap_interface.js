const convertForm = document.getElementById("convertForm");
const convertButton = document.getElementById("convertButton");
const downloadLink = document.getElementById("downloadLink");
const downloadHeld2Link = document.getElementById("downloadHeld2Link");
const downloadHeldLink = document.getElementById("downloadHeldLink");
const convertStatus = document.getElementById("convertStatus");
const pointSearch = document.getElementById("pointSearch");
const pointList = document.getElementById("pointList");
const selectAllButton = document.getElementById("selectAllButton");
const clearAllButton = document.getElementById("clearAllButton");
const hostInput = document.getElementById("hostInput");
const portInput = document.getElementById("portInput");
const fpsInput = document.getElementById("fpsInput");
const prefixInput = document.getElementById("prefixInput");
const loopInput = document.getElementById("loopInput");
const startStreamButton = document.getElementById("startStreamButton");
const stopStreamButton = document.getElementById("stopStreamButton");
const streamStatus = document.getElementById("streamStatus");
const summaryDataset = document.getElementById("summaryDataset");
const summaryPoints = document.getElementById("summaryPoints");
const summaryStream = document.getElementById("summaryStream");

const state = {
  dataset: null,
  selectedPoints: new Set(),
  datasetSelectionKey: null,
};

function setConvertStatus(message) {
  convertStatus.textContent = message;
}

function setStreamStatus(message) {
  streamStatus.textContent = message;
}

function updateSummary() {
  summaryDataset.textContent = state.dataset ? state.dataset.csvName : "No CSV yet";
  summaryPoints.textContent = String(state.selectedPoints.size);
}

function buildPointGroups(pointNames) {
  const sortedNames = [...pointNames].sort((left, right) => left.localeCompare(right));
  const pointSet = new Set(pointNames);
  const consumed = new Set();
  const groups = [];

  sortedNames.forEach((pointName) => {
    if (consumed.has(pointName)) {
      return;
    }

    const bilateralMatch = pointName.match(/^l(.+)$/i);
    if (bilateralMatch) {
      const suffix = bilateralMatch[1];
      const rightName = `r${suffix}`;
      if (pointSet.has(rightName)) {
        consumed.add(pointName);
        consumed.add(rightName);
        groups.push({
          key: suffix.toLowerCase(),
          label: suffix,
          items: [pointName, rightName],
        });
        return;
      }
    }

    if (/^r.+/i.test(pointName) && pointSet.has(`l${pointName.slice(1)}`)) {
      return;
    }

    consumed.add(pointName);
    groups.push({
      key: pointName.toLowerCase(),
      label: pointName,
      items: [pointName],
    });
  });

  groups.sort((left, right) => left.key.localeCompare(right.key));
  return groups;
}

function renderPoints() {
  if (!state.dataset) {
    pointList.className = "point-list empty";
    pointList.textContent = "Convert a dataset to see available points.";
    return;
  }

  const filter = pointSearch.value.trim().toLowerCase();
  const pointGroups = buildPointGroups(state.dataset.pointNames)
    .map((group) => ({
      ...group,
      items: group.items.filter((pointName) => pointName.toLowerCase().includes(filter)),
    }))
    .filter((group) => !filter || group.label.toLowerCase().includes(filter) || group.items.length);

  pointList.className = "point-list";
  pointList.innerHTML = "";

  pointGroups.forEach((group) => {
    const section = document.createElement("section");
    section.className = "point-group";

    const header = document.createElement("div");
    header.className = "point-group-header";

    const groupToggleLabel = document.createElement("label");
    groupToggleLabel.className = "point-group-toggle";

    const groupToggle = document.createElement("input");
    groupToggle.type = "checkbox";
    const selectedCount = group.items.filter((pointName) => state.selectedPoints.has(pointName)).length;
    groupToggle.checked = selectedCount === group.items.length;
    groupToggle.indeterminate = selectedCount > 0 && selectedCount < group.items.length;
    groupToggle.addEventListener("change", () => {
      if (groupToggle.checked) {
        group.items.forEach((pointName) => state.selectedPoints.add(pointName));
      } else {
        group.items.forEach((pointName) => state.selectedPoints.delete(pointName));
      }
      updateSummary();
      renderPoints();
    });

    const groupTitle = document.createElement("span");
    groupTitle.className = "point-group-title";
    groupTitle.textContent = group.label;

    groupToggleLabel.appendChild(groupToggle);
    groupToggleLabel.appendChild(groupTitle);
    header.appendChild(groupToggleLabel);

    const meta = document.createElement("span");
    meta.className = "point-group-meta";
    meta.textContent = group.items.length > 1 ? `${selectedCount}/${group.items.length}` : "single";
    header.appendChild(meta);

    section.appendChild(header);

    const items = document.createElement("div");
    items.className = "point-group-items";

    group.items.forEach((pointName) => {
      const label = document.createElement("label");
      label.className = "point-chip";

      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = state.selectedPoints.has(pointName);
      input.addEventListener("change", () => {
        if (input.checked) {
          state.selectedPoints.add(pointName);
        } else {
          state.selectedPoints.delete(pointName);
        }
        updateSummary();
      });

      const text = document.createElement("span");
      text.textContent = pointName;

      label.appendChild(input);
      label.appendChild(text);
      items.appendChild(label);
    });

    section.appendChild(items);
    pointList.appendChild(section);
  });

  if (!pointGroups.length) {
    pointList.className = "point-list empty";
    pointList.textContent = "No points match that filter.";
  }
}

function applyDataset(dataset) {
  state.dataset = dataset;
  state.selectedPoints = new Set(dataset.pointNames);
  state.datasetSelectionKey = dataset.csvName;
  downloadLink.href = dataset.downloadUrl;
  downloadLink.download = dataset.csvName;
  downloadLink.classList.remove("disabled");
  downloadHeld2Link.href = dataset.held2DownloadUrl;
  downloadHeld2Link.download = dataset.held2CsvName;
  downloadHeld2Link.classList.remove("disabled");
  downloadHeldLink.href = dataset.heldDownloadUrl;
  downloadHeldLink.download = dataset.heldCsvName;
  downloadHeldLink.classList.remove("disabled");
  setConvertStatus(
    `Converted ${dataset.csvName}, plus sampled variants ${dataset.held2CsvName} and ${dataset.heldCsvName}, with ${dataset.frameCount} source frames and ${dataset.pointNames.length} points.`
  );
  updateSummary();
  renderPoints();
}

async function refreshStatus() {
  const response = await fetch("/api/status");
  const payload = await response.json();

  if (payload.dataset) {
    const datasetChanged = state.datasetSelectionKey !== payload.dataset.csvName;
    state.dataset = payload.dataset;
    if (datasetChanged) {
      state.selectedPoints = new Set(payload.dataset.pointNames);
      state.datasetSelectionKey = payload.dataset.csvName;
    }
    downloadLink.href = payload.dataset.downloadUrl;
    downloadLink.download = payload.dataset.csvName;
    downloadLink.classList.remove("disabled");
    downloadHeld2Link.href = payload.dataset.held2DownloadUrl;
    downloadHeld2Link.download = payload.dataset.held2CsvName;
    downloadHeld2Link.classList.remove("disabled");
    downloadHeldLink.href = payload.dataset.heldDownloadUrl;
    downloadHeldLink.download = payload.dataset.heldCsvName;
    downloadHeldLink.classList.remove("disabled");
    setConvertStatus(
      `Ready: ${payload.dataset.csvName}, plus sampled variants ${payload.dataset.held2CsvName} and ${payload.dataset.heldCsvName}, with ${payload.dataset.frameCount} source frames and ${payload.dataset.pointNames.length} points.`
    );
    updateSummary();
    renderPoints();
  } else {
    downloadLink.classList.add("disabled");
    downloadHeld2Link.classList.add("disabled");
    downloadHeldLink.classList.add("disabled");
    setConvertStatus("Nothing converted yet.");
    state.dataset = null;
    state.selectedPoints = new Set();
    state.datasetSelectionKey = null;
    updateSummary();
  }

  const stream = payload.stream;
  if (stream.active) {
    setStreamStatus(
      `Streaming to ${stream.host}:${stream.port} at ${stream.fps} FPS. Frames sent: ${stream.framesSent}.`
    );
    summaryStream.textContent = "Streaming";
  } else if (stream.lastError) {
    setStreamStatus(`Streamer stopped: ${stream.lastError}`);
    summaryStream.textContent = "Error";
  } else {
    setStreamStatus("Streamer is idle.");
    summaryStream.textContent = "Idle";
  }
}

convertForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(convertForm);
  if (!formData.get("asf") || !formData.get("amc")) {
    setConvertStatus("Please choose both an ASF file and an AMC file.");
    return;
  }

  convertButton.disabled = true;
  setConvertStatus("Converting files...");

  try {
    const response = await fetch("/api/convert", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Conversion failed.");
    }
    applyDataset(payload.dataset);
  } catch (error) {
    setConvertStatus(error.message);
  } finally {
    convertButton.disabled = false;
  }
});

pointSearch.addEventListener("input", renderPoints);

selectAllButton.addEventListener("click", () => {
  if (!state.dataset) {
    return;
  }
  state.selectedPoints = new Set(state.dataset.pointNames);
  updateSummary();
  renderPoints();
});

clearAllButton.addEventListener("click", () => {
  state.selectedPoints = new Set();
  updateSummary();
  renderPoints();
});

startStreamButton.addEventListener("click", async () => {
  if (!state.dataset) {
    setStreamStatus("Convert a dataset before starting the stream.");
    return;
  }

  if (!state.selectedPoints.size) {
    setStreamStatus("Select at least one point to stream.");
    return;
  }

  setStreamStatus("Starting OSC stream...");

  try {
    const response = await fetch("/api/stream/start", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        host: hostInput.value || "127.0.0.1",
        port: Number(portInput.value || 7000),
        fps: Number(fpsInput.value || 30),
        prefix: prefixInput.value || "/mocap",
        loop: loopInput.checked,
        selectedPoints: Array.from(state.selectedPoints),
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Could not start OSC streaming.");
    }
    await refreshStatus();
  } catch (error) {
    setStreamStatus(error.message);
  }
});

stopStreamButton.addEventListener("click", async () => {
  try {
    await fetch("/api/stream/stop", { method: "POST" });
    await refreshStatus();
  } catch (error) {
    setStreamStatus(error.message);
  }
});

refreshStatus();
setInterval(refreshStatus, 1000);
