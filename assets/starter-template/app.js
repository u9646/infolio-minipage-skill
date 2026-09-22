(() => {
  "use strict";

  const state = { env: null, records: [], preferences: {}, pagination: null, photos: [], editing: null, busy: false, retry: null };
  let mutationSerial = 0;
  const byId = (id) => document.getElementById(id);
  const create = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  };
  const messages = () => window.MINIPAGE_MESSAGES;
  let language = "en";
  const text = (key, values = {}) => {
    const value = messages()[language]?.[key] ?? messages().en?.[key] ?? key;
    return value.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
  };

  function applyEnvironment(env) {
    state.env = env;
    const candidates = [env.language, env.language.split("-")[0], env.manifest.defaultLocale, "en"];
    language = candidates.find((candidate) => messages()[candidate]) ?? "en";
    document.documentElement.lang = language;
    document.documentElement.dir = /^(ar|fa|he|ur)(-|$)/i.test(language) ? "rtl" : "ltr";
    document.documentElement.dataset.theme = env.theme === "dark" ? "dark" : "light";
    document.title = text("pageTitle");
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      node.textContent = text(node.dataset.i18n);
    });
  }

  function setBusy(value) {
    state.busy = value;
    document.querySelectorAll("button, input, textarea").forEach((node) => {
      node.disabled = value;
    });
  }

  function status(key, error = false, retry) {
    const region = byId("status");
    const retryButton = byId("retry");
    state.retry = retry ?? null;
    region.hidden = !key;
    region.className = `status${error ? " error" : ""}`;
    byId("status-message").textContent = key ? text(key) : "";
    retryButton.textContent = text("retry");
    retryButton.hidden = !retry;
  }

  function failure(error, retry) {
    const key = {
      VERSION_CONFLICT: "errorConflict", DATA_NOT_READY: "errorNotReady",
      NOT_FOUND: "errorMissing", CHANNEL_CLOSED: "errorClosed",
      VALIDATION_FAILED: "errorValidation",
    }[error?.code] ?? "errorGeneric";
    const action = error?.code === "VERSION_CONFLICT" ? load : retry;
    status(key, true, ["CHANNEL_CLOSED", "NOT_FOUND", "VALIDATION_FAILED"].includes(error?.code) ? null : action);
  }

  async function run(action, { saving = false, retry } = {}) {
    if (state.busy) return;
    setBusy(true);
    status(saving ? "saving" : "loading");
    try {
      const value = await action();
      status(saving ? "saved" : null);
      return value;
    } catch (error) {
      failure(error, retry);
      throw error;
    } finally {
      setBusy(false);
    }
  }

  function photoNode(photo, removable = false) {
    const holder = create("span", "photo");
    const image = create("img");
    image.src = photo.url;
    image.alt = photo.name || text("photoAlt");
    image.addEventListener("error", () => {
      holder.replaceChildren(create("span", "meta", text("photoUnavailable")));
    }, { once: true });
    holder.append(image);
    if (removable) {
      const button = create("button", "text-button", text("delete"));
      button.type = "button";
      button.setAttribute("aria-label", text("removePhoto", { name: image.alt }));
      button.addEventListener("click", () => {
        state.photos = state.photos.filter((item) => item.id !== photo.id);
        renderDraftPhotos();
      });
      holder.append(button);
    }
    return holder;
  }

  function renderDraftPhotos() {
    byId("photo-list").replaceChildren(...state.photos.map((photo) => photoNode(photo, true)));
  }

  function render() {
    document.body.classList.toggle("compact", state.preferences.compact === true);
    byId("density-toggle").textContent = text(state.preferences.compact ? "compactOn" : "compactOff");
    byId("count").textContent = text("loadedCount", { loaded: state.records.length, total: state.pagination?.total ?? state.records.length });
    byId("load-more").hidden = !state.pagination?.nextCursor;
    byId("records").replaceChildren(...state.records.map((record) => {
      const article = create("article", `record${record.values.done ? " done" : ""}`);
      article.append(create("h3", "", record.values.title || ""));
      if (record.values.details) article.append(create("p", "", record.values.details));
      const actions = create("div", "record-actions");
      const toggle = create("button", "text-button", text(record.values.done ? "reopen" : "complete"));
      toggle.type = "button";
      toggle.setAttribute("aria-label", text(record.values.done ? "markOpen" : "markDone", { title: record.values.title }));
      toggle.addEventListener("click", () => updateRecord(record, { done: !record.values.done }));
      const edit = create("button", "text-button", text("edit"));
      edit.type = "button";
      edit.addEventListener("click", () => beginEdit(record));
      const remove = create("button", "text-button danger", text("delete"));
      remove.type = "button";
      remove.addEventListener("click", () => confirmRemove(record, actions));
      actions.append(toggle, edit, remove);
      article.append(actions);
      return article;
    }));
    byId("empty").hidden = state.records.length > 0;
  }

  function mutationId() {
    mutationSerial += 1;
    return `template:${Date.now()}:${mutationSerial}:${Math.random().toString(36).slice(2)}`;
  }

  function resetForm() {
    state.editing = null;
    state.photos = [];
    byId("item-form").reset();
    byId("form-title").textContent = text("newItem");
    byId("save").textContent = text("save");
    byId("cancel-edit").hidden = true;
    renderDraftPhotos();
  }

  function beginEdit(record) {
    state.editing = record;
    state.photos = Array.isArray(record.values.photos) ? [...record.values.photos] : [];
    byId("title").value = record.values.title ?? "";
    byId("details").value = record.values.details ?? "";
    byId("form-title").textContent = text("editItem");
    byId("save").textContent = text("saveChanges");
    byId("cancel-edit").hidden = false;
    renderDraftPhotos();
  }

  function updateRecord(record, values) {
    const requestId = mutationId();
    const attempt = () => run(async () => {
      const result = await window.infolio.collection.update({ fieldKey: "records", recordId: record.id, expectedVersion: record.version, values, mutationId: requestId });
      state.records = state.records.map((item) => item.id === result.record.id ? result.record : item);
      render();
    }, { saving: true, retry: attempt }).catch(() => {});
    void attempt();
  }

  function confirmRemove(record, actions) {
    actions.replaceChildren(create("span", "meta", text("deleteConfirm")));
    const cancel = create("button", "text-button", text("cancel"));
    cancel.type = "button";
    cancel.addEventListener("click", render);
    const confirm = create("button", "text-button danger", text("delete"));
    confirm.type = "button";
    confirm.addEventListener("click", () => removeRecord(record));
    actions.append(cancel, confirm);
  }

  function removeRecord(record) {
    const requestId = mutationId();
    const attempt = () => run(async () => {
      await window.infolio.collection.delete({ fieldKey: "records", recordId: record.id, expectedVersion: record.version, mutationId: requestId });
      state.records = state.records.filter((item) => item.id !== record.id);
      state.pagination.total = Math.max(0, state.pagination.total - 1);
      render();
    }, { saving: true, retry: attempt }).catch(() => {});
    void attempt();
  }

  async function load() {
    await run(async () => {
      const { page } = await window.infolio.collection.query();
      state.records = page.content.data.records ?? [];
      state.preferences = page.content.data.preferences ?? {};
      state.pagination = page.content._pagination?.records ?? {
        limit: 20,
        total: state.records.length,
        nextCursor: null,
      };
      render();
      byId("workspace").hidden = false;
    }, { retry: load }).catch(() => {});
  }

  byId("retry").addEventListener("click", () => state.retry?.());
  byId("cancel-edit").addEventListener("click", resetForm);
  byId("density-toggle").addEventListener("click", () => {
    const preferences = { ...state.preferences, compact: !state.preferences.compact };
    const requestId = mutationId();
    const attempt = () => run(async () => {
      await window.infolio.collection.update({ values: { preferences }, mutationId: requestId });
      state.preferences = preferences;
      render();
    }, { saving: true, retry: attempt }).catch(() => {});
    void attempt();
  });
  byId("pick-images").addEventListener("click", () => {
    void run(async () => {
      const images = await window.infolio.native.pickImages();
      if (images.length) state.photos.push(...images);
      renderDraftPhotos();
    }).catch(() => {});
  });
  byId("load-more").addEventListener("click", () => {
    void run(async () => {
      const result = await window.infolio.collection.query({ fieldKey: "records", limit: state.pagination.limit, cursor: state.pagination.nextCursor });
      state.records = [...new Map([...state.records, ...result.records].map((item) => [item.id, item])).values()];
      state.pagination = { ...state.pagination, total: result.total, nextCursor: result.nextCursor };
      render();
    }).catch(() => {});
  });
  byId("item-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const editing = state.editing;
    const values = { title: byId("title").value.trim(), details: byId("details").value.trim(), photos: [...state.photos] };
    if (!values.title) return;
    const requestId = mutationId();
    const attempt = () => run(async () => {
      const result = editing
        ? await window.infolio.collection.update({ fieldKey: "records", recordId: editing.id, expectedVersion: editing.version, values, mutationId: requestId })
        : await window.infolio.collection.create({ fieldKey: "records", values: { ...values, done: false }, mutationId: requestId });
      state.records = editing ? state.records.map((item) => item.id === result.record.id ? result.record : item) : [...state.records, result.record];
      if (!editing) state.pagination.total += 1;
      resetForm();
      render();
    }, { saving: true, retry: attempt }).catch(() => {});
    void attempt();
  });

  async function boot() {
    try {
      const env = await window.infolio.env.get();
      applyEnvironment(env);
      await load();
      resetForm();
    } catch (error) {
      failure(error, boot);
    }
  }

  void boot();
})();
